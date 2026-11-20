"""
Biên dịch điều kiện dữ liệu của dòng .decl ('Template[A, B] | <act_cond> | <corr_cond> | <time_cond>')
thành hàm kiểm tra tất định trên một event (Tầng 3).

Cú pháp (một hoặc nhiều mệnh đề nối bằng 'and'):
    A.<thuộc tính> <op> <giá trị>          op ∈ {==, !=, <, <=, >, >=}
    A.date <op> <ngày>                     ngày = year-MM-DD | year+k-MM-DD | YYYY-MM-DD

- Tên thuộc tính được phép có dấu cách / gạch nối (BPIC2018: 'case:young farmer', 'case:program-id').
- Giá trị đọc ở event trước, rồi ở bản ghi hồ sơ dùng chung (khóa '_case', đề xuất 1); tên rút gọn
  'RequestedAmount' được thử thêm dạng 'case:RequestedAmount' (như trước).
- 'date' là thuộc tính giả: ngày LỊCH của event theo múi giờ `timezone` (BPIC2018: Europe/Berlin — log gốc
  ghi giờ Đức, parquet lưu UTC). 'year' = giá trị `year_attr` của hồ sơ (mặc định case:year).
  Thiếu năm / năm không phải số / thiếu thời điểm -> mệnh đề KHÔNG thỏa.
- Mệnh đề không phân tích được -> coi là luôn đúng (giữ hành vi cũ của engine, tương thích BPIC2017).
"""

import math
import re
import sys
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

Event = Dict[str, Any]
Predicate = Callable[[Event], bool]

DATE_ATTRIBUTE = "date"
DEFAULT_TIMEZONE = "UTC"
DEFAULT_YEAR_ATTR = "case:year"
CASE_KEY = "_case"
TIMESTAMP_KEY = "_ts_sec"

_CLAUSE = re.compile(r"^[AaTt]\.(.+?)\s*(==|!=|<=|>=|<|>)\s*(.+)$")
DATE_VALUE = re.compile(r"^(year(?:[+-]\d+)?|\d{4})-(\d{2})-(\d{2})$")
_AND = re.compile(r"\s+and\s+")


def _always_true(_: Event) -> bool:
    return True


def split_conjunction(cond_str: str) -> List[str]:
    """Tách theo ' and ' nằm NGOÀI dấu nháy."""
    parts: List[str] = []
    buf: List[str] = []
    quote: Optional[str] = None
    i = 0
    while i < len(cond_str):
        ch = cond_str[i]
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch.isspace():
            m = _AND.match(cond_str, i)
            if m:
                parts.append("".join(buf).strip())
                buf = []
                i = m.end()
                continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _is_missing(val: Any) -> bool:
    return val is None or (isinstance(val, float) and math.isnan(val))


def lookup(ev: Event, attr: str) -> Any:
    """Giá trị thuộc tính: event -> bản ghi hồ sơ '_case'; thử cả tiền tố 'case:' cho tên rút gọn."""
    names = [attr] if attr.startswith("case:") else [attr, f"case:{attr}"]
    case = ev.get(CASE_KEY) or {}
    for source in (ev, case):
        for name in names:
            val = source.get(name)
            if not _is_missing(val):
                return val
    return None


def _parse_value(raw: str) -> Any:
    if raw in ("True", "true"):
        return True
    if raw in ("False", "false"):
        return False
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    try:
        return float(raw)
    except ValueError:
        return raw


def _equal(val: Any, target: Any) -> bool:
    """
    Bằng nhau; một chuỗi số trong log so với một số trong dòng .decl được so như số.
    (format_condition không đặt nháy cho chuỗi toàn chữ số, nên 'A.case:year == 2016' đọc ra số 2016.0 trong khi
    log BPIC2018 lưu case:year là chuỗi '2016' — trước 2026-11-09 phép so này luôn sai.)
    """
    if val == target:
        return True
    if isinstance(target, float) and isinstance(val, str):
        try:
            return float(val) == target
        except ValueError:
            return False
    return False


def _compare(val: Any, op: str, target: Any) -> bool:
    if op == "==":
        return _equal(val, target)
    if op == "!=":
        return not _equal(val, target)
    try:
        a, b = (val, target) if isinstance(target, date) else (float(val), float(target))
    except (ValueError, TypeError):
        return False
    return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]


def _value_predicate(attr: str, op: str, target: Any) -> Predicate:
    def _pred(ev: Event) -> bool:
        val = lookup(ev, attr)
        if val is None:
            return False
        if isinstance(target, bool):
            val = val.lower() == "true" if isinstance(val, str) else bool(val)
        return _compare(val, op, target)

    return _pred


def _case_year(ev: Event, year_attr: str) -> Optional[int]:
    raw = lookup(ev, year_attr)
    if raw is None:
        return None
    try:
        return int(float(str(raw)))
    except ValueError:
        return None


def _date_predicate(op: str, raw: str, tz: ZoneInfo, year_attr: str) -> Optional[Predicate]:
    m = DATE_VALUE.match(raw.strip("\"'"))
    if not m:
        return None
    year_spec, month, day = m.group(1), int(m.group(2)), int(m.group(3))
    offset = int(year_spec[4:] or 0) if year_spec.startswith("year") else None

    def _pred(ev: Event) -> bool:
        ts = ev.get(TIMESTAMP_KEY)
        if _is_missing(ts):
            return False
        if offset is None:
            year = int(year_spec)
        else:
            base = _case_year(ev, year_attr)
            if base is None:
                return False
            year = base + offset
        try:
            target = date(year, month, day)
        except ValueError:
            return False
        return _compare(datetime.fromtimestamp(float(ts), tz).date(), op, target)

    return _pred


def _dropped(clause: str) -> Predicate:
    """v1.2 (rà soát lõi C8): điều kiện không đọc được vẫn bị bỏ (tương thích BPIC2017) nhưng KHÔNG im lặng."""
    if clause.strip() and clause.strip() not in _WARNED:
        _WARNED.add(clause.strip())
        sys.stderr.write(f"CẢNH BÁO: bỏ điều kiện không đọc được (coi như luôn đúng): '{clause.strip()}'\n")
    return _always_true


_WARNED: set = set()


def _compile_clause(clause: str, tz: ZoneInfo, year_attr: str) -> Predicate:
    m = _CLAUSE.match(clause.strip())
    if not m:
        return _dropped(clause)
    attr, op, raw = m.group(1).strip(), m.group(2), m.group(3).strip()
    if attr == DATE_ATTRIBUTE:
        return _date_predicate(op, raw, tz, year_attr) or _dropped(clause)
    return _value_predicate(attr, op, _parse_value(raw))


def compile_condition(
    cond_str: str, timezone: str = DEFAULT_TIMEZONE, year_attr: str = DEFAULT_YEAR_ATTR
) -> Predicate:
    """Hàm event -> bool; mọi mệnh đề (nối 'and') phải thỏa. Chuỗi rỗng -> luôn đúng."""
    if not cond_str or not cond_str.strip():
        return _always_true
    tz = ZoneInfo(timezone)
    preds = [_compile_clause(c, tz, year_attr) for c in split_conjunction(cond_str)]
    if len(preds) == 1:
        return preds[0]
    return lambda ev: all(p(ev) for p in preds)
