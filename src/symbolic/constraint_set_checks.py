"""
Kiểm TẬP ràng buộc đã qua kiểm (sau Tầng 1–3 + kiểm trên log): mâu thuẫn và trùng lặp giữa các cặp ràng buộc.
Từng ràng buộc riêng lẻ đã được kiểm; phần này bắt lỗi chỉ lộ ra khi đặt chúng cạnh nhau (VD Existence(A) từ khoản
này và Absence(A) từ khoản khác). Chỉ BÁO CÁO cho người xem — không xoá ràng buộc nào.

Phương pháp (2026-11-20): mỗi mẫu DECLARE = một automat hữu hạn tất định (DFA) trên bảng chữ cái = các activity của
cặp (tách biến thể theo đúng/sai của từng điều kiện dữ liệu trên activity đó) + 1 ký hiệu 'activity khác'; duyệt MỌI
trạng thái đến được của tích hai DFA → kết luận CHÍNH XÁC cho mọi độ dài vết (trước đây: duyệt vết ≤ 5).
`_holds` (ngữ nghĩa LTLf theo định nghĩa) giữ lại làm chuẩn: test đối chiếu DFA với `_holds` trên mọi vết ngắn.

  CONFLICT               không vết nào thoả cả hai (mọi hồ sơ vi phạm ít nhất một)
  CONFLICT_IF_ACTIVATED  thoả được cả hai CHỈ khi ràng buộc hai ngôi không được kích hoạt (VD Response(A,B) và
                         Not Response(A,B): hồ sơ nào có A là vi phạm một trong hai)
  IMPLIES                a ⇒ b trên mọi vết (b thừa khi đã có a) — chỉ xét cặp không có thời hạn
  DUPLICATE              cùng dòng .decl (thường là nhất quán: hai khoản cùng dẫn tới một luật)

AN TOÀN (không bịa mâu thuẫn): (1) mọi tổ hợp đúng/sai của các điều kiện đều coi là có thể xảy ra (thừa vết →
chỉ có thể bỏ sót mâu thuẫn); (2) thời hạn của mẫu khẳng định (Response …) được bỏ → ràng buộc YẾU đi, mâu thuẫn tìm
được vẫn là mâu thuẫn thật. (3) Mẫu phủ định có thời hạn (Not Response(A,B) ≤ t …): khi bỏ thời gian, MỌI vết đều
thoả được nó (giãn các sự kiện xa nhau) → không thể chứng minh mâu thuẫn nếu không suy luận thời gian. Trường hợp
chứng minh được bằng khoảng thời gian và được xét: Response(A,B) ≤ t1 với Not Response(A,B) ≤ t2, cùng A, B, cùng điều
kiện, cùng đơn vị cố định, thời hạn bắt đầu từ 0, t1 ≤ t2 → B phải đến trong t1 nhưng bị cấm trong t2 →
CONFLICT_IF_ACTIVATED. Các cặp có mẫu phủ định có thời hạn khác: bỏ qua.
"""

import itertools
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterator, List, Mapping, Optional, Sequence, Tuple

from ..mde.constraint_ast import UNARY_TEMPLATES, DeclareConstraintAST, activity_members, format_condition

MAX_LEN = 5  # chỉ còn dùng cho _traces (test đối chiếu) — kiểm cặp dùng DFA, không giới hạn độ dài
METHOD = "LTLf -> DFA, tích automat, chính xác mọi độ dài vết"
FIXED_UNITS = {"s", "m", "h", "d", "w"}  # đơn vị độ dài cố định (tháng, ngày làm việc: không so được chặt)
CHOICE_FAMILY = {"Choice", "Exclusive Choice"}  # engine áp điều kiện cho CẢ A và B (declare4py_verifier)
PRECEDENCE_FAMILY = {"Precedence", "Alternate Precedence", "Chain Precedence", "Not Precedence"}
NEGATIVE = {"Absence", "Not Responded Existence", "Not Response", "Not Precedence", "Not Co-Existence"}

