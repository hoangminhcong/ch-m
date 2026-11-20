"""
Phân loại tương đương ngữ nghĩa ràng buộc sinh ra ↔ gold (BPIC2017, RQ1–RQ3).
Tách từ experiment_runner.py (2026-11-20, mục 7 — giảm kích thước file); nội dung hàm GIỮ NGUYÊN.
experiment_runner.py nhập lại các tên này nên mọi `from src.evaluation.experiment_runner import ...` cũ vẫn chạy.
"""

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


from src.mde.constraint_ast import DeclareConstraintAST
from src.evaluation.justification_tree import filter_activity_events


def classify_semantic_equivalence(
    cand_ast: Optional[DeclareConstraintAST],
    gold_ast: Optional[Dict[str, Any]],
    log_df: pd.DataFrame,
) -> str:
    """
    Phân loại kết quả tổng hợp ràng buộc vào đúng 5 cột của Bảng 1 (RQ1 - theo Mục 3.4.6 & 4.2 của OCL2026):
    - 'EQ': Khớp hoàn toàn về mẫu DECLARE, tên hoạt động, toán tử số học và ngưỡng thời gian/tiền tệ.
    - 'STRENGTHENED': Quá chặt (VD: sinh Chain Precedence thay vì Precedence, hoặc thu hẹp ngưỡng).
    - 'WEAKENED': Quá lỏng (VD: bỏ sót giới hạn thời gian time_max hoặc nới lỏng time_max).
    - 'REVERSED': Lệch hướng / Đảo chiều (nhầm lẫn giữa Precedence và Response hoặc sai hoạt động).
    - 'VACUOUS': Quy tắc rỗng (không kích hoạt được trên bất kỳ hồ sơ nào trong log).
    """
    if cand_ast is None or gold_ast is None:
        return "REVERSED"

    act_rows = filter_activity_events(log_df, cand_ast.activation_activity)
    if act_rows.empty:
        return "VACUOUS"
    if cand_ast.activation_attr:
        attr_col = cand_ast.activation_attr
        if attr_col not in act_rows.columns and f"case:{attr_col}" in act_rows.columns:
            attr_col = f"case:{attr_col}"
        if attr_col in act_rows.columns:
            col = act_rows[attr_col].dropna()
            op = cand_ast.activation_op
            if (
                pd.api.types.is_numeric_dtype(col)
                and isinstance(cand_ast.activation_val, (int, float))
                and not isinstance(cand_ast.activation_val, bool)
            ):
                try:
                    val = float(cand_ast.activation_val)
                    if op == ">=" and (col >= val).sum() == 0:
                        return "VACUOUS"
                    if op == ">" and (col > val).sum() == 0:
                        return "VACUOUS"
                    if op == "<=" and (col <= val).sum() == 0:
                        return "VACUOUS"
                except Exception:
                    pass

    same_acts = (
        cand_ast.activation_activity == gold_ast["activation_activity"]
        and cand_ast.target_activity == gold_ast.get("target_activity")
    )
    is_swapped_acts = (
        cand_ast.activation_activity == gold_ast.get("target_activity")
        and cand_ast.target_activity == gold_ast["activation_activity"]
    )
    same_tpl = cand_ast.template_name == gold_ast["template_name"]
    same_attr = (
        cand_ast.activation_attr == gold_ast.get("activation_attr")
        and cand_ast.activation_op == gold_ast.get("activation_op")
        and cand_ast.activation_val == gold_ast.get("activation_val")
    )
    same_time = cand_ast.time_max == gold_ast.get("time_max")

    # 1. Tương đương ngữ nghĩa hoàn toàn
    if same_acts and same_tpl and same_attr and same_time:
        return "EQ"

    # 2. Đảo chiều thứ tự hoạt động hoặc phân cực phủ định
    if is_swapped_acts:
        return "REVERSED"

    cand_neg = "Not " in cand_ast.template_name or cand_ast.template_name in ("Absence",)
    gold_neg = "Not " in gold_ast["template_name"] or gold_ast["template_name"] in ("Absence",)
    if cand_neg != gold_neg:
        return "REVERSED"

    if {"Precedence", "Response"} == {cand_ast.template_name, gold_ast["template_name"]}:
        return "REVERSED"

    # 3. Phân cấp độ mạnh của mẫu Declare chuẩn (Template Subsumption Hierarchy)
    RESPONSE_HIERARCHY = ["Responded Existence", "Response", "Alternate Response", "Chain Response"]
    PRECEDENCE_HIERARCHY = ["Responded Existence", "Precedence", "Alternate Precedence", "Chain Precedence"]

    if same_acts:
        if cand_ast.template_name in RESPONSE_HIERARCHY and gold_ast["template_name"] in RESPONSE_HIERARCHY:
            cand_idx = RESPONSE_HIERARCHY.index(cand_ast.template_name)
            gold_idx = RESPONSE_HIERARCHY.index(gold_ast["template_name"])
            if cand_idx > gold_idx:
                return "STRENGTHENED"
            elif cand_idx < gold_idx:
                return "WEAKENED"

        if cand_ast.template_name in PRECEDENCE_HIERARCHY and gold_ast["template_name"] in PRECEDENCE_HIERARCHY:
            cand_idx = PRECEDENCE_HIERARCHY.index(cand_ast.template_name)
            gold_idx = PRECEDENCE_HIERARCHY.index(gold_ast["template_name"])
            if cand_idx > gold_idx:
                return "STRENGTHENED"
            elif cand_idx < gold_idx:
                return "WEAKENED"

    # 4. So sánh thuộc tính dữ liệu và thời hạn thời gian khi cùng mẫu hoặc tương thích
    if same_acts and same_tpl:
        # Candidate có thêm điều kiện thuộc tính mà Gold không yêu cầu -> Quá chặt
        if cand_ast.activation_attr is not None and gold_ast.get("activation_attr") is None:
            return "STRENGTHENED"
        # Candidate bỏ mất điều kiện thuộc tính mà Gold yêu cầu -> Quá lỏng
        if cand_ast.activation_attr is None and gold_ast.get("activation_attr") is not None:
            return "WEAKENED"

        # Candidate có thêm giới hạn thời gian mà Gold không có -> Quá chặt
        if cand_ast.time_max is not None and gold_ast.get("time_max") is None:
            return "STRENGTHENED"
        # Candidate bỏ giới hạn thời gian mà Gold yêu cầu -> Quá lỏng
        if cand_ast.time_max is None and gold_ast.get("time_max") is not None:
            return "WEAKENED"

        # Cả hai cùng có giới hạn thời gian
        if cand_ast.time_max is not None and gold_ast.get("time_max") is not None:
            if cand_ast.time_max < gold_ast["time_max"]:
                return "STRENGTHENED"
            elif cand_ast.time_max > gold_ast["time_max"]:
                return "WEAKENED"

        # Thuộc tính khác nhau nhưng cùng tồn tại
        if cand_ast.activation_attr != gold_ast.get("activation_attr"):
            return "STRENGTHENED"

    if same_acts:
        return "STRENGTHENED" if (cand_ast.activation_attr or cand_ast.time_max) else "WEAKENED"

    return "REVERSED"
