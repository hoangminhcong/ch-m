"""
M8 — biên dịch AST ràng buộc DECLARE → truy vấn Cypher trên ĐỒ THỊ SỰ KIỆN trong Neo4j (2026-11-20).

Đồ thị sự kiện (src/kg/event_graph.py; nạp + đối chiếu với engine: scripts/verify_cypher_compiler.py):
  (:EvCase {id, <thuộc tính hồ sơ, tên gốc như 'case:young farmer'>})-[:HAS_EVENT]->(:Ev {idx, activity, ts, day, ...})
  idx = thứ tự event trong hồ sơ (như engine: sắp theo thời gian, ổn định); ts = giây epoch; day = NGÀY ĐỊA PHƯƠNG
  (múi giờ của engine, Europe/Berlin) — tính sẵn lúc nạp bằng đúng phép tính của engine.

Ngữ nghĩa: dựng lại TỪNG NHÁNH của engine (`Declare4Py._check_single_trace`, `time_windows.within`):
  a / b   vị trí event thuộc phía A / B CÓ xét điều kiện (Response…: điều kiện trên A; họ Precedence: trên B;
          Choice / Exclusive Choice: trên cả hai); a0 / b0 KHÔNG xét điều kiện (biên ngắt của họ Alternate)
  W(x,y)  cửa sổ thời gian giữa event sớm x và muộn y:
          d / w / mo với calendar_periods (CAP — Quy định 1182/71): ngày(y) ∈ [ngày(x)+lo, dời_cuối_tuần(ngày(x)+hi)]
          s / m / h (hoặc d / w khi không calendar_periods): lo·k ≤ ts(y) − ts(x) ≤ hi·k
          wd: số ngày Thứ Hai–Thứ Sáu trong [bắt_đầu, ngày(y)), bắt_đầu = ngày(x) lùi về Thứ Sáu nếu là cuối tuần
  Mẫu không có thời gian trong engine (Existence, Absence, Choice, Not Co-Existence…) bỏ qua cửa sổ, như engine.
Điều kiện dữ liệu đọc bằng ĐÚNG bộ đọc của engine (data_conditions): tra event trước rồi hồ sơ (cả tên 'case:'); thiếu
giá trị → sai; '==' với số so được với chuỗi số; bool theo chuỗi 'true'; 'date' so ngày địa phương với
date(năm hồ sơ + lệch, tháng, ngày).

KHÔNG hỗ trợ (báo UnsupportedConstraint, không dịch sai): 'mo' khi không calendar_periods; điều kiện ngày 29/02.
"""

import re
from dataclasses import dataclass
from typing import Any, Callable, List, Mapping, Tuple

from ..mde.constraint_ast import DeclareConstraintAST, activity_members
from ..symbolic.constraint_set_checks import CHOICE_FAMILY, PRECEDENCE_FAMILY
from ..symbolic.data_conditions import _CLAUSE, DATE_ATTRIBUTE, DATE_VALUE, DEFAULT_YEAR_ATTR, _parse_value, split_conjunction
from ..symbolic.time_windows import CALENDAR_PERIOD_UNITS, FIXED_SECONDS, TimeWindow, parse_time_window

CASE_LABEL = "EvCase"
EVENT_LABEL = "Ev"
HAS_EVENT = "HAS_EVENT"
_DECL = re.compile(r"^([^\[]+)\[(.*?)\]\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*)$")  # như Declare4Py.parse_decl_lines


class UnsupportedConstraint(ValueError):
    """Ràng buộc có thành phần chưa dịch được đúng ngữ nghĩa sang Cypher."""


@dataclass(frozen=True)
class CompiledConstraint:
    decl: str
    cypher: str  # trả về case_id, activated (bool), violated (bool) cho MỌI hồ sơ