Symbol = Tuple[str, Tuple[bool, ...]]  # (activity, giá trị đúng/sai của từng điều kiện đặt trên activity đó)
Trace = Tuple[Symbol, ...]
OTHER: Symbol = ("__other__", ())


@dataclass(frozen=True)
class Spec:
    clause: str
    decl: str
    template: str
    act: FrozenSet[str]
    tgt: FrozenSet[str]
    cond: str  # '' = không điều kiện
    cond_side: str  # 'act' | 'tgt' (họ Precedence: trên B) | 'both' (Choice, Exclusive Choice) — như engine
    timed: bool
    window: Optional[Tuple[int, int, str]] = None  # (time_min, time_max, đơn vị) nếu có thời hạn


def _condition(model: DeclareConstraintAST) -> str:
    """Điều kiện dạng chuẩn (như phần thứ 2 của dòng .decl) — dựng từ AST, KHÔNG tách dòng .decl theo '|' vì tên
    nhóm activity '{A | B}' cũng chứa '|'."""
    if not model.activation_attr:
        return ""
    parts = [format_condition(model.activation_attr, model.activation_op, model.activation_val)]
    return " and ".join(parts + [format_condition(c.attr, c.op, c.val) for c in model.extra_conditions])


def _cond_side(tpl: str) -> str:
    return "tgt" if tpl in PRECEDENCE_FAMILY else "both" if tpl in CHOICE_FAMILY else "act"


def make_spec(clause: str, ast: Mapping[str, Any]) -> Spec:
    model = DeclareConstraintAST.model_validate(dict(ast))
    tpl = model.template_name
    window = (model.time_min or 0, model.time_max, model.time_unit or "d") if model.time_max is not None else None
    return Spec(clause, model.to_declare4py_line().strip(), tpl, activity_members(model.activation_activity),
                activity_members(model.target_activity) if model.target_activity else frozenset(),
                _condition(model), _cond_side(tpl), model.time_max is not None, window)


# ------------------------------------------------------------------- ngữ nghĩa DECLARE (LTLf trên vết hữu hạn)


def _positions(s: Spec, trace: Trace, side: str, ci: Mapping[Tuple[str, str], int]) -> List[int]:
    acts = s.act if side == "act" else s.tgt
    conditioned = bool(s.cond) and s.cond_side in (side, "both")
    return [i for i, (act, bits) in enumerate(trace)
            if act in acts and (not conditioned or bits[ci[(act, s.cond)]])]


def _next_after(items: Sequence[int], i: int, default: int) -> int:
    return min((k for k in items if k > i), default=default)


def _holds(s: Spec, trace: Trace, ci: Mapping[Tuple[str, str], int]) -> bool:
    a, b = _positions(s, trace, "act", ci), _positions(s, trace, "tgt", ci)
    ar = [i for i, (act, _) in enumerate(trace) if act in s.act]
    br = [i for i, (act, _) in enumerate(trace) if act in s.tgt]
    rules = {
        "Existence": lambda: bool(a),
        "Absence": lambda: not a,
        "Exactly1": lambda: len(a) == 1,
        "Init": lambda: 0 in a,
        "Choice": lambda: bool(a or b),
        "Exclusive Choice": lambda: bool(a or b) and not (a and b),
        "Responded Existence": lambda: not a or bool(b),
        "Not Responded Existence": lambda: not (a and b),
        "Not Co-Existence": lambda: not (a and b),
        "Response": lambda: all(any(j > i for j in b) for i in a),
        # Alternate: engine ngắt ở A / B BẤT KỲ (không xét điều kiện) — ar / br = vị trí không kèm điều kiện
        "Alternate Response": lambda: all(any(i < j < _next_after(ar, i, len(trace)) for j in b) for i in a),
        "Chain Response": lambda: all(i + 1 in b for i in a),
        "Precedence": lambda: all(any(i < j for i in a) for j in b),
        "Alternate Precedence": lambda: all(any(max((k for k in br if k < j), default=-1) < i < j for i in a)
                                            for j in b),
        "Chain Precedence": lambda: all(j - 1 in a for j in b),
        "Not Response": lambda: not any(j > i for i in a for j in b),
        "Not Precedence": lambda: not any(i < j for i in a for j in b),
    }
    if s.template not in rules:
        raise ValueError(f"mẫu chưa hỗ trợ: {s.template}")
    return rules[s.template]()


