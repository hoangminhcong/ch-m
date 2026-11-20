"""
Hồ sơ miền (domain profile): phần chữ của prompt sinh ràng buộc (real_llm_client.py) và prompt trọng tài
Tầng 3.1 (verbalizer_roundtrip.py) phụ thuộc vào bộ luật + log.

- BPIC2017_PROFILE: Directive 2008/48/EC + BPIC2017 — chữ GIỐNG HỆT bản trước khi tách profile
  (tests/test_domain_profiles.py so từng byte với fixture chụp từ code cũ).
- CAP_PROFILE: 4 Quy định CAP + BPIC2018 — thêm cú pháp extra_conditions và 'date'. Ví dụ few-shot là
  miền giả định (thư viện), không trùng câu nào trong phiếu CAP.

Prompt chỉ nhận văn bản luật + Γ; không có trường nào cho mô tả gold.
"""

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class FewShotExample:
    clause_id: str
    clause_text: str
    activities: Tuple[str, ...]
    case_attributes: Tuple[Tuple[str, str], ...]  # (tên, kiểu Γ)
    event_attributes: Tuple[Tuple[str, str], ...]
    answer: Mapping[str, Any] = field(default_factory=dict)  # thứ tự khóa = thứ tự trong JSON gửi LLM


@dataclass(frozen=True)
class DomainProfile:
    name: str
    generator_system: str  # có chỗ '{templates}'
    clause_label: str
    show_attribute_types: bool
    examples: Tuple[FewShotExample, ...]
    judge_role: str
    judge_clause_phrase: str
    judge_context: str
    case_noun: str
    # Kiểm D (obligation_gate.py): LLM phân tích nghĩa vụ trước và được trả no_constraint. BPIC2017: tắt.
    abstain_enabled: bool = False


def _attr_list(attrs: Sequence[Tuple[str, str]], show_types: bool) -> List[str]:
    return [f"{n} ({t})" if show_types else n for n, t in attrs]


def _query(profile: DomainProfile, clause_id: str, text: str, activities: Sequence[str],
           case_attrs: Sequence[Tuple[str, str]], event_attrs: Sequence[Tuple[str, str]], final: bool) -> str:
    content = (
        f"{profile.clause_label} ({clause_id}): {text}\n"
        f"Allowed Activities: {list(activities)}\n"
        f"Allowed Case Attributes: {_attr_list(case_attrs, profile.show_attribute_types)}\n"
        f"Allowed Event Attributes: {_attr_list(event_attrs, profile.show_attribute_types)}"
    )
    return content + "\nReturn the DECLARE constraint as a valid JSON object." if final else content


def _schema_attrs(attrs: Mapping[str, Mapping[str, Any]]) -> List[Tuple[str, str]]:
    return [(name, str(meta.get("type", "String"))) for name, meta in attrs.items()]


def build_generation_messages(
    profile: DomainProfile,
    chunk: Mapping[str, Any],
    process_schema: Mapping[str, Any],
    allowed_templates: Sequence[str],
    dumps: Callable[[Any], str],
) -> List[Dict[str, str]]:
    """System + các cặp ví dụ few-shot + câu hỏi thật. `dumps` = json.dumps (giữ đúng định dạng cũ)."""
    system = profile.generator_system.replace("{templates}", str(list(allowed_templates)))
    messages = [{"role": "system", "content": system}]
    for ex in profile.examples:
        messages.append({"role": "user", "content": _query(
            profile, ex.clause_id, ex.clause_text, ex.activities, ex.case_attributes, ex.event_attributes,
            final=False)})
        messages.append({"role": "assistant", "content": dumps(dict(ex.answer))})
    messages.append({"role": "user", "content": _query(
        profile, chunk["article_id"], chunk["text"], process_schema["valid_activities"],
        _schema_attrs(process_schema["case_attributes"]), _schema_attrs(process_schema["event_attributes"]),
        final=True)})
    return messages


JUDGE_NOTES_USE = ("Use these notes only to judge whether each activity is the step the clause talks about; "
                   "they describe the event log, not the law.")


