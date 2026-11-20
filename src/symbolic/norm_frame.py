"""
Khung chuẩn tắc có danh mục đóng (cấu hình N; đăng ký trước B6, docs/V2_DANG_KY_TRUOC.md) — M2 Norm Extractor.

LLM điền trong `obligation_analysis`: norm_type (danh mục đóng), action (trích nguyên văn), deadline (trích hoặc
null). Code kiểm (không do LLM quyết):
  N1 định dạng khung            frame_error
  N2 loại chuẩn tắc không diễn đạt được bằng DECLARE (nội dung, tính toán, tổ chức, chế tài, định nghĩa) → BASELESS
  N3 có trích thời hạn mà AST không có thời hạn / điều kiện ngày   missing_deadline
  N5 mẫu DECLARE không hợp loại chuẩn tắc (TEMPLATES_BY_NORM)       template_error
  N4 activity không thuộc loại giấy tờ mà khoản được nối tới qua MAPS_TO (KG)   kg_support
"""

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Mapping, Optional, Sequence

from ..kg.metamodel import NORM_TYPES  # danh mục đóng thuộc metamodel (M2) — một nguồn duy nhất
from ..mde.constraint_ast import activity_members

COMPOSITE_SEP = " / "
EXPRESSIBLE = frozenset({"action_order", "deadline", "prohibition"})
DATE_ATTR = "date"
# N5 (bổ sung B6, 2026-11-20, trước mọi lần chạy N): mẫu DECLARE hợp với loại chuẩn tắc — theo ngữ nghĩa mẫu và mục
# 5.2–5.3 của hướng dẫn gán nhãn (KHÔNG rút từ gold). Thời hạn: mẫu mang được time_max hoặc điều kiện ngày; hạn chót
# "không được làm A sau mốc" = Absence(A) với ngày(A) > mốc. Cấm: mẫu phủ định hoặc Absence.
_POSITIVE_ORDER = ("Response", "Alternate Response", "Chain Response", "Precedence", "Alternate Precedence",
                   "Chain Precedence")
TEMPLATES_BY_NORM = {
    "action_order": frozenset({"Existence", "Init", "Exactly1", "Choice", "Exclusive Choice", "Responded Existence",
                               *_POSITIVE_ORDER}),
    "deadline": frozenset({"Existence", "Absence", *_POSITIVE_ORDER}),
    "prohibition": frozenset({"Absence", "Not Responded Existence", "Not Response", "Not Precedence",
                              "Not Co-Existence"}),
}


@dataclass(frozen=True)
class NormFrame:
    """Đầu vào kiểm N4 cho MỘT khoản: loại giấy tờ mà khoản được nối tới qua MAPS_TO (ontology đã duyệt)."""
    clause_doctypes: FrozenSet[str]


def frame_error(analysis: Optional[Mapping[str, Any]]) -> Optional[str]:
    """N1 — phản hồi cho LLM nếu khung thiếu / sai; None nếu hợp lệ."""
    if not isinstance(analysis, Mapping):
        return None  # thiếu obligation_analysis: kiểm D đã báo
    if analysis.get("norm_type") not in NORM_TYPES:
        return (f"obligation_analysis.norm_type must be one of {list(NORM_TYPES)}, "
                f"got {analysis.get('norm_type')!r}.")
    action = analysis.get("action")
    if not isinstance(action, str) or not action.strip():
        return "obligation_analysis.action must quote the action phrase of the clause."
    deadline = analysis.get("deadline")
    if deadline is not None and (not isinstance(deadline, str) or not deadline.strip()):
        return "obligation_analysis.deadline must quote the period or date of the clause, or be null."
    return None