def _activated(s: Spec, trace: Trace, ci: Mapping[Tuple[str, str], int]) -> bool:
    """Ràng buộc hai ngôi có sự kiện kích hoạt (họ Precedence: kích hoạt bởi B); một ngôi luôn coi là kích hoạt."""
    if s.template in UNARY_TEMPLATES:
        return True
    return bool(_positions(s, trace, "tgt" if s.template in PRECEDENCE_FAMILY else "act", ci))


def _alphabet(specs: Sequence[Spec]) -> Tuple[List[Symbol], Dict[Tuple[str, str], int]]:
    """Mỗi activity × mọi tổ hợp đúng/sai của các điều kiện đặt trên nó (thừa tổ hợp → an toàn) + 'khác'."""
    conds: Dict[str, List[str]] = {}
    for s in specs:
        on_side = {"act": s.act, "tgt": s.tgt, "both": s.act | s.tgt}[s.cond_side]
        for act in sorted(s.act | s.tgt):
            conds.setdefault(act, [])
            if s.cond and act in on_side and s.cond not in conds[act]:
                conds[act].append(s.cond)
    symbols: List[Symbol] = [OTHER]
    index: Dict[Tuple[str, str], int] = {}
    for act, cs in sorted(conds.items()):
        index.update({(act, c): i for i, c in enumerate(cs)})
        symbols += [(act, bits) for bits in itertools.product((True, False), repeat=len(cs))]
    return symbols, index


def _traces(symbols: Sequence[Symbol], max_len: int) -> Iterator[Trace]:
    for n in range(max_len + 1):
        yield from itertools.product(symbols, repeat=n)


def _weaken(s: Spec) -> Optional[Spec]:
    """Bỏ thời hạn của mẫu khẳng định (ràng buộc yếu đi → mâu thuẫn tìm được vẫn đúng); phủ định có hạn → None."""
    if not s.timed:
        return s
    if s.template in NEGATIVE:
        return None
    return Spec(s.clause, s.decl, s.template, s.act, s.tgt, s.cond, s.cond_side, False)


# ------------------------------------------------------------------- DFA của từng mẫu (chính xác, mọi độ dài)
# Trạng thái: giá trị nhỏ bất biến; None = trạng thái chết (đã vi phạm, không cứu được). Mỗi bước nhận (a, b) = ký hiệu
# hiện tại thuộc phía kích hoạt / phía đích (đã xét điều kiện). Khớp từng chữ với `_holds` (tests đối chiếu).

_PAIR = ("Choice", "Exclusive Choice", "Responded Existence", "Not Responded Existence", "Not Co-Existence")
_INIT = {"Existence": False, "Absence": True, "Exactly1": 0, "Init": "start", "Response": False,
         "Alternate Response": False, "Chain Response": False, "Precedence": False, "Alternate Precedence": False,
         "Chain Precedence": False, "Not Response": False, "Not Precedence": False}


def _sides(s: Spec, sym: Symbol, ci: Mapping[Tuple[str, str], int]) -> Tuple[bool, bool, bool, bool]:
    """(a, b, ar, br) cho một ký hiệu."""
    return (_is_side(s, sym, "act", ci), _is_side(s, sym, "tgt", ci), sym[0] in s.act, sym[0] in s.tgt)


def _is_side(s: Spec, sym: Symbol, side: str, ci: Mapping[Tuple[str, str], int]) -> bool:
    act, bits = sym
    acts = s.act if side == "act" else s.tgt
    conditioned = bool(s.cond) and s.cond_side in (side, "both")
    return act in acts and (not conditioned or bits[ci[(act, s.cond)]])