def build_judge_prompt(profile: DomainProfile, chunk: Mapping[str, Any], ast_json: str, verbalized: str,
                       notes: str = "") -> str:
    """notes (v2): ghi chú activity khai phá từ log; rỗng → prompt giữ nguyên từng byte như v1."""
    context = f"{profile.judge_context}\n" + (f"\n{notes}\n{JUDGE_NOTES_USE}\n" if notes else "")
    return (
        f"{profile.judge_role}\n"
        f"Compare the original {profile.judge_clause_phrase} with the back-translated business process constraint:\n"
        f"- Original Legal Clause ({chunk['article_id']}): \"{chunk['text']}\"\n"
        f"- Candidate AST JSON: {ast_json}\n"
        f"- Back-translated Constraint: \"{verbalized}\"\n"
        "\n"
        "Context:\n"
        f"{context}"
        "\n"
        "Provide compiler-style diagnostic feedback WITHOUT revealing any benchmark ground-truth answers.\n"
        'Return JSON only: {"verdict": "EQUIVALENT" | "REVERSED_ORDER" | "THRESHOLD_MISMATCH" | "BASELESS", '
        '"diagnostic_feedback": "..."}\n'
    )


# --------------------------------------------------------------------------- BPIC2017 (chữ y nguyên bản cũ)

_NO_CONDITION = {"activation_attr": None, "activation_op": None, "activation_val": None}

BPIC2017_PROFILE = DomainProfile(
    name="bpic2017",
    generator_system=(
        "You are a formal compliance assistant for financial workflows. "
        "Translate the cited EU Directive clause "
        "into a formal DECLARE constraint in JSON format.\n"
        "Allowed DECLARE templates: {templates}\n"
        "Return valid JSON with keys: article_id, template_name, activation_activity, target_activity, "
        "activation_attr, activation_op, activation_val, time_min, time_max, time_unit.\n"
        "IMPORTANT RULES:\n"
        "1. Only specify activation_attr, activation_op, activation_val, or time_max if explicitly stated in the directive clause; otherwise, you MUST set them to null.\n"
        "2. Numeric monetary thresholds (e.g. 500) belong to activation_val as a float (e.g. 500.0) with activation_op (e.g. '<=', '>=').\n"
        "3. Durations (e.g. 7 days) belong to time_max (e.g. 7) with time_unit ('s', 'm', 'h', 'd')."
    ),
    clause_label="Directive Clause",
    show_attribute_types=False,
    examples=(
        FewShotExample(
            clause_id="Article Example-1",
            clause_text="The creditor shall verify the identity of the consumer before granting the credit.",
            activities=("Identity_Verification", "Account_Opening"),
            case_attributes=(("case:RequestedAmount", "Float"),),
            event_attributes=(("Action", "String"),),
            answer={"article_id": "Article Example-1", "template_name": "Precedence",
                    "activation_activity": "Identity_Verification", "target_activity": "Account_Opening",
                    **_NO_CONDITION, "time_min": None, "time_max": None, "time_unit": None},
        ),
        FewShotExample(
            clause_id="Article Example-2",
            clause_text="For incoming transfers exceeding EUR 5,000, the bank shall notify the compliance officer within 3 days.",
            activities=("Receive_Transfer", "Notify_Officer"),
            case_attributes=(("case:CustomerSegment", "String"),),
            event_attributes=(("TransferAmount", "Float"),),
            answer={"article_id": "Article Example-2", "template_name": "Response",
                    "activation_activity": "Receive_Transfer", "target_activity": "Notify_Officer",
                    "activation_attr": "TransferAmount", "activation_op": ">", "activation_val": 5000.0,
                    "time_min": None, "time_max": 3, "time_unit": "d"},
        ),
    ),
    judge_role="You are a formal semantic compliance judge for financial process mining.",
    judge_clause_phrase="EU Directive 2008/48/EC legal clause",
    judge_context=(
        "In business process modeling for financial institutions, statutory principles are operationalized into concrete workflow steps and status transitions in the bank's IT system.\n"
        "- An operational workflow constraint that logically supports, facilitates, or implements the statutory obligation stated in the clause is a legitimate implementation and should be classified as EQUIVALENT.\n"
        "- Do NOT classify a constraint as BASELESS simply because IT activity names do not appear verbatim in the Directive text.\n"
        "- STRICTLY classify as BASELESS if and only if:\n"
        "   1. The transaction or domain is explicitly EXCLUDED from the Directive's scope by the clause;\n"
        "   2. The constraint introduces a quantitative threshold or deadline that is not stated in the clause;\n"
        "   3. The claimed rule contradicts the legal text (e.g. it turns a right granted to one party into an obligation imposed on that party)."
    ),
    case_noun="credit case",
)


# --------------------------------------------------------------------------- CAP / BPIC2018

