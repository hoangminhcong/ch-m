"""
Chấm điểm TN5–TN8 bộ CAP: so dự đoán của hệ thống (mỗi khoản luật một kết quả) với gold đã duyệt.

Dự đoán của một khoản (`outcome`): RULE (có AST), BASELESS (hệ thống kết luận khoản không có ràng buộc kiểm được),
FAILED (hết số vòng tự sửa, không có kết quả).

So AST theo cấu trúc (không cần log — độ rỗng/vacuity đo riêng ở TN7):
  EQ            cùng mẫu, cùng cặp activity, cùng TẬP điều kiện (chính + extra), cùng thời hạn (quy về giây)
  STRENGTHENED  cùng activity, mẫu mạnh hơn trong cùng họ, hoặc thời hạn ngắn hơn
  WEAKENED      cùng activity, mẫu yếu hơn trong cùng họ, hoặc bỏ / nới thời hạn
  COND_DIFF     cùng activity và mẫu, khác điều kiện dữ liệu (chiều mạnh/yếu phụ thuộc mẫu nên không gán)
  REVERSED      đảo cặp activity, đảo cực (Not …/Absence), hoặc nhầm Precedence ↔ Response
  MISMATCH      khác activity (không phải đảo), hoặc mẫu không so được
Một khoản có nhiều gold → lấy lớp tốt nhất. Câu bẫy: đúng khi BASELESS.
"""

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..mde.constraint_ast import activity_members
from ..symbolic.time_windows import CALENDAR_UNITS, FIXED_SECONDS

RULE, BASELESS, FAILED = "RULE", "BASELESS", "FAILED"
CLASS_RANK = {"EQ": 0, "STRENGTHENED": 1, "WEAKENED": 1, "COND_DIFF": 1, "UNIT_DIFF": 1, "REVERSED": 2,
              "MISMATCH": 3}
SYMMETRIC_TEMPLATES = {"Choice", "Exclusive Choice", "Co-Existence", "Not Co-Existence"}
POSITIVE_CLASSES = list(CLASS_RANK) + ["MISSED_AS_BASELESS", "FAILED"]
TRAP_CLASSES = ["TRAP_DETECTED", "TRAP_FALSE_RULE", "TRAP_FAILED"]
UNIT_SECONDS = {**FIXED_SECONDS, "mo": 30.44 * 86400, "wd": 1.4 * 86400}  # mo, wd: gần đúng, chỉ để xếp thứ tự
HIERARCHIES = (
    ["Responded Existence", "Response", "Alternate Response", "Chain Response"],
    ["Responded Existence", "Precedence", "Alternate Precedence", "Chain Precedence"],
    ["Existence", "Exactly1"],
)


def _norm_val(val: Any) -> Any:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    try:
        return float(s)
    except ValueError:
        return s


def condition_set(ast: Mapping[str, Any]) -> frozenset:
    conds = []
    if ast.get("activation_attr"):
        conds.append((ast["activation_attr"], ast.get("activation_op"), ast.get("activation_val")))
    conds += [(c["attr"], c["op"], c["val"]) for c in ast.get("extra_conditions") or []]
    return frozenset((a.removeprefix("A.") if isinstance(a, str) else a, o, _norm_val(v)) for a, o, v in conds)


def time_seconds(ast: Mapping[str, Any]) -> Optional[float]:
    """Thời hạn quy về giây — GẦN ĐÚNG với tháng lịch / ngày làm việc (chỉ dùng để xếp chặt / lỏng)."""
    if ast.get("time_max") is None:
        return None
    return float(ast["time_max"]) * UNIT_SECONDS.get(ast.get("time_unit") or "d", 86400)


def time_exact(ast: Mapping[str, Any]) -> Optional[Tuple[float, float, str]]:
    """Khoá so EQ: (time_min, time_max, đơn vị); đơn vị cố định quy về giây, tháng lịch / ngày làm việc giữ nguyên.
    time_min (None = 0) có trong khoá — rà soát 2026-11-18 E-H3: trước đây '2..5 ngày' bằng '≤ 5 ngày'."""
    if ast.get("time_max") is None:
        return None
    unit = ast.get("time_unit") or "d"
    lo = float(ast.get("time_min") or 0)
    if unit in CALENDAR_UNITS:
        return (lo, float(ast["time_max"]), unit)
    factor = UNIT_SECONDS.get(unit, 86400)
    return (lo * factor, float(ast["time_max"]) * factor, "s")


def _negative(template: str) -> bool:
    return template.startswith("Not ") or template == "Absence"