def _init(tpl: str) -> Any:
    if tpl in _PAIR:
        return (False, False)
    if tpl not in _INIT:
        raise ValueError(f"mẫu chưa hỗ trợ: {tpl}")
    return _INIT[tpl]


def _step(tpl: str, q: Any, a: bool, b: bool, ar: Optional[bool] = None, br: Optional[bool] = None) -> Any:
    """a, b: ký hiệu thuộc phía A / B (đã xét điều kiện); ar, br: thuộc A / B KHÔNG xét điều kiện (biên ngắt của họ
    Alternate, như engine). Mặc định ar = a, br = b."""
    ar = a if ar is None else ar
    br = b if br is None else br
    if q is None:
        return None
    if tpl in _PAIR:
        return (q[0] or a, q[1] or b)
    if tpl == "Existence":
        return q or a
    if tpl == "Absence":
        return None if a else q
    if tpl == "Exactly1":
        return None if (a and q == 1) else (q + 1 if a else q)
    if tpl == "Init":
        return q if q != "start" else ("ok" if a else None)
    if tpl == "Response":  # q = còn A chờ B (B ở cùng vị trí đáp ứng A trước đó, không đáp ứng chính nó)
        return a or (q and not b)
    if tpl == "Alternate Response":  # A (bất kỳ) mới đến khi A cũ chưa được đáp ứng (B cùng vị trí không tính) → chết
        if ar and q:
            return None
        return a or (q and not b)
    if tpl == "Chain Response":  # q = ký hiệu trước là A
        return None if (q and not b) else a
    if tpl == "Precedence":  # q = đã gặp A ở vị trí trước
        return None if (b and not q) else (q or a)
    if tpl == "Alternate Precedence":  # q = có A kể từ B (bất kỳ) gần nhất (A cùng vị trí với B không tính)
        if b and not q:
            return None
        return False if br else (q or a)
    if tpl == "Chain Precedence":  # q = ký hiệu trước là A
        return None if (b and not q) else a
    if tpl in ("Not Response", "Not Precedence"):  # q = đã gặp A ở vị trí trước
        return None if (b and q) else (q or a)
    raise ValueError(f"mẫu chưa hỗ trợ: {tpl}")


def _accept(tpl: str, q: Any) -> bool:
    if q is None:
        return False
    if tpl in _PAIR:
        a, b = q
        return {"Choice": a or b, "Exclusive Choice": a != b, "Responded Existence": (not a) or b,
                "Not Responded Existence": not (a and b), "Not Co-Existence": not (a and b)}[tpl]
    if tpl == "Existence":
        return bool(q)
    if tpl == "Exactly1":
        return q == 1
    if tpl == "Init":
        return q == "ok"
    if tpl in ("Response", "Alternate Response", "Chain Response"):
        return not q
    return True  # Absence, họ Precedence, Not Response / Not Precedence: chưa chết là thoả


def accepts(s: Spec, trace: Trace, ci: Mapping[Tuple[str, str], int]) -> bool:
    """DFA của s chấp nhận vết (dùng để đối chiếu với `_holds` trong test)."""
    q = _init(s.template)
    for sym in trace:
        q = _step(s.template, q, *_sides(s, sym, ci))
    return _accept(s.template, q)


def _reachable(specs: Sequence[Spec], symbols: Sequence[Symbol], ci: Mapping[Tuple[str, str], int]) -> set:
    """Mọi trạng thái đến được của tích các DFA, kèm cờ 'đã kích hoạt' của từng ràng buộc (một ngôi: luôn True)."""
    start = tuple((_init(s.template), s.template in UNARY_TEMPLATES) for s in specs)
    seen, frontier = {start}, [start]
    while frontier:
        state = frontier.pop()
        for sym in symbols:
            nxt = []
            for s, (q, fired) in zip(specs, state, strict=True):
                a, b, ar, br = _sides(s, sym, ci)
                trig = b if s.template in PRECEDENCE_FAMILY else a
                nxt.append((_step(s.template, q, a, b, ar, br), fired or trig))
            nxt_t = tuple(nxt)
            if nxt_t not in seen:
                seen.add(nxt_t)
                frontier.append(nxt_t)
    return seen