CAP_PROFILE_NO_DUTY = DomainProfile(  # CAP không có kiểm D — cấu hình ablation Y-noDuty
    name="cap-noduty",
    generator_system=(
        "You are a formal compliance assistant for public administration workflows. "
        "Translate the cited clause of the EU Common Agricultural Policy regulations "
        "(Regulations (EU) No 1306/2013, 1307/2013, 640/2014, 809/2014) "
        "into a formal DECLARE constraint in JSON format.\n"
        "The event log records how a public authority processes aid applications; "
        "one case is one applicant's application for one year.\n"
        "Allowed DECLARE templates: {templates}\n"
        "Return valid JSON with keys: article_id, template_name, activation_activity, target_activity, "
        "activation_attr, activation_op, activation_val, extra_conditions, time_min, time_max, time_unit.\n"
        "IMPORTANT RULES:\n"
        "1. Only specify activation_attr, activation_op, activation_val, extra_conditions, or time_max if explicitly stated in the clause; otherwise, you MUST set them to null (extra_conditions to []).\n"
        "2. Numeric thresholds belong to activation_val as a number with activation_op (e.g. '<=', '>='). "
        "Case attributes (prefix 'case:') may be used as conditions; Boolean attributes are compared with == true or == false.\n"
        "3. Durations belong to time_max with the unit stated in the clause, never converted: time_unit 'd' (calendar days), "
        "'wd' (working days), 'w' (weeks), 'mo' (calendar months), 'h', 'm' or 's' (e.g. 'within two months' -> time_max 2, time_unit 'mo').\n"
        "4. If several conditions must hold together, put the first in activation_attr/activation_op/activation_val "
        "and the others in extra_conditions as a list of {\"attr\": ..., \"op\": ..., \"val\": ...}; all conditions are combined with AND. "
        "Conditions apply to the event that activates the constraint: the activation_activity for Existence, Response and similar "
        "templates, but the target_activity (the later event) for Precedence, Alternate Precedence, Chain Precedence and Not Precedence. "
        "A condition on a case attribute with Existence means EVERY case must contain such an event; to say 'cases with property X "
        "must contain A', use Responded Existence from an activity present in every case to A, with the condition on X.\n"
        "4b. If the same step is recorded by different activities (e.g. a different document type in different years), "
        "activation_activity or target_activity may be a group written as {Activity 1 | Activity 2}.\n"
        "5. A fixed calendar date uses the attribute \"date\" (the calendar date of the event) with a value "
        "\"year-MM-DD\" (year = the year of the case), \"year+1-MM-DD\" (the following year) or \"YYYY-MM-DD\" (a fixed year). "
        "A period between two dates is two conditions on \"date\"."
    ),
    clause_label="Regulation Clause",
    show_attribute_types=True,
    examples=(
        FewShotExample(
            clause_id="Example-1",
            clause_text="Annual membership cards shall be renewed no later than 31 January.",
            activities=("Renew_Card", "Borrow_Book", "Return_Book"),
            case_attributes=(("case:year", "String"), ("case:student", "Boolean")),
            event_attributes=(("time:timestamp", "Timestamp"),),
            answer={"article_id": "Example-1", "template_name": "Existence",
                    "activation_activity": "Renew_Card", "target_activity": None,
                    "activation_attr": "date", "activation_op": "<=", "activation_val": "year-01-31",
                    "extra_conditions": [], "time_min": None, "time_max": None, "time_unit": None},
        ),
        FewShotExample(
            clause_id="Example-2",
            clause_text="Where a student member under 18 years of age borrows a rare book, "
                        "the library shall record a deposit within 2 days.",
            activities=("Borrow_Rare_Book", "Record_Deposit", "Renew_Card"),
            case_attributes=(("case:year", "String"), ("case:student", "Boolean"), ("case:age", "Float")),
            event_attributes=(("time:timestamp", "Timestamp"),),
            answer={"article_id": "Example-2", "template_name": "Response",
                    "activation_activity": "Borrow_Rare_Book", "target_activity": "Record_Deposit",
                    "activation_attr": "case:student", "activation_op": "==", "activation_val": True,
                    "extra_conditions": [{"attr": "case:age", "op": "<", "val": 18.0}],
                    "time_min": None, "time_max": 2, "time_unit": "d"},
        ),
    ),
    judge_role="You are a formal semantic compliance judge for public administration process mining.",
    judge_clause_phrase="EU Common Agricultural Policy regulation clause",
    judge_context=(
        "The event log records how a public authority processes aid applications (one case = one applicant's application for one year). "
        "Statutory obligations are operationalized into concrete workflow steps of the authority's IT system.\n"
        "A condition on \"date\" refers to the calendar date of the event; \"year\" is the year of the case and \"year+1\" the following year.\n"
        "- An operational workflow constraint that logically supports, facilitates, or implements the statutory obligation stated in the clause is a legitimate implementation and should be classified as EQUIVALENT.\n"
        "- Do NOT classify a constraint as BASELESS simply because IT activity names do not appear verbatim in the regulation text.\n"
        "- STRICTLY classify as BASELESS if and only if:\n"
        "   1. The clause imposes no obligation that could be observed in the processing of applications (e.g. definitions, empowerments of the Commission, reporting duties of Member States);\n"
        "   2. The constraint introduces a quantitative threshold, date or deadline that is not stated in the clause;\n"
        "   3. The claimed rule contradicts the legal text (e.g. it turns a right granted to one party into an obligation imposed on that party)."
    ),
    case_noun="application case",
)