def quote_error(analysis: Optional[Mapping[str, Any]], sources: Sequence[str]) -> Optional[str]:
    """N1 (bổ sung 2026-11-20): `action` và `deadline` phải là trích dẫn THẬT của văn bản đưa cho LLM (khoản + khoản
    được dẫn chiếu) — cùng phép kiểm dẫn chứng của proof trace: 'unsupported' (không nguyên văn, không gần nguyên văn)
    → phản hồi. Đoạn quá ngắn để kết luận (< MIN_FRAGMENT ký tự) không xét."""
    from ..evaluation.proof_trace import evidence_check  # nhập tại chỗ: tránh vòng symbolic ↔ evaluation

    if not isinstance(analysis, Mapping):
        return None
    for key in ("action", "deadline"):
        quote = analysis.get(key)
        if isinstance(quote, str) and quote.strip() and evidence_check(quote, sources)["level"] == "unsupported":
            return (f"obligation_analysis.{key} \"{quote}\" is not a quote of the clause text. Copy the words of the "
                    "clause (or of a referenced provision) verbatim.")
    return None


def not_expressible(analysis: Optional[Mapping[str, Any]]) -> bool:
    """N2 — loại chuẩn tắc không phải thứ tự / thời hạn / cấm của các bước xử lý hồ sơ."""
    return isinstance(analysis, Mapping) and analysis.get("norm_type") in NORM_TYPES \
        and analysis["norm_type"] not in EXPRESSIBLE


def _has_time(ast: Mapping[str, Any]) -> bool:
    if ast.get("time_max") is not None:
        return True
    conds = [ast.get("activation_attr")] + [c.get("attr") for c in ast.get("extra_conditions") or []]
    return DATE_ATTR in conds


def missing_deadline(analysis: Optional[Mapping[str, Any]], ast: Mapping[str, Any]) -> Optional[str]:
    """N3 — phản hồi nếu khung trích thời hạn mà ràng buộc không có thời hạn / điều kiện ngày."""
    if not isinstance(analysis, Mapping) or not analysis.get("deadline") or _has_time(ast):
        return None
    return (f"Your obligation_analysis quotes the deadline \"{analysis['deadline']}\", but the constraint has no "
            "time_max and no condition on \"date\". Express the deadline in the constraint, or set deadline to null "
            "if the clause states none.")


def template_error(analysis: Optional[Mapping[str, Any]], ast: Mapping[str, Any]) -> Optional[str]:
    """N5 — phản hồi nếu mẫu DECLARE không hợp với loại chuẩn tắc đã khai (VD 'prohibition' mà dùng Response)."""
    if not isinstance(analysis, Mapping) or analysis.get("norm_type") not in TEMPLATES_BY_NORM:
        return None
    allowed = TEMPLATES_BY_NORM[analysis["norm_type"]]
    if ast.get("template_name") in allowed:
        return None
    return (f"Your obligation_analysis says norm_type \"{analysis['norm_type']}\", but template "
            f"\"{ast.get('template_name')}\" does not express that kind of norm. Use one of {sorted(allowed)}, or "
            "correct norm_type if the clause is a different kind of norm.")


def ast_doctypes(ast: Mapping[str, Any]) -> FrozenSet[str]:
    names = [ast.get("activation_activity"), ast.get("target_activity")]
    return frozenset(m.split(COMPOSITE_SEP, 1)[0] for n in names if n for m in activity_members(n))


def kg_support(ast: Mapping[str, Any], clause_doctypes: FrozenSet[str]) -> Dict[str, Any]:
    """N4 / tín hiệu S2 — loại giấy tờ của mọi activity ⊆ loại giấy tờ của khoản qua MAPS_TO."""
    used = ast_doctypes(ast)
    unsupported = sorted(used - clause_doctypes)
    return {"supported": not unsupported, "activity_doctypes": sorted(used),
            "clause_doctypes": sorted(clause_doctypes), "unsupported": unsupported}


def kg_feedback(rec: Mapping[str, Any]) -> str:
    linked = ", ".join(f"'{d}'" for d in rec["clause_doctypes"]) or "none"
    return (f"Knowledge-graph check: the clause is linked (through its legal terms) to these document types: "
            f"{linked}; your constraint uses activities of {', '.join(repr(d) for d in rec['unsupported'])}, which the "
            "clause does not refer to. Use activities that record the action the clause regulates, or return "
            "no_constraint if no such activity exists. If you are sure, you may keep the constraint.")
