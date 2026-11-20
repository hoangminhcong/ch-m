"""
v2 — kiểm dựa trên hồ sơ tầng Tiến trình (src/kg/process_profile.py) trong vòng lặp sinh.
Tham số chốt trước khi chạy: docs/V2_DANG_KY_TRUOC.md mục 3. Không dùng gold; phản hồi không gợi ý đáp án cụ thể
ngoài những gì log ghi (tên loại giấy tờ, năm, activity cùng bước).

  year_group_feedback    activity chỉ có ở một phần các năm mà log có loại giấy tờ / bước thay thế cho các năm còn
                         lại → nhắc cú pháp nhóm {A | B} (phản hồi một lần cho mỗi ràng buộc).
  event_attribute_error  điều kiện trên thuộc tính event mà activity mang điều kiện không bao giờ ghi (HAS_ATTRIBUTE).
  MassViolationChecker   > 20% số hồ sơ có kích hoạt bị vi phạm → phản hồi một lần kèm ≤ 2 hồ sơ phản ví dụ;
                         LLM giữ nguyên → chấp nhận, gắn cờ.
  activity_notes         ghi chú activity cho giám khảo Tầng 3 (loại giấy tờ, năm, tỉ lệ hồ sơ, vai trò, bước
                         trước/sau; nghĩa loại giấy tờ chỉ khi ontology đã duyệt).
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..mde.constraint_ast import DeclareConstraintAST, activity_members
from .data_conditions import CASE_KEY

MASS_VIOLATION_THRESHOLD = 0.20  # chốt 2026-11-16, docs/V2_DANG_KY_TRUOC.md mục 3
MAX_EXAMPLES = 2
MAX_STEPS = 12
VIOLATED, VACUOUS = "Violated", "Vacuously Satisfied"
PRECEDENCE_FAMILY = ("Precedence", "Alternate Precedence", "Chain Precedence", "Not Precedence")
NON_EVENT_ATTRS = ("date", "time:timestamp")


@dataclass(frozen=True)
class ProcessV2:
    """Bật các kiểm v2 trong vòng lặp sinh. mass = None → bỏ kiểm vi phạm hàng loạt (VD khi chưa nạp log)."""

    profile: Mapping[str, Any]
    mass: Optional["MassViolationChecker"] = None
    ontology: Optional[Mapping[str, Any]] = None
    # Công tắc cho các cấu hình ablation của Z (scripts/run_cap_generation.py): mặc định bật hết
    check_attribute: bool = True
    check_year: bool = True
    check_mass: bool = True
    judge_notes: bool = True


def _years(ys: Sequence[int]) -> str:
    return ", ".join(str(y) for y in ys)


def _scope_years(activity_years: Sequence[int], years: Optional[Sequence[int]]) -> List[int]:
    return sorted(set(activity_years) & set(years)) if years else list(activity_years)


def _sides(ast: Mapping[str, Any]) -> List[str]:
    return [s for s in (ast.get("activation_activity"), ast.get("target_activity")) if s]


def _condition_side(ast: Mapping[str, Any]) -> Optional[str]:
    """Activity mà điều kiện áp lên: B với họ Precedence (quy ước Declare4Py), A với các mẫu còn lại."""
    if ast.get("template_name") in PRECEDENCE_FAMILY and ast.get("target_activity"):
        return ast["target_activity"]
    return ast.get("activation_activity")


def year_group_feedback(ast: Mapping[str, Any], profile: Mapping[str, Any],
                        years: Optional[Sequence[int]] = None) -> Optional[str]:
    """years (tập Đức): chỉ xét các năm của khoản — khoản 2016 không bị gợi ý mở rộng sang 2015/2017."""
    acts = profile["activities"]
    all_years = set(profile["years"]) & set(years) if years else set(profile["years"])
    replacements, doctype_years = profile.get("doctype_replacements", {}), profile.get("doctype_years", {})
    for spec in _sides(ast):
        members = [m for m in sorted(activity_members(spec)) if m in acts]
        if not members:
            continue
        covered = set().union(*(acts[m]["years"] for m in members)) & all_years
        missing = all_years - covered
        if not missing:
            continue
        steps = sorted({s for m in members for s in acts[m]["same_step"]
                        if s not in members and s in acts and set(acts[s]["years"]) & missing})
        doctypes = sorted({d for m in members for d in replacements.get(acts[m]["doctype"], [])
                           if set(doctype_years.get(d, [])) & missing})
        if not steps and not doctypes:
            continue
        where = f" as document type {', '.join(repr(d) for d in doctypes)}" if doctypes else ""
        same = f" Activities for the same step in those years: {steps}." if steps else ""
        return (f"[Year Coverage]: Activity '{spec}' is recorded only in years {_years(sorted(covered))} of the event "
                f"log (years {_years(sorted(all_years))}). In years {_years(sorted(missing))} the log records this "
                f"kind of document{where} instead.{same} If the clause applies regardless of year, write the step as "
                "a group {Activity 1 | Activity 2} that also includes the activity used in those years; if the "
                "clause only concerns the years above, keep the constraint unchanged.")
    return None


def event_attribute_error(ast: Mapping[str, Any], profile: Mapping[str, Any]) -> Optional[str]:
    side = _condition_side(ast)
    if not side:
        return None
    attrs = [ast["activation_attr"]] if ast.get("activation_attr") else []
    attrs += [c.get("attr") for c in ast.get("extra_conditions") or [] if c.get("attr")]
    acts = profile["activities"]
    for raw in attrs:
        attr = raw.strip()[2:] if raw.strip().startswith(("A.", "T.")) else raw.strip()
        if attr.startswith("case:") or attr in NON_EVENT_ATTRS:
            continue
        for m in sorted(activity_members(side)):
            if m in acts and attr not in acts[m]["event_attributes"]:
                return (f"[Layer 2 Attribute Placement]: Event attribute '{attr}' is never recorded on activity '{m}' "
                        "in the event log, so the condition can never hold for that event. Use an attribute that is "
                        "recorded on that activity, or a case attribute.")
    return None


def _steps(events: Sequence[Mapping[str, Any]]) -> str:
    out: List[str] = []
    last = None
    for e in events:
        name = e["concept:name"]
        if name == last:
            continue
        last = name
        ts = e.get("time:timestamp")
        out.append(f"{name} ({str(ts)[:10]})" if ts is not None else name)
    return " → ".join(out[:MAX_STEPS]) + (" → …" if len(out) > MAX_STEPS else "")


class MassViolationChecker:
    """Áp ràng buộc ứng viên lên toàn log (engine Declare4Py đã nạp) và đếm hồ sơ bị vi phạm / có kích hoạt."""

    def __init__(self, engine: Any, threshold: float = MASS_VIOLATION_THRESHOLD,
                 max_examples: int = MAX_EXAMPLES) -> None:
        self.engine, self.threshold, self.max_examples = engine, threshold, max_examples
        self._cache: Dict[str, Dict[str, Any]] = {}

    def assess(self, ast: Mapping[str, Any], years: Optional[Sequence[int]] = None) -> Dict[str, Any]:
        """years (tập Đức): chỉ hồ sơ của các năm của khoản; None = mọi hồ sơ."""
        line = DeclareConstraintAST.model_validate(dict(ast)).to_declare4py_line().strip()
        key = line if years is None else f"{line}@{sorted(years)}"
        if key in self._cache:
            return self._cache[key]
        parsed = self.engine.parse_decl_lines([line])
        if not parsed:
            raise ValueError(f"Engine không phân tích được dòng .decl: {line}")
        activated, violated, examples = 0, 0, []
        results = self.engine.case_results(parsed[0]) if years is None else \
            self.engine.case_results(parsed[0], years=years)
        for case_id, res, events in results:
            if res.state == VACUOUS:
                continue
            activated += 1
            if res.state == VIOLATED:
                violated += 1
                if len(examples) < self.max_examples:
                    examples.append(self._example(case_id, events))
        ratio = violated / activated if activated else 0.0
        rec = {"activated": activated, "violated": violated, "ratio": round(ratio, 4),
               "mass_violation": activated > 0 and ratio > self.threshold, "examples": examples}
        self._cache[key] = rec
        return rec

    @staticmethod
    def _example(case_id: str, events: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        year = events[0].get(CASE_KEY, {}).get("case:year") if events else None
        return {"case": case_id, "year": year, "steps": _steps(events)}

    def feedback(self, ast: Mapping[str, Any], rec: Mapping[str, Any]) -> str:
        cases = "; ".join(f"case {e['case']}" + (f" (year {e['year']})" if e["year"] is not None else "")
                          + f": {e['steps']}" for e in rec["examples"])
        return (f"[Log-grounded Mass Violation]: Checked on the event log, the constraint is violated in "
                f"{rec['violated']} of {rec['activated']} activated cases ({100 * rec['ratio']:.0f}%). An agency in "
                f"normal operation rarely violates a legal obligation in more than {100 * self.threshold:.0f}% of its "
                "cases, so the constraint may not express what the clause requires (wrong activity, order, template "
                f"or a missing condition). Example violating cases — {cases}. Re-read the clause and check that each "
                "activity really is the step the clause talks about. If the constraint is correct, return it "
                "unchanged.")


def activity_notes(ast: Mapping[str, Any], profile: Mapping[str, Any],
                   ontology: Optional[Mapping[str, Any]] = None, years: Optional[Sequence[int]] = None) -> str:
    """years (tập Đức): năm hoạt động chỉ nêu trong các năm của khoản; tỉ lệ hồ sơ là trên toàn log (ghi rõ)."""
    acts = profile["activities"]
    onto = ontology if ontology and ontology.get("status") == "approved" else None
    lines: List[str] = []
    for m in dict.fromkeys(x for s in _sides(ast) for x in sorted(activity_members(s))):
        a = acts.get(m)
        if a is None:
            continue
        meaning = (onto or {}).get("doctypes", {}).get(a["doctype"], {}).get("meaning")
        applicant = m in set((onto or {}).get("applicant_initiated", []))
        roles = ", ".join(f"{k} {100 * v:.0f}%" for k, v in a["roles"].items() if v)
        before = ", ".join(n["activity"] for n in a["predecessors"]) or "none (first step)"
        after = ", ".join(n["activity"] for n in a["successors"]) or "none (last step)"
        lines.append(f"- '{m}': document type '{a['doctype']}'" + (f" ({meaning})" if meaning else "")
                     + ("; initiated by the applicant" if applicant else "")
                     + f"; recorded in years {_years(_scope_years(a['years'], years)) or 'none of the clause years'}; "
                     f"occurs in {100 * a['case_ratio']:.1f}% of cases{' (all years)' if years else ''}; "
                     f"performed by: {roles or 'unknown'}; usually preceded by: {before}; followed by: {after}")
    return "Process model notes (mined from the event log):\n" + "\n".join(lines) if lines else ""