# --------------------------------------------------------------------------- CAP + kiểm D (cấu hình chính)

_DUTY_RULE = (
    "\n6. Before the constraint, analyse the obligation in \"obligation_analysis\": "
    "{\"duty_bearer\": one of [\"member_state_rules_or_systems\", \"commission\", \"paying_agency_case_processing\", "
    "\"applicant\", \"other\"], \"observable_in_log\": true or false, \"evidence\": a short quote from the clause}. "
    "Obligations of Member States to adopt rules, to set up or maintain systems, databases or registers, or to report, "
    "and empowerments of the Commission, are not recorded in individual application cases. "
    "If observable_in_log is false, return only {\"article_id\": ..., \"obligation_analysis\": {...}, \"no_constraint\": true}.\n"
    "7. Do not choose an activity only because its name shares a word with the clause."
)
_JUDGE_EXTRA = (
    "\n- Obligations of Member States to adopt rules, to set up or maintain systems, databases or registers are not "
    "observable in individual application cases; a constraint derived from them is BASELESS.\n"
    "- A word shared by the clause and an activity name is not by itself evidence that the constraint is EQUIVALENT."
)


def _with_analysis(answer: Mapping[str, Any], duty_bearer: str, evidence: str) -> Dict[str, Any]:
    head = {"article_id": answer["article_id"],
            "obligation_analysis": {"duty_bearer": duty_bearer, "observable_in_log": True, "evidence": evidence}}
    return {**head, **{k: v for k, v in answer.items() if k != "article_id"}}


_EX1, _EX2 = CAP_PROFILE_NO_DUTY.examples
CAP_PROFILE = replace(
    CAP_PROFILE_NO_DUTY,
    name="cap",
    # F-PROMPT (kiểm toán đợt 2): danh sách khoá JSON nhắc cả obligation_analysis / no_constraint của quy tắc 6
    generator_system=CAP_PROFILE_NO_DUTY.generator_system.replace(
        "time_min, time_max, time_unit.\n",
        "time_min, time_max, time_unit, and obligation_analysis (or only article_id, obligation_analysis and "
        "no_constraint, see rule 6).\n", 1) + _DUTY_RULE,
    examples=(
        replace(_EX1, answer=_with_analysis(_EX1.answer, "applicant", "shall be renewed no later than 31 January")),
        replace(_EX2, answer=_with_analysis(_EX2.answer, "other", "the library shall record a deposit within 2 days")),
        FewShotExample(
            clause_id="Example-3",
            clause_text="Member States shall set up a national register of public libraries and keep it up to date.",
            activities=("Renew_Card", "Borrow_Book", "Return_Book", "Register_Reader"),
            case_attributes=(("case:year", "String"), ("case:student", "Boolean")),
            event_attributes=(("time:timestamp", "Timestamp"),),
            answer={"article_id": "Example-3",
                    "obligation_analysis": {"duty_bearer": "member_state_rules_or_systems", "observable_in_log": False,
                                            "evidence": "Member States shall set up a national register"},
                    "no_constraint": True},
        ),
    ),
    judge_context=CAP_PROFILE_NO_DUTY.judge_context + _JUDGE_EXTRA,
    abstain_enabled=True,
)

# --------------------------------------------------------------------------- CAP + khung chuẩn tắc (cấu hình N)
# Đăng ký trước B6 (docs/V2_DANG_KY_TRUOC.md): danh mục loại chuẩn tắc đóng; kiểm ở src/symbolic/norm_frame.py.