def _template_direction(cand: str, gold: str) -> Optional[int]:
    """+1 mạnh hơn, -1 yếu hơn, 0 bằng, None không so được."""
    if cand == gold:
        return 0
    for h in HIERARCHIES:
        if cand in h and gold in h:
            return 1 if h.index(cand) > h.index(gold) else -1
    return None


def compare_ast(cand: Mapping[str, Any], gold: Mapping[str, Any]) -> str:
    # nhóm activity {A | B} so theo tập thành viên (không phụ thuộc thứ tự)
    acts_c = tuple(activity_members(a) if a else None for a in (cand["activation_activity"], cand.get("target_activity")))
    acts_g = tuple(activity_members(a) if a else None for a in (gold["activation_activity"], gold.get("target_activity")))
    if cand["template_name"] == gold["template_name"] in SYMMETRIC_TEMPLATES and acts_c == acts_g[::-1]:
        acts_c = acts_g  # đối xứng: Choice(A,B) = Choice(B,A) (rà soát 2026-11-18 E-H2)
    if acts_c != acts_g:
        return "REVERSED" if acts_c == acts_g[::-1] and acts_g[1] else "MISMATCH"
    tc, tg = cand["template_name"], gold["template_name"]
    if _negative(tc) != _negative(tg) or {tc, tg} == {"Precedence", "Response"}:
        return "REVERSED"
    direction = _template_direction(tc, tg)
    if direction is None:
        return "MISMATCH"
    if direction:
        return "STRENGTHENED" if direction > 0 else "WEAKENED"
    if condition_set(cand) != condition_set(gold):
        return "COND_DIFF"
    if time_exact(cand) == time_exact(gold):
        return "EQ"
    t_c, t_g = time_seconds(cand), time_seconds(gold)
    if t_g is None:
        return "STRENGTHENED"
    if t_c is not None and abs(t_c - t_g) < 1e-6 * max(t_g, 1.0):
        # cùng thời hạn quy đổi nhưng khác đơn vị (5 wd ~ 7 d; 30 d ~ 1 mo) hoặc khác time_min (rà soát E-M3, E-H3)
        return "UNIT_DIFF" if _time_min(cand) == _time_min(gold) else "COND_DIFF"
    return "WEAKENED" if t_c is None or t_c > t_g else "STRENGTHENED"


def _time_min(ast: Mapping[str, Any]) -> float:
    return float(ast.get("time_min") or 0)


def best_class(cand: Mapping[str, Any], golds: Sequence[Mapping[str, Any]]) -> str:
    return min((compare_ast(cand, g) for g in golds), key=CLASS_RANK.__getitem__)


def score_clause(gold_clause: Mapping[str, Any], prediction: Optional[Mapping[str, Any]]) -> str:
    outcome = prediction["outcome"] if prediction else FAILED
    if gold_clause["kind"] == "trap":
        return {BASELESS: "TRAP_DETECTED", RULE: "TRAP_FALSE_RULE"}.get(outcome, "TRAP_FAILED")
    if outcome == BASELESS:
        return "MISSED_AS_BASELESS"
    if outcome != RULE:
        return "FAILED"
    return best_class(prediction["ast"], gold_clause["gold"])


def is_correct(cls: str) -> bool:
    return cls in ("EQ", "TRAP_DETECTED")


# B1 (đăng ký bổ sung, đã duyệt 2026-11-19) — chấm theo thành phần kiểu IRAC, mức LỒNG NHAU (mức sau chỉ đạt khi mức
# trước đạt): issue = không trả BASELESS · rule = cùng mẫu DECLARE · application = cùng activity (nhóm so theo tập,
# mẫu đối xứng không theo thứ tự) · conclusion = EQ (thêm cùng điều kiện và thời hạn). Phân tích PHỤ.
COMPONENT_LEVELS = ("issue", "rule", "application", "conclusion")


def _component_depth_one(cand: Mapping[str, Any], gold: Mapping[str, Any]) -> int:
    if cand["template_name"] != gold["template_name"]:
        return 1
    cls = compare_ast(cand, gold)
    if cls in ("MISMATCH", "REVERSED"):
        return 2
    return 4 if cls == "EQ" else 3


def component_depth(gold_clause: Mapping[str, Any], prediction: Optional[Mapping[str, Any]]) -> int:
    """Số mức đạt (0–4) cho khoản positive — lấy gold khớp sâu nhất; bẫy không dùng hàm này."""
    if not prediction or prediction.get("outcome") != RULE or not prediction.get("ast"):
        return 0
    return max(_component_depth_one(prediction["ast"], g) for g in gold_clause["gold"])


