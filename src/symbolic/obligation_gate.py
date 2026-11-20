"""
Kiểm D — phân tích nghĩa vụ trước khi viết ràng buộc (chỉ với hồ sơ miền bật `abstain_enabled`, VD CAP).

LLM điền `obligation_analysis` = {duty_bearer, observable_in_log, evidence} rồi mới chọn mẫu DECLARE, và được
phép trả `no_constraint: true` khi khoản luật không có nghĩa vụ quan sát được trên từng hồ sơ. Gốc lỗi ở
R1306:Art70(2): nghĩa vụ "Nhà nước lập hệ thống" bị đọc thành nghĩa vụ xử lý hồ sơ.

Phần ký hiệu (kiểm được, không cần LLM): định dạng phân tích hợp lệ; và NHẤT QUÁN — đã nói nghĩa vụ không ở
mức hồ sơ (Nhà nước làm luật / lập hệ thống, Ủy ban) hoặc observable_in_log = false mà vẫn trả ràng buộc →
phản hồi một lần để LLM tự xem lại. Lập luận được lưu trong trajectory để kiểm toán.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..mde.constraint_ast import extract_json_payload

DUTY_BEARERS = ("member_state_rules_or_systems", "commission", "paying_agency_case_processing", "applicant", "other")
NOT_CASE_LEVEL = frozenset({"member_state_rules_or_systems", "commission"})


@dataclass(frozen=True)
class ObligationDecision:
    analysis: Optional[Dict[str, Any]]
    no_constraint: bool
    error: Optional[str]          # phân tích thiếu / sai định dạng → phản hồi cho LLM
    inconsistent: Optional[str]   # phân tích nói không ở mức hồ sơ nhưng vẫn trả ràng buộc


def _load(raw: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(extract_json_payload(str(raw)))
    except (json.JSONDecodeError, TypeError):
        return None  # Tầng 1 sẽ báo lỗi JSON
    return data if isinstance(data, dict) else None


def _analysis_error(analysis: Any) -> Optional[str]:
    if not isinstance(analysis, dict):
        return ("Missing 'obligation_analysis'. Before the constraint, return \"obligation_analysis\": "
                f"{{\"duty_bearer\": one of {list(DUTY_BEARERS)}, \"observable_in_log\": true|false, "
                "\"evidence\": a short quote from the clause}.")
    if analysis.get("duty_bearer") not in DUTY_BEARERS:
        return f"obligation_analysis.duty_bearer must be one of {list(DUTY_BEARERS)}, got {analysis.get('duty_bearer')!r}."
    if not isinstance(analysis.get("observable_in_log"), bool):
        return "obligation_analysis.observable_in_log must be true or false."
    return None


def assess_obligation(raw: Any) -> ObligationDecision:
    data = _load(raw)
    if data is None:
        return ObligationDecision(None, False, None, None)
    analysis = data.get("obligation_analysis")
    error = _analysis_error(analysis)
    if error:
        return ObligationDecision(None, False, error, None)
    no_constraint = data.get("no_constraint") is True
    if no_constraint and analysis["observable_in_log"]:
        return ObligationDecision(analysis, False, "no_constraint is true but obligation_analysis.observable_in_log "
                                                   "is true; make them consistent.", None)
    inconsistent = None
    if not no_constraint and (not analysis["observable_in_log"] or analysis["duty_bearer"] in NOT_CASE_LEVEL):
        inconsistent = (
            f"Obligation analysis inconsistency: you identified duty_bearer='{analysis['duty_bearer']}' "
            f"(observable_in_log={str(analysis['observable_in_log']).lower()}), whose obligations are not recorded "
            "in the processing of individual cases, yet you returned a constraint. Either correct the analysis "
            "with evidence from the clause, or return no_constraint."
        )
    return ObligationDecision(analysis, no_constraint, None, inconsistent)