_NORM_RULE = (
    "\n8. In obligation_analysis also give \"norm_type\": one of [\"action_order\", \"deadline\", \"prohibition\", "
    "\"content_requirement\", \"calculation\", \"organisational\", \"penalty\", \"definition\"], \"action\": a verbatim "
    "quote of the action phrase the clause regulates, and \"deadline\": a verbatim quote of the period or date stated "
    "in the clause, or null. Norm types:\n"
    "- action_order: a step in processing a case must take place, or must take place before or after another step;\n"
    "- deadline: a step must take place within a period or by a date;\n"
    "- prohibition: a step must not take place, possibly under conditions (e.g. an aid shall not be paid);\n"
    "- content_requirement: what an application, declaration, document, check or report must contain, cover or identify;\n"
    "- calculation: how an amount, area, rate or reduction is calculated;\n"
    "- organisational: responsibilities, systems, registers, records, delegation, duties of Member States or of the "
    "Commission;\n"
    "- penalty: the size or computation of an administrative penalty or reduction;\n"
    "- definition: definitions, scope, or references to other provisions.\n"
    "Only action_order, deadline and prohibition can be expressed as a DECLARE constraint; for every other type set "
    "observable_in_log to false and return no_constraint.\n"
    "9. The template must match norm_type: action_order -> Existence, Init, Exactly1, Choice, Exclusive Choice, "
    "Responded Existence, Response, Alternate Response, Chain Response, Precedence, Alternate Precedence or "
    "Chain Precedence; deadline -> Response, Alternate Response, Chain Response, Precedence, Alternate Precedence or "
    "Chain Precedence with time_max, or Existence / Absence with a condition on \"date\" (a deadline 'A by date D' "
    "is Absence(A) with date > D); prohibition -> Absence, Not Responded Existence, Not Response, Not Precedence or "
    "Not Co-Existence."
)


def _with_norm(answer: Mapping[str, Any], norm_type: str, action: str, deadline: Optional[str]) -> Dict[str, Any]:
    analysis = {**answer["obligation_analysis"], "norm_type": norm_type, "action": action, "deadline": deadline}
    return {**answer, "obligation_analysis": analysis}


_CEX1, _CEX2, _CEX3 = CAP_PROFILE.examples
CAP_PROFILE_NORM = replace(
    CAP_PROFILE,
    name="cap-norm",
    generator_system=CAP_PROFILE.generator_system + _NORM_RULE,
    examples=(
        replace(_CEX1, answer=_with_norm(_CEX1.answer, "deadline", "Annual membership cards shall be renewed",
                                         "no later than 31 January")),
        replace(_CEX2, answer=_with_norm(_CEX2.answer, "deadline", "the library shall record a deposit",
                                         "within 2 days")),
        replace(_CEX3, answer=_with_norm(_CEX3.answer, "organisational",
                                         "Member States shall set up a national register", None)),
        FewShotExample(
            clause_id="Example-4",
            clause_text="The deposit record shall indicate the title of the book and the amount paid.",
            activities=("Borrow_Rare_Book", "Record_Deposit", "Renew_Card"),
            case_attributes=(("case:year", "String"), ("case:student", "Boolean")),
            event_attributes=(("time:timestamp", "Timestamp"),),
            answer={"article_id": "Example-4",
                    "obligation_analysis": {"duty_bearer": "other", "observable_in_log": False,
                                            "evidence": "The deposit record shall indicate the title of the book",
                                            "norm_type": "content_requirement",
                                            "action": "The deposit record shall indicate the title of the book and "
                                                      "the amount paid",
                                            "deadline": None},
                    "no_constraint": True},
        ),
    ),
)

_EU_SOURCE = ("the EU Common Agricultural Policy regulations (Regulations (EU) No 1306/2013, 1307/2013, 640/2014, "
              "809/2014)")
_DE_SOURCE = ("the German national rules implementing the EU Common Agricultural Policy (InVeKoS-Verordnung, "
              "Direktzahlungen-Durchführungsverordnung). The clause is written in German; referenced EU provisions "
              "may be quoted in English. The event log comes from Germany")


def german_profile(base: DomainProfile) -> DomainProfile:
    """Tập Đức (docs/V2_DANG_KY_TRUOC.md mục 5.1): chỉ đổi phần MÔ TẢ NGUỒN văn bản; quy tắc, ví dụ, ngữ cảnh giám
    khảo giữ nguyên. Prompt bộ CAP không đổi (hồ sơ CAP_PROFILE / CAP_PROFILE_NO_DUTY không bị sửa)."""
    if _EU_SOURCE not in base.generator_system:
        raise ValueError(f"Hồ sơ {base.name} không có đoạn mô tả nguồn EU để thay.")
    return replace(base, name=base.name + "-de",
                   generator_system=base.generator_system.replace(_EU_SOURCE, _DE_SOURCE, 1),
                   judge_clause_phrase="German national CAP implementing rule clause (in German)")