def _lit(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(float(v))
    return "'" + str(v).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _value(attr: str, event: str) -> str:
    """Như data_conditions.lookup: event trước, rồi hồ sơ; thử cả 'case:<attr>' cho tên rút gọn."""
    names = [attr] if attr.startswith("case:") else [attr, f"case:{attr}"]
    return "coalesce(" + ", ".join([f"{event}[{_lit(n)}]" for n in names] + [f"c[{_lit(n)}]" for n in names]) + ")"


def _date_clause(op: str, raw: str, event: str) -> str:
    m = DATE_VALUE.match(raw.strip("\"'"))
    if not m:
        raise UnsupportedConstraint(f"giá trị ngày không đọc được: {raw!r}")
    year_spec, month, day = m.group(1), int(m.group(2)), int(m.group(3))
    if (month, day) == (2, 29):
        raise UnsupportedConstraint("điều kiện ngày 29/02 (engine coi năm không nhuận là sai) chưa dịch")
    if year_spec.startswith("year"):
        offset = int(year_spec[4:] or 0)
        year = f"(toInteger(toFloat(toString({_value(DEFAULT_YEAR_ATTR, event)}))) + {offset})"
    else:
        year = str(int(year_spec))
    target = f"date({{year: {year}, month: {month}, day: {day}}})"
    cy_op = {"==": "=", "!=": "<>"}.get(op, op)
    # CASE (không dùng AND): Cypher không bảo đảm dừng sớm, date({year: null}) phải không bao giờ được tính
    return f"(CASE WHEN {event}.day IS NULL OR {year} IS NULL THEN false ELSE {event}.day {cy_op} {target} END)"


def _clause(raw_clause: str, event: str) -> str:
    m = _CLAUSE.match(raw_clause.strip())
    if not m:
        raise UnsupportedConstraint(f"điều kiện không đọc được: {raw_clause!r}")
    attr, op, raw = m.group(1).strip(), m.group(2), m.group(3).strip()
    if attr == DATE_ATTRIBUTE:
        return _date_clause(op, raw, event)
    target = _parse_value(raw)
    v = _value(attr, event)
    neg = "NOT " if op == "!=" else ""
    if isinstance(target, bool):
        if op not in ("==", "!="):
            return "false"
        return f"({v} IS NOT NULL AND {neg}((toLower(toString({v})) = 'true') = {_lit(target)}))"
    if op in ("==", "!="):
        eq = f"{v} = {_lit(target)}"
        if isinstance(target, float):
            eq = f"({eq} OR toFloatOrNull(toString({v})) = {_lit(target)})"
        return f"({v} IS NOT NULL AND {neg}({eq}))"
    if not isinstance(target, float):
        raise UnsupportedConstraint(f"so sánh thứ tự với giá trị không phải số: {raw_clause!r}")
    return f"({v} IS NOT NULL AND toFloatOrNull(toString({v})) {op} {_lit(target)})"


def _condition_expr(cond: str, event: str) -> str:
    return " AND ".join(_clause(c, event) for c in split_conjunction(cond)) if cond else "true"


def _side_list(acts: frozenset, cond: str) -> str:
    """Vị trí event (0-based) có activity thuộc acts và thoả điều kiện cond (dạng .decl, rỗng = không điều kiện)."""
    names = "[" + ", ".join(_lit(a) for a in sorted(acts)) + "]"
    return f"[i IN range(0, size(ev) - 1) WHERE ev[i].activity IN {names} AND {_condition_expr(cond, 'ev[i]')}]"


# ---------------------------------------------------------------------------------------------- cửa sổ thời gian


def _roll_weekend(d: str) -> str:
    return f"({d} + duration({{days: CASE {d}.dayOfWeek WHEN 6 THEN 2 WHEN 7 THEN 1 ELSE 0 END}}))"


def _busdays(x: str, y: str) -> str:
    """np.busday_count(busday_offset(ngày(x), 0, roll='backward'), ngày(y)) — ngày(y) ≥ ngày(x)."""
    start = (f"({x}.day - duration({{days: CASE {x}.day.dayOfWeek WHEN 6 THEN 1 WHEN 7 THEN 2 ELSE 0 END}}))")
    days = f"duration.inDays({start}, {y}.day).days"
    return (f"(({days}) / 7 * 5 + size([k IN range(0, ({days}) % 7 - 1) "
            f"WHERE ({start}.dayOfWeek - 1 + k) % 7 < 5]))")


def _window(w: TimeWindow, calendar_periods: bool) -> Callable[[str, str], str]:
    """Hàm (event sớm, event muộn) → biểu thức Cypher 'nằm trong cửa sổ', như time_windows.within."""
    if calendar_periods and w.unit in CALENDAR_PERIOD_UNITS:
        lo, hi = int(w.lo), int(w.hi)

        def add(d: str, n: int) -> str:
            return f"({d} + duration({{{'months' if w.unit == 'mo' else 'days'}: {n * (7 if w.unit == 'w' else 1)}}}))"

        return lambda x, y: f"({add(f'{x}.day', lo)} <= {y}.day AND {y}.day <= {_roll_weekend(add(f'{x}.day', hi))})"
    if w.unit in FIXED_SECONDS:
        k = FIXED_SECONDS[w.unit]
        return lambda x, y: f"({w.lo * k!r} <= {y}.ts - {x}.ts AND {y}.ts - {x}.ts <= {w.hi * k!r})"
    if w.unit == "wd":
        return lambda x, y: f"({w.lo!r} <= {_busdays(x, y)} AND {_busdays(x, y)} <= {w.hi!r})"
    raise UnsupportedConstraint(f"đơn vị thời gian '{w.unit}' khi không tính theo lịch chưa dịch sang Cypher")


def _holds(tpl: str, win: Callable[[int, int], str]) -> str:
    """Điều kiện THOẢ của engine cho từng mẫu; win(i, j) = cửa sổ giữa ev[i] (sớm) và ev[j] (muộn)."""
    rules = {
        "Existence": "size(a) > 0",
        "Absence": "size(a) = 0",
        "Exactly1": "size(a) = 1",
        "Init": "0 IN a",
        "Choice": "(size(a) > 0 OR size(b) > 0)",
        "Exclusive Choice": "((size(a) > 0) <> (size(b) > 0))",
        "Not Responded Existence": "NOT (size(a) > 0 AND size(b0) > 0)",
        "Not Co-Existence": "NOT (size(a) > 0 AND size(b0) > 0)",
        "Responded Existence": f"all(i IN a WHERE any(j IN b0 WHERE CASE WHEN j < i THEN {win('j', 'i')} "
                               f"ELSE {win('i', 'j')} END))",
        "Response": f"all(i IN a WHERE any(j IN b0 WHERE j > i AND {win('i', 'j')}))",
        "Alternate Response": (f"all(i IN a WHERE any(j IN b0 WHERE j > i AND "
                               f"j < coalesce(head([k IN a0 WHERE k > i]), size(ev)) AND {win('i', 'j')}))"),
        "Chain Response": f"all(i IN a WHERE (i + 1) IN b0 AND {win('i', 'i + 1')})",
        "Precedence": f"all(j IN b WHERE any(i IN a0 WHERE i < j AND {win('i', 'j')}))",
        "Alternate Precedence": (f"all(j IN b WHERE any(i IN a0 WHERE i < j AND "
                                 f"i > coalesce(last([k IN b0 WHERE k < j]), -1) AND {win('i', 'j')}))"),
        "Chain Precedence": f"all(j IN b WHERE (j - 1) IN a0 AND {win('j - 1', 'j')})",
        "Not Precedence": f"NOT any(j IN b WHERE any(i IN a0 WHERE i < j AND {win('i', 'j')}))",
        "Not Response": f"NOT any(i IN a WHERE any(j IN b0 WHERE j > i AND {win('i', 'j')}))",
    }
    if tpl not in rules:
        raise UnsupportedConstraint(f"mẫu chưa hỗ trợ: {tpl}")
    return rules[tpl]


def compile_constraint(ast: Mapping[str, Any], calendar_periods: bool = True) -> CompiledConstraint:
    """calendar_periods=True: thời hạn d / w / mo theo ngày lịch (Quy định 1182/71) — như engine của bộ CAP."""
    model = DeclareConstraintAST.model_validate(dict(ast))
    decl = model.to_declare4py_line().strip()
    m = _DECL.match(decl)
    if not m:
        raise UnsupportedConstraint(f"dòng .decl không đọc được: {decl}")
    tpl, cond, time_str = m.group(1).strip(), m.group(3).strip(), m.group(5).strip()
    window = parse_time_window(time_str)
    if window is None:
        win = lambda x, y: "true"  # noqa: E731
    else:
        w = _window(window, calendar_periods)
        win = lambda x, y: w(f"ev[{x}]", f"ev[{y}]")  # noqa: E731
    holds = _holds(tpl, win)
    act = activity_members(model.activation_activity)
    tgt = activity_members(model.target_activity) if model.target_activity else frozenset()
    on_target = tpl in PRECEDENCE_FAMILY
    both = tpl in CHOICE_FAMILY  # engine: điều kiện của Choice / Exclusive Choice áp cho CẢ A và B
    lists = {"a": _side_list(act, "" if on_target else cond), "a0": _side_list(act, ""),
             "b": _side_list(tgt, cond if (on_target or both) else "") if tgt else "[]",
             "b0": _side_list(tgt, "") if tgt else "[]"}
    trigger = "size(b) > 0" if on_target else ("true" if not tgt or both else "size(a) > 0")
    cypher = (f"MATCH (c:{CASE_LABEL})\n"
              f"OPTIONAL MATCH (c)-[:{HAS_EVENT}]->(x:{EVENT_LABEL})\n"
              f"WITH c, x ORDER BY x.idx\n"
              f"WITH c, [y IN collect(x) WHERE y IS NOT NULL] AS ev\n"
              f"WITH c, ev, " + ", ".join(f"{v} AS {k}" for k, v in lists.items()) + "\n"
              f"RETURN c.id AS case_id, {trigger} AS activated, NOT ({holds}) AS violated")
    _check_balanced(cypher)
    return CompiledConstraint(decl, cypher)


def _check_balanced(text: str) -> None:
    """Kiểm thô cú pháp (ngoặc cân bằng ngoài chuỗi) — lỗi dịch lộ ra ngay, không đợi Neo4j."""
    depth, quote = [], None
    pairs = {")": "(", "]": "[", "}": "{"}
    for i, ch in enumerate(text):
        if quote:
            if ch == quote and text[i - 1] != "\\":
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth.append(ch)
        elif ch in pairs:
            if not depth or depth.pop() != pairs[ch]:
                raise AssertionError(f"ngoặc lệch ở vị trí {i}")
    if depth or quote:
        raise AssertionError("ngoặc / nháy chưa đóng")


def coverage(rules: Mapping[str, Mapping[str, Any]], calendar_periods: bool = True
             ) -> Tuple[List[str], List[Tuple[str, str]]]:
    """(khoản dịch được, [(khoản, lý do) không dịch được]) — phạm vi hỗ trợ thật trên một tập luật."""
    ok, unsupported = [], []
    for nid, ast in sorted(rules.items()):
        try:
            compile_constraint(ast, calendar_periods)
            ok.append(nid)
        except UnsupportedConstraint as exc:
            unsupported.append((nid, str(exc)))
    return ok, unsupported