def _timed_window_conflict(a: Spec, b: Spec) -> bool:
    """Response(A,B) ≤ t1 và Not Response(A,B) ≤ t2 (cùng A, B, điều kiện, đơn vị cố định, bắt đầu 0), t1 ≤ t2."""
    for x, y in ((a, b), (b, a)):
        if x.template != "Response" or y.template != "Not Response" or not x.window or not y.window:
            continue
        same = (x.act, x.tgt, x.cond) == (y.act, y.tgt, y.cond)
        unit_ok = x.window[2] == y.window[2] and x.window[2] in FIXED_UNITS
        if same and unit_ok and x.window[0] == 0 and y.window[0] == 0 and x.window[1] <= y.window[1]:
            return True
    return False


def check_pair(a: Spec, b: Spec, max_len: int = MAX_LEN) -> Optional[Dict[str, Any]]:
    """Một phát hiện cho cặp (a, b), hoặc None. Chính xác (tích DFA); `max_len` giữ cho tương thích, không dùng."""
    base = {"a": a.clause, "b": b.clause, "decl_a": a.decl, "decl_b": b.decl}
    if a.decl == b.decl:
        return {**base, "kind": "DUPLICATE", "note": "cùng dòng .decl"}
    if not (a.act | a.tgt) & (b.act | b.tgt) and not (a.template == b.template == "Init"):
        return None  # không chung activity → độc lập, trừ hai Init (cùng đòi vị trí đầu tiên)
    if _timed_window_conflict(a, b):
        return {**base, "kind": "CONFLICT_IF_ACTIVATED",
                "note": "B phải đến trong thời hạn của Response nhưng bị Not Response cấm trong khoảng dài hơn"}
    wa, wb = _weaken(a), _weaken(b)
    if wa is None or wb is None:
        return None  # mẫu phủ định có thời hạn: không chứng minh được mâu thuẫn nếu bỏ thời gian (xem đầu file)
    symbols, ci = _alphabet([wa, wb])
    states = _reachable([wa, wb], symbols, ci)
    both = [st for st in states if _accept(wa.template, st[0][0]) and _accept(wb.template, st[1][0])]
    if not both:
        return {**base, "kind": "CONFLICT", "note": "không vết nào (mọi độ dài) thoả cả hai"}
    if not any(st[0][1] and st[1][1] for st in both):
        return {**base, "kind": "CONFLICT_IF_ACTIVATED",
                "note": "chỉ thoả cả hai khi ràng buộc hai ngôi không được kích hoạt"}
    if a.timed or b.timed:
        return None  # kéo theo cần ngữ nghĩa thời hạn chính xác — không xét
    for x, y, i, j in ((a, b, 0, 1), (b, a, 1, 0)):
        if not any(_accept(x.template, st[i][0]) and not _accept(y.template, st[j][0]) for st in states):
            return {"a": x.clause, "b": y.clause, "decl_a": x.decl, "decl_b": y.decl, "kind": "IMPLIES",
                    "note": "a ⇒ b trên mọi vết (mọi độ dài)"}
    return None


def check_constraint_set(rules: Mapping[str, Mapping[str, Any]], max_len: int = MAX_LEN) -> List[Dict[str, Any]]:
    """rules: khoản → AST (dict). Trả mọi phát hiện giữa các cặp khoản, thứ tự ổn định."""
    specs = [make_spec(c, ast) for c, ast in sorted(rules.items())]
    found = [check_pair(x, y, max_len) for x, y in itertools.combinations(specs, 2)]
    return [f for f in found if f]
