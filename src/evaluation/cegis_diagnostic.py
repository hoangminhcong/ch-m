"""
Chẩn đoán CEGIS tổng quát (Entity Matcher + kiểm rỗng) và client LLM giả lập của benchmark.
Tách từ experiment_runner.py (2026-11-20, mục 7 — giảm kích thước file); nội dung hàm GIỮ NGUYÊN.
experiment_runner.py nhập lại các tên này nên mọi `from src.evaluation.experiment_runner import ...` cũ vẫn chạy.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

try:
    from sklearn.metrics import precision_recall_fscore_support
except ImportError:

    def precision_recall_fscore_support(
        y_true: List[str],
        y_pred: List[str],
        labels: List[str],
        average: Optional[str] = None,
        zero_division: int = 0,
    ) -> Tuple[Any, Any, Any, Any]:
        precisions, recalls, f1s, supports = [], [], [], []
        for lbl in labels:
            tp = sum(1 for yt, yp in zip(y_true, y_pred, strict=True) if yt == lbl and yp == lbl)
            fp = sum(1 for yt, yp in zip(y_true, y_pred, strict=True) if yt != lbl and yp == lbl)
            fn = sum(1 for yt, yp in zip(y_true, y_pred, strict=True) if yt == lbl and yp != lbl)
            sup = sum(1 for yt in y_true if yt == lbl)
            p = tp / (tp + fp) if (tp + fp) > 0 else float(zero_division)
            r = tp / (tp + fn) if (tp + fn) > 0 else float(zero_division)
            f1 = (2 * p * r / (p + r)) if (p + r) > 0 else float(zero_division)
            precisions.append(p)
            recalls.append(r)
            f1s.append(f1)
            supports.append(sup)
        if average == "macro":
            return (
                sum(precisions) / len(labels),
                sum(recalls) / len(labels),
                sum(f1s) / len(labels),
                None,
            )
        return precisions, recalls, f1s, supports


from src.mde.constraint_ast import format_condition
from src.symbolic.data_conditions import compile_condition
from src.symbolic.verbalizer_roundtrip import (
    extract_clause_numeric_entities,
    verify_generic_numeric_entities,
)
from src.evaluation.justification_tree import filter_activity_events
from src.evaluation.grounded_auditor import (
    DeterministicAuditNarratorClient,
)


def run_generic_cegis_diagnostic(
    ast_dict: Dict[str, Any],
    retrieved_chunk: Dict[str, Any],
    log_df: Optional[pd.DataFrame] = None,
) -> Dict[str, str]:
    """
    Thuật toán Đối chiếu Thực thể Tổng quát (Generic Entity Matcher & Vacuity Checker):
    Tuyệt đối không dùng các lệnh `if art_id == ...` gõ cứng số liệu hay mớm lời.
    - Bước 1: Dùng Regex (`extract_clause_numeric_entities`) quét toàn bộ các con số và đơn vị trong văn bản luật
      của điều khoản đó (ví dụ tìm thấy: `[(14.0, 'days'), (200.0, 'EUR'), (75000.0, 'EUR')]`).
    - Bước 2: So sánh xem con số mà AI nộp lên (`time_max` hoặc `activation_val`) có nằm trong danh sách
      các con số được luật cho phép hay không, đồng thời kiểm tra độ rỗng (Vacuity) trên `log_df`.
    - Bước 3: Nếu không khớp, gửi phản hồi theo phong cách Trình biên dịch (Compiler Diagnostic) không mớm đáp án:
      `"[Diagnostic Mismatch]: Con số ... bạn chọn không xuất hiện trong văn bản luật của điều khoản này.
        Các mốc định lượng được luật đề cập gồm: {danh_sách_số_tìm_được}. Hãy đọc lại văn bản và tự hiệu chỉnh."`
    """
    clause_text = str(retrieved_chunk.get("text", ""))
    clause_lower = clause_text.lower()
    entities = extract_clause_numeric_entities(clause_text)
    formatted_entities = (
        ", ".join(f"[{int(v) if v.is_integer() else v}, '{u}']" for v, u in entities)
        if entities
        else "[]"
    )

    # 1. Kiểm tra ngữ cảnh loại trừ phạm vi (Scope Exclusion) hoặc điều khoản miễn trừ hoàn toàn bằng phân tích văn bản tổng quát
    val = ast_dict.get("activation_val")
    if isinstance(val, str) and "shall not apply" in clause_lower:
        tokens = [t.lower() for t in re.split(r"[^a-zA-Z0-9]+", val) if len(t) >= 4]
        if any(tok in clause_lower for tok in tokens):
            return {
                "verdict": "BASELESS",
                "diagnostic_feedback": (
                    f"[Diagnostic Scope Exclusion]: Giá trị '{val}' nằm trong danh mục bị loại trừ khỏi phạm vi áp dụng "
                    f"('shall not apply') của văn bản điều khoản này."
                ),
            }

    # (Đã bỏ 2026-11-09: một nhánh viết cứng câu "Articles 5 and 6 shall not apply" của Directive 2008/48/EC —
    #  quy tắc riêng cho một khoản luật của bộ đề, trái nguyên tắc "không if-else gõ cứng" của chính hàm này.)

    # 2. Bước 1–3: Đối chiếu các con số AI nộp lên (`time_max`, `activation_val`) với danh sách số Regex quét từ văn bản luật
    ok_num, num_verdict, num_diag = verify_generic_numeric_entities(ast_dict, retrieved_chunk)
    if not ok_num and num_verdict and num_diag:
        return {
            "verdict": num_verdict,
            "diagnostic_feedback": num_diag,
        }

    # 3. Kiểm tra nếu điều khoản có chứa mốc thời gian bắt buộc (days/months) nhưng AST bỏ sót `time_max=None`
    time_entities = [(v, u) for v, u in entities if u in ("days", "months")]
    if (
        ast_dict.get("template_name") in ("Response", "Chain Response", "Alternate Response")
        and ast_dict.get("time_max") is None
        and time_entities
    ):
        return {
            "verdict": "THRESHOLD_MISMATCH",
            "diagnostic_feedback": (
                f"[Diagnostic Mismatch]: Bạn đã chọn mẫu phản hồi '{ast_dict.get('template_name')}' nhưng bỏ trống time_max=None, "
                f"trong khi văn bản điều khoản có đề cập các mốc thời lượng: {formatted_entities}. "
                f"Hãy đọc lại văn bản và tự hiệu chỉnh."
            ),
        }

    # 4. Kiểm tra Độ rỗng (Vacuity Check) trên Log nếu có `log_df` — mọi loại điều kiện (số, chuỗi, Boolean,
    #    nhiều điều kiện 'and'), trước đây chỉ ngưỡng số nên bỏ sót VD case:year == '2018'.
    if log_df is not None and _activation_rows_matching(ast_dict, log_df) == 0:
        return {
            "verdict": "THRESHOLD_MISMATCH",
            "diagnostic_feedback": (
                f"[Diagnostic Vacuity]: Điều kiện kích hoạt '{_condition_text(ast_dict)}' không kích hoạt được trên bất kỳ "
                f"hồ sơ nào trong nhật ký sự kiện (0 activations). Các mốc định lượng được luật đề cập gồm: "
                f"{formatted_entities}. Hãy đọc lại văn bản và tự hiệu chỉnh."
            ),
        }

    return {"verdict": "EQUIVALENT", "diagnostic_feedback": "Semantically faithful."}


def _condition_text(ast_dict: Dict[str, Any]) -> str:
    conds = []
    if ast_dict.get("activation_attr"):
        conds.append(format_condition(ast_dict["activation_attr"], ast_dict.get("activation_op"),
                                      ast_dict.get("activation_val")))
    conds += [format_condition(c["attr"], c["op"], c["val"]) for c in ast_dict.get("extra_conditions") or []]
    return " and ".join(conds)


def _activation_rows_matching(ast_dict: Dict[str, Any], log_df: pd.DataFrame) -> Optional[int]:
    """
    Số sự kiện kích hoạt thoả mọi điều kiện (phía B với họ Precedence, như engine). None = không kiểm:
    không có điều kiện (độ rỗng do thiếu activity đã do classify_semantic_equivalence xử lý), hoặc có điều kiện
    'date' (cần dấu thời gian đã chuẩn hoá của engine — dùng LogGroundingChecker, src/symbolic/log_grounding.py).
    """
    cond_str = _condition_text(ast_dict)
    if not cond_str or "A.date" in cond_str:
        return None
    precedence = str(ast_dict.get("template_name", "")).endswith("Precedence")
    act = ast_dict.get("target_activity") if precedence and ast_dict.get("target_activity") else \
        ast_dict.get("activation_activity")
    rows = filter_activity_events(log_df, str(act or ""))
    if rows.empty:
        return None
    predicate = compile_condition(cond_str)
    return sum(1 for rec in rows.to_dict("records") if predicate(rec))


class BenchmarkExperimentLLMClient:
    """
    Client kiểm thử phục vụ Unit Test (`tests/test_unit_mock.py` & `tests/test_phase5_benchmark_evaluation.py`):
    Sử dụng trực tiếp `run_generic_cegis_diagnostic` (Generic Entity Matcher bằng Regex + Vacuity Check),
    hoàn toàn không chứa bất kỳ lệnh `if art_id == ...` gõ cứng số liệu nào.
    """

    def __init__(self, log_df: Optional[pd.DataFrame] = None) -> None:
        self.narrator = DeterministicAuditNarratorClient()
        self.log_df = log_df

    def generate_ast(
        self,
        chunk: Dict[str, Any],
        process_schema: Dict[str, Any],
        feedback: str = "",
        rule_meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        if rule_meta is not None:
            payload = rule_meta["raw_attempt_1"] if not feedback else rule_meta["repaired_attempt_2"]
            return json.dumps(payload, ensure_ascii=False)

        art_id = chunk.get("article_id", "Article 14(1)")
        return json.dumps(
            {
                "article_id": art_id,
                "template_name": "Response",
                "activation_activity": "O_Sent (mail and online)",
                "target_activity": "O_Returned",
                "time_min": 0,
                "time_max": 14,
                "time_unit": "d",
            },
            ensure_ascii=False,
        )

    def chat_json(
        self,
        prompt: Any,
        temperature: float = 0.0,
        ast_dict: Optional[Dict[str, Any]] = None,
        retrieved_chunk: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        if ast_dict is None or retrieved_chunk is None:
            return {"verdict": "EQUIVALENT", "diagnostic_feedback": "Verified."}
        return run_generic_cegis_diagnostic(ast_dict, retrieved_chunk, log_df=self.log_df)

    def chat(self, prompt_or_messages: Any, temperature: float = 0.0) -> str:
        return self.narrator.chat(prompt_or_messages, temperature=temperature)
