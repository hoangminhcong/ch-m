"""
Chuyển ký hiệu ràng buộc của người gán nhãn (phiếu CAP, docs/HUONG_DAN_GAN_NHAN_CAP.md) sang AST DECLARE.

Cú pháp nhận (mục 4–5 của docs/HUONG_DAN_GAN_NHAN_CAP.md):
    Template(A)                                Existence(A)
    Template(A → B)                            Response(A → B)        ('->' cũng được)
    {A1 | A2}                                  nhóm activity: cùng một bước ghi bằng tên khác nhau (VD theo năm)
    … ≤ n ngày  /  … trong ≤ n ngày            thời hạn: ngày (d), giờ (h), tuần (w), tháng lịch (mo),
                                               ngày làm việc (wd) — giữ đúng đơn vị của luật, không quy đổi
    … với X op v  /  … | X op v and Y op w     điều kiện thuộc tính ('và' = 'and')
    ngày(X) <= 15/05/năm                       điều kiện ngày lịch (năm = case:year, năm+1 = năm sau)
    ngày(X) trong [01/12/năm, 30/06/năm+1]     khoảng ngày → hai điều kiện >= và <=
X = activity KÍCH HOẠT: B với Precedence(A → B) (và Alternate/Chain/Not Precedence), A với các mẫu khác
(chuẩn Declare4Py; F-PREC, kiểm toán 2026-11-09).

Bộ chuyển KHÔNG đoán: tên activity phải trùng một activity của Γ (chỉ bỏ qua khác biệt chữ hoa/thường và
khoảng trắng quanh '/'), thuộc tính phải có trong Γ. Sai → NotationError kèm gợi ý, để người gán / người duyệt
sửa phiếu.
"""

import difflib
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..mde.constraint_ast import BINARY_TEMPLATES, UNARY_TEMPLATES, activity_group, activity_members, validate_layer1_ast
from ..mde.typing_environment import ProcessTypingEnvironment
from ..symbolic.data_conditions import DATE_ATTRIBUTE