def component_rates(gold_clauses: Mapping[str, Mapping[str, Any]],
                    predictions: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """Tỉ lệ khoản positive đạt từng mức (kèm Wilson 95%) và độ sâu từng khoản."""
    pos = [nid for nid, g in gold_clauses.items() if g["kind"] == "positive"]
    depth = {nid: component_depth(gold_clauses[nid], predictions.get(nid)) for nid in pos}
    out: Dict[str, Any] = {"per_clause": depth}
    for k, level in enumerate(COMPONENT_LEVELS, start=1):
        hit, n = sum(d >= k for d in depth.values()), len(depth)
        lo, hi = wilson(hit, n)
        out[level] = {"n": n, "correct": hit, "rate": round(hit / n, 4) if n else None,
                      "ci95": [round(lo, 4), round(hi, 4)]}
    return out


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Khoảng tin cậy Wilson 95% cho tỉ lệ k/n (đáng tin hơn xấp xỉ chuẩn khi n nhỏ)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def mcnemar_exact(b: int, c: int) -> float:
    """p-value hai phía của kiểm định McNemar chính xác (b = chỉ A đúng, c = chỉ B đúng)."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def _rate(classes: Iterable[str]) -> Dict[str, Any]:
    classes = list(classes)
    k, n = sum(map(is_correct, classes), 0), len(classes)
    lo, hi = wilson(k, n)
    return {"n": n, "correct": k, "rate": round(k / n, 4) if n else None, "ci95": [round(lo, 4), round(hi, 4)]}


def _counts(classes: Iterable[str], labels: Sequence[str]) -> Dict[str, int]:
    classes = list(classes)
    return {lab: classes.count(lab) for lab in labels}


def score_config(gold_clauses: Mapping[str, Mapping[str, Any]],
                 predictions: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """Chấm một cấu hình trên mọi khoản được chấm (positive + trap). Thiếu dự đoán → FAILED."""
    per = {nid: score_clause(g, predictions.get(nid)) for nid, g in gold_clauses.items()}
    pos = [nid for nid, g in gold_clauses.items() if g["kind"] == "positive"]
    traps = [nid for nid, g in gold_clauses.items() if g["kind"] == "trap"]
    tier4 = [nid for nid in pos if gold_clauses[nid]["tier4"]]
    positive = {**_rate(per[n] for n in pos), "classes": _counts((per[n] for n in pos), POSITIVE_CLASSES)}
    trap = {**_rate(per[n] for n in traps), "classes": _counts((per[n] for n in traps), TRAP_CLASSES)}
    return {
        "per_clause": per,
        "overall": _rate(per.values()),
        "balanced": balanced_rate(positive, trap),
        "positive": positive,
        "tier4": _rate(per[n] for n in tier4),
        "non_tier4": _rate(per[n] for n in pos if n not in tier4),
        "trap": trap,
        "components": component_rates(gold_clauses, predictions),
        "missing_predictions": sorted(set(gold_clauses) - set(predictions)),
    }


def balanced_rate(positive: Mapping[str, Any], trap: Mapping[str, Any]) -> Optional[float]:
    """Trung bình tỉ lệ đúng của hai loại khoản: không bị loại chiếm đa số (bẫy) thổi phồng. Thiếu một loại → None."""
    if not positive["n"] or not trap["n"]:
        return None
    return round((positive["rate"] + trap["rate"]) / 2, 4)


def always_baseless_predictions(gold_clauses: Mapping[str, Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Mức chuẩn tầm thường: kết luận BASELESS cho mọi khoản mà không đọc gì."""
    return {nid: {"outcome": BASELESS, "ast": None} for nid in gold_clauses}


def paired_comparison(score_a: Mapping[str, Any], score_b: Mapping[str, Any],
                      subset: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """So cặp hai cấu hình trên cùng các khoản: b = chỉ A đúng, c = chỉ B đúng, McNemar chính xác."""
    ids = list(subset) if subset is not None else sorted(score_a["per_clause"])
    a = [is_correct(score_a["per_clause"][i]) for i in ids]
    b = [is_correct(score_b["per_clause"][i]) for i in ids]
    only_a = [i for i, x, y in zip(ids, a, b, strict=True) if x and not y]
    only_b = [i for i, x, y in zip(ids, a, b, strict=True) if y and not x]
    return {"n": len(ids), "both": sum(x and y for x, y in zip(a, b, strict=True)), "only_a": only_a, "only_b": only_b,
            "p_value": round(mcnemar_exact(len(only_a), len(only_b)), 4)}


def tier4_ids(gold_clauses: Mapping[str, Mapping[str, Any]]) -> List[str]:
    return sorted(nid for nid, g in gold_clauses.items() if g["kind"] == "positive" and g["tier4"])