ALL_TEMPLATES = sorted(UNARY_TEMPLATES | BINARY_TEMPLATES)
_TEMPLATE_BY_KEY = {re.sub(r"[\s\-]", "", t).lower(): t for t in ALL_TEMPLATES}
_HEAD = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 \-]*?)\s*\(")
_TIME = re.compile(r"(?:\btrong\s*)?(?:<=|<)\s*(\d+)\s*(ngày\s+làm\s+việc|working\s+days?|ngày|days?|d|giờ|hours?|h|"
                   r"tuần|weeks?|tháng|months?)(?![\w])", re.IGNORECASE)
_DATE_RANGE = re.compile(r"^ngày\s*\((.+?)\)\s*trong\s*\[\s*([^,\]]+?)\s*,\s*([^\]]+?)\s*\]$", re.IGNORECASE)
_DATE_CMP = re.compile(r"^ngày\s*\((.+?)\)\s*(==|!=|<=|>=|<|>)\s*(\S+)$", re.IGNORECASE)
_ATTR_CMP = re.compile(r"^(?:[AaTt]\.)?(.+?)\s*(==|!=|<=|>=|<|>)\s*(.+)$")
_DMY = re.compile(r"^(\d{1,2})/(\d{1,2})/(năm(?:\s*[+-]\s*\d+)?|\d{4})$", re.IGNORECASE)
_CONJ = re.compile(r"\s+(?:and|và)\s+", re.IGNORECASE)
_SYMBOLS = (("->", "→"), ("=>", "→"), ("≤", "<="), ("≥", ">="), ("≠", "!="))
DAY_UNITS = {"ngày": "d", "day": "d", "days": "d", "d": "d", "giờ": "h", "hour": "h", "hours": "h", "h": "h",
             "tuần": "w", "week": "w", "weeks": "w", "tháng": "mo", "month": "mo", "months": "mo",
             "ngày làm việc": "wd", "working day": "wd", "working days": "wd"}
PRECEDENCE_SIDE = ("Precedence", "Alternate Precedence", "Chain Precedence", "Not Precedence")


class NotationError(ValueError):
    """Ký hiệu trong phiếu không chuyển được sang AST hợp lệ (cần người sửa phiếu)."""


def normalize(text: str) -> str:
    out = " ".join(str(text).replace("`", "").split())
    for old, new in _SYMBOLS:
        out = out.replace(old, new)
    return re.sub(r"(?<![=!<>])=(?!=)", "==", out)


def _key(name: str) -> str:
    return re.sub(r"\s*/\s*", " / ", " ".join(name.split())).lower()


def resolve_activity(name: str, activities: List[str]) -> str:
    by_key = {_key(a): a for a in activities}
    hit = by_key.get(_key(name))
    if hit:
        return hit
    close = difflib.get_close_matches(_key(name), list(by_key), n=3, cutoff=0.6)
    hint = f" Gần nhất: {[by_key[c] for c in close]}" if close else ""
    raise NotationError(f"Activity '{name}' không có trong log (docs/CAP_VOCABULARY.md).{hint}")


def resolve_name(name: str, activities: List[str]) -> str:
    """Một activity, hoặc nhóm '{A | B}' (cùng một bước ghi bằng activity khác nhau, VD theo năm) → dạng chuẩn."""
    return activity_group(resolve_activity(m, activities) for m in activity_members(name))


def resolve_attribute(name: str, types: Mapping[str, str]) -> str:
    name = name.strip()
    for cand in (name, f"case:{name}"):
        if cand in types:
            return cand
    close = difflib.get_close_matches(name, list(types), n=3, cutoff=0.6)
    raise NotationError(f"Thuộc tính '{name}' không có trong Γ.{' Gần nhất: ' + str(close) if close else ''}")


def parse_value(raw: str, attr_type: Optional[str]) -> Any:
    """Giá trị theo kiểu của thuộc tính trong Γ ('0,3' → 0.3; True/False; chuỗi bỏ nháy)."""
    raw = raw.strip().strip("\"'")
    if attr_type == "Boolean":
        if raw.lower() not in ("true", "false"):
            raise NotationError(f"Thuộc tính Boolean cần True/False, gặp '{raw}'")
        return raw.lower() == "true"
    if attr_type in ("Float", "Integer"):
        try:
            return float(raw.replace(",", "."))
        except ValueError as exc:
            raise NotationError(f"Thuộc tính số cần giá trị số, gặp '{raw}'") from exc
    return raw


def parse_date(raw: str) -> str:
    """'15/05/năm' → 'year-05-15'; '30/06/năm+1' → 'year+1-06-30'; '15/05/2016' → '2016-05-15'."""
    m = _DMY.match(raw.strip())
    if not m:
        raise NotationError(f"Ngày '{raw}' không đúng dạng DD/MM/năm, DD/MM/năm+1 hoặc DD/MM/YYYY")
    day, month, year = int(m.group(1)), int(m.group(2)), re.sub(r"\s", "", m.group(3)).lower()
    if not (1 <= day <= 31 and 1 <= month <= 12):
        raise NotationError(f"Ngày '{raw}' ngoài phạm vi")
    year = year.replace("năm", "year")
    if year == "year+0":
        year = "year"
    return f"{year}-{month:02d}-{day:02d}"


def _split_head(text: str) -> Tuple[str, str, str]:
    """→ (template, phần trong ngoặc, phần còn lại). Đếm ngoặc cân bằng (tên activity có thể chứa ngoặc)."""
    m = _HEAD.match(text)
    if not m:
        raise NotationError(f"Không nhận ra mẫu DECLARE ở đầu '{text}'")
    template = _TEMPLATE_BY_KEY.get(re.sub(r"[\s\-]", "", m.group(1)).lower())
    if template is None:
        raise NotationError(f"Mẫu '{m.group(1)}' không thuộc {ALL_TEMPLATES}")
    depth, start = 0, m.end() - 1
    for i in range(start, len(text)):
        depth += (text[i] == "(") - (text[i] == ")")
        if depth == 0:
            return template, text[start + 1:i], text[i + 1:]
    raise NotationError(f"Thiếu dấu ')' trong '{text}'")


def _take_time(rest: str) -> Tuple[Optional[int], Optional[str], str]:
    """Thời hạn giữ ĐÚNG đơn vị của luật (tháng lịch 'mo', tuần 'w', ngày làm việc 'wd') — không quy đổi (mục 7)."""
    found = list(_TIME.finditer(rest))
    strict = [m for m in found if re.search(r"<(?!=)", m.group(0))]
    if strict:  # rà soát 2026-11-18 E-M6: '< N' từng bị lưu thành time_max = N (tức ≤ N)
        raise NotationError(f"Thời hạn '{strict[0].group(0).strip()}' dùng '<': ghi rõ '<= N' (chậm nhất N) cho "
                            "đúng ý luật")
    if len(found) > 1:
        raise NotationError(f"Có nhiều hơn một thời hạn trong '{rest}'")
    if not found:
        return None, None, rest
    m = found[0]
    return int(m.group(1)), DAY_UNITS[" ".join(m.group(2).lower().split())], rest[:m.start()] + rest[m.end():]


def _condition_segments(rest: str) -> List[str]:
    rest = rest.strip()
    rest = re.sub(r"^(?:\|\s*)?với\s+", "", rest, flags=re.IGNORECASE)
    parts = [p for seg in re.split(r"\s*\|\s*|\s+với\s+", rest) for p in _CONJ.split(seg)]
    return [p.strip(" ,") for p in parts if p.strip(" ,")]


def _parse_condition(seg: str, activation: str, types: Mapping[str, str],
                     activities: List[str]) -> List[Tuple[str, str, Any]]:
    m = _DATE_RANGE.match(seg)
    if m:
        _date_subject(m.group(1), activation, activities)
        return [(DATE_ATTRIBUTE, ">=", parse_date(m.group(2))), (DATE_ATTRIBUTE, "<=", parse_date(m.group(3)))]
    m = _DATE_CMP.match(seg)
    if m:
        _date_subject(m.group(1), activation, activities)
        return [(DATE_ATTRIBUTE, m.group(2), parse_date(m.group(3)))]
    m = _ATTR_CMP.match(seg)
    if not m:
        raise NotationError(f"Không hiểu điều kiện '{seg}'")
    attr = resolve_attribute(m.group(1), types)
    return [(attr, m.group(2), parse_value(m.group(3), types.get(attr)))]


def _date_subject(name: str, activation: str, activities: List[str]) -> None:
    if resolve_name(name, activities) != activation:
        raise NotationError(f"ngày({name}): chỉ hỗ trợ ngày của activity kích hoạt '{activation}'")


def _attribute_types(gamma: Mapping[str, Any]) -> Dict[str, str]:
    return {k: v["type"] for k, v in {**gamma["case_attributes"], **gamma["event_attributes"]}.items()}


def notation_to_ast(notation: str, gamma: Mapping[str, Any], article_id: str) -> Dict[str, Any]:
    """Một ràng buộc dạng phiếu → AST dict đã qua Tầng 1 và Tầng 2 (Γ). Sai → NotationError."""
    text = normalize(notation)
    activities = list(gamma["valid_activities"])
    template, inside, rest = _split_head(text)
    names = [p.strip() for p in inside.split("→")]
    if len(names) > 2 or not all(names):
        raise NotationError(f"Cặp activity không hợp lệ trong '{inside}'")
    acts = [resolve_name(n, activities) for n in names]
    time_max, unit, rest = _take_time(rest)
    types = _attribute_types(gamma)
    # Điều kiện thuộc sự kiện KÍCH HOẠT: B với họ Precedence (chuẩn Declare4Py, F-PREC), A với các mẫu khác
    activation = acts[1] if template in PRECEDENCE_SIDE and len(acts) == 2 else acts[0]
    conds = [c for seg in _condition_segments(rest) for c in _parse_condition(seg, activation, types, activities)]
    ast = {"article_id": article_id, "template_name": template, "activation_activity": acts[0],
           "target_activity": acts[1] if len(acts) == 2 else None,
           "activation_attr": None, "activation_op": None, "activation_val": None, "extra_conditions": [],
           "time_min": 0, "time_max": time_max, "time_unit": unit or "d"}
    if conds:
        ast.update(activation_attr=conds[0][0], activation_op=conds[0][1], activation_val=conds[0][2],
                   extra_conditions=[{"attr": a, "op": o, "val": v} for a, o, v in conds[1:]])
    return _validated(ast, gamma)


def _validated(ast: Dict[str, Any], gamma: Mapping[str, Any]) -> Dict[str, Any]:
    ok, res = validate_layer1_ast(ast)
    if not ok:
        raise NotationError(f"Tầng 1: {res}")
    ok, err = ProcessTypingEnvironment(dict(gamma)).validate_ast(res)
    if not ok:
        raise NotationError(f"Tầng 2 (Γ): {err}")
    return res.model_dump(exclude={"decomposition"})
