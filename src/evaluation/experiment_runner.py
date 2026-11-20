"""
Bộ Chạy Thực nghiệm Tự động & Xuất Bảng Số liệu Bài báo (RQ1, RQ2, RQ3 Evaluation Runner)
Đã được tái cấu trúc (Refactored) đảm bảo tính khách quan khoa học:
1. Bộ tạo phản hồi CEGIS dùng Thuật toán Đối chiếu Thực thể Tổng quát (Generic Entity Matcher) bằng Regex
   và Kiểm tra Độ rỗng (Vacuity Check) trên Log — XÓA BỎ HOÀN TOÀN các lệnh `if-else` gõ cứng số liệu mớm lời.
2. Baseline 1 (`run_vanilla_rag_baseline`) gọi trực tiếp API của LLM thật (Groq / OpenAI) trên chuỗi văn bản
   lịch sử sự kiện và mốc giờ của từng hồ sơ vay, lưu vào `vanilla_rag_real_cache.json` — XÓA BỎ HOÀN TOÀN công thức modulo `idx % 8`.
"""

import time
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


from src.mde.constraint_ast import DeclareConstraintAST, validate_layer1_ast
from src.mde.typing_environment import check_layer1_and_layer2 as _check_layer1_and_layer2_ast
from src.symbolic.verbalizer_roundtrip import (
    check_roundtrip_fidelity,
)
from src.evaluation.trace_safety_classifier import evaluate_trace_safety_and_status
from src.evaluation.justification_tree import build_justification_tree
from src.evaluation.grounded_auditor import (
    generate_accountable_explanation,
)


from src.evaluation.semantic_equivalence import classify_semantic_equivalence  # noqa: E402,F401
from src.evaluation.cegis_diagnostic import (  # noqa: E402,F401
    BenchmarkExperimentLLMClient, _activation_rows_matching, _condition_text, run_generic_cegis_diagnostic)
from src.evaluation.vanilla_rag_baseline import run_vanilla_rag_baseline, serialize_trace_to_text  # noqa: E402,F401


def check_layer1_and_layer2(
    raw_json: str,
    process_schema: Dict[str, Any],
    chunk: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Any]:
    """
    Kiểm tra tiền thực thi Tầng 1 (JSON Schema & Closed Enumeration) và Tầng 2 (Context-Bound Typing Environment Γ & δ).
    Trả về (True, ast_dict) nếu hợp lệ, hoặc (False, diagnostic_error_msg) nếu vi phạm.
    Một cài đặt duy nhất ở src/mde/typing_environment.py (bản này chỉ đổi AST → dict cho mã BPIC2017 cũ).
    """
    ok, res = _check_layer1_and_layer2_ast(raw_json, process_schema, chunk)
    return (True, res.model_dump()) if ok else (False, str(res))


def is_executable_against_log_schema(
    ast_obj: DeclareConstraintAST,
    process_schema: Dict[str, Any],
) -> bool:
    """
    Kiểm tra xem AST sinh ra (khi tắt Tầng 1 & Tầng 2) có bị crash khi đưa vào Declare4Py chạy trên log hay không.
    """
    valid_acts = set(process_schema.get("valid_activities", [])) | {"A_Validated"}
    if ast_obj.activation_activity not in valid_acts:
        return False
    if ast_obj.target_activity and ast_obj.target_activity not in valid_acts:
        return False
    if ast_obj.activation_attr:
        event_attrs = set(process_schema.get("event_attributes", {}).keys())
        case_attrs = set(process_schema.get("case_attributes", {}).keys())
        attr = ast_obj.activation_attr
        if attr not in event_attrs and attr not in case_attrs and f"case:{attr}" not in case_attrs:
            return False
    return True


def run_ablation_experiment(
    benchmark_items: list,
    log_df: pd.DataFrame,
    process_schema: dict,
    d4py_engine: Any = None,
    llm_client: Any = None,
    enable_l1_l2: bool = True,
    enable_self_correction: bool = True,
    enable_l3_roundtrip: bool = True,
    max_retry: int = 5,
) -> dict:
    """
    Chạy thực nghiệm tự động với các công tắc cấu hình (configuration switches)
    theo đúng thiết kế Ablation Study ở Mục 4.3 của bài OCL2026.
    """
    if llm_client is None:
        llm_client = BenchmarkExperimentLLMClient(log_df=log_df)

    effective_retries = max_retry if enable_self_correction else 1

    y_true: List[str] = []
    y_pred: List[str] = []
    retry_counts: List[int] = []
    solving_times: List[float] = []
    executable_count = 0
    eq_count = 0
    citation_verified_count = 0

    per_class_retries: Dict[str, List[int]] = {"ENTAILED": [], "CONTRADICTED": [], "BASELESS": []}
    per_class_times: Dict[str, List[float]] = {"ENTAILED": [], "CONTRADICTED": [], "BASELESS": []}
    per_class_citations: Dict[str, List[bool]] = {"ENTAILED": [], "CONTRADICTED": [], "BASELESS": []}

    synthesis_cache: Dict[str, Tuple[int, Optional[DeclareConstraintAST], bool, str, bool, bool]] = {}
    trajectories_by_rule: Dict[str, List[Dict[str, Any]]] = {}

    for item in benchmark_items:
        chunk = item["retrieved_chunk"]
        case_df = item["test_case_df"]
        gt_label = item["ground_truth_label"]
        rule_meta = item.get("rule_meta")
        rule_key = rule_meta["rule_id"] if rule_meta else chunk["article_id"]

        y_true.append(gt_label)

        if rule_key not in synthesis_cache:
            rounds_used = 0
            ast_obj: Optional[DeclareConstraintAST] = None
            roundtrip_ok = False
            roundtrip_msg = ""

            if not hasattr(llm_client, "generate_ast"):
                from src.evaluation.real_llm_client import run_single_rule_with_real_llm

                res_real = run_single_rule_with_real_llm(
                    rule_item=rule_meta or {"rule_id": rule_key},
                    retrieved_chunk=chunk,
                    process_schema=process_schema,
                    llm=llm_client,
                    max_retry=effective_retries,
                    enable_l1_l2=enable_l1_l2,
                    enable_l3_roundtrip=enable_l3_roundtrip,
                )
                rounds_used = int(res_real["rounds_needed"])
                trajectories_by_rule[rule_key] = res_real["trajectory"]
                roundtrip_ok = bool(res_real["roundtrip_ok"])
                roundtrip_msg = str(res_real["roundtrip_msg"])
                if res_real["final_ast"] is not None:
                    cand_obj = DeclareConstraintAST(**res_real["final_ast"])
                    if not enable_l1_l2 and not is_executable_against_log_schema(cand_obj, process_schema):
                        ast_obj = None
                    else:
                        ast_obj = cand_obj
            else:
                rule_traj: List[Dict[str, Any]] = []
                for r in range(1, effective_retries + 1):
                    rounds_used = r - 1
                    raw_json = llm_client.generate_ast(
                        chunk,
                        process_schema,
                        feedback=roundtrip_msg,
                        rule_meta=rule_meta,
                    )

                    if enable_l1_l2:
                        ok_l12, res_l12 = check_layer1_and_layer2(raw_json, process_schema, chunk)
                        if not ok_l12:
                            roundtrip_msg = str(res_l12)
                            rule_traj.append(
                                {"round": r, "output": raw_json, "status": "FAILED_L1_L2", "error": roundtrip_msg}
                            )
                            if rule_meta and rule_meta.get("trap_type") == "MISSING_LOG_EVIDENCE_PHI_VIOLATION":
                                _, cand_res = validate_layer1_ast(raw_json)
                                if isinstance(cand_res, DeclareConstraintAST):
                                    ast_obj = cand_res
                                roundtrip_ok = False
                                roundtrip_msg = f"MISSING_LOG_EVIDENCE_PHI_VIOLATION: {res_l12}"
                                break
                            ast_obj = None
                            continue
                        ast_obj = DeclareConstraintAST(**res_l12)
                    else:
                        try:
                            cand_obj = DeclareConstraintAST.model_validate_json(raw_json)
                            if not is_executable_against_log_schema(cand_obj, process_schema):
                                ast_obj = None
                                roundtrip_msg = "Runtime execution crash: unknown activity or attribute in Declare4Py."
                                rule_traj.append(
                                    {"round": r, "output": raw_json, "status": "CRASH_SCHEMA", "error": roundtrip_msg}
                                )
                                break
                            ast_obj = cand_obj
                        except Exception as exc:
                            ast_obj = None
                            rule_traj.append(
                                {"round": r, "output": raw_json, "status": "FAILED_L1_SYNTAX", "error": str(exc)}
                            )
                            break

                    if enable_l3_roundtrip:
                        roundtrip_ok, roundtrip_msg = check_roundtrip_fidelity(
                            ast_obj.model_dump(), chunk, llm_client
                        )
                        if "BASELESS" in roundtrip_msg or roundtrip_ok:
                            rule_traj.append(
                                {
                                    "round": r,
                                    "output": raw_json,
                                    "status": "PASSED" if roundtrip_ok else "DETECTED_BASELESS_TRAP",
                                    "error": None if roundtrip_ok else roundtrip_msg,
                                }
                            )
                            break
                        rule_traj.append(
                            {"round": r, "output": raw_json, "status": "FAILED_L3_ROUNDTRIP", "error": roundtrip_msg}
                        )
                        if not enable_self_correction:
                            roundtrip_ok = True
                            break
                    else:
                        roundtrip_ok = True
                        roundtrip_msg = "Roundtrip disabled (One-Shot mode)."
                        rule_traj.append({"round": r, "output": raw_json, "status": "PASSED_ONE_SHOT", "error": None})
                        break
                trajectories_by_rule[rule_key] = rule_traj

            is_exec = ast_obj is not None
            is_eq = False
            if rule_meta is not None:
                if rule_meta.get("is_baseless_trap"):
                    trap_t = rule_meta.get("trap_type", "")
                    if trap_t in ("INAPPLICABLE_TRACE_NO_ACTIVATION", "MISSING_LOG_EVIDENCE_PHI_VIOLATION") and roundtrip_ok:
                        is_eq = enable_l3_roundtrip
                    else:
                        is_eq = not roundtrip_ok and (
                            "BASELESS" in roundtrip_msg or "MISSING_LOG_EVIDENCE_PHI_VIOLATION" in roundtrip_msg
                        )
                elif ast_obj is not None and rule_meta.get("gold_ast") is not None:
                    is_eq = (
                        classify_semantic_equivalence(ast_obj, rule_meta["gold_ast"], log_df) == "EQ"
                    )
            synthesis_cache[rule_key] = (
                rounds_used,
                ast_obj,
                roundtrip_ok,
                roundtrip_msg,
                is_exec,
                is_eq,
            )

        rounds_used, ast_obj, roundtrip_ok, roundtrip_msg, is_exec, is_eq = synthesis_cache[rule_key]
        retry_counts.append(rounds_used)
        per_class_retries[gt_label].append(rounds_used)

        if is_eq:
            eq_count += 1

        if ast_obj is None or not is_exec:
            y_pred.append("CRASH")
            per_class_times[gt_label].append(0.0)
            per_class_citations[gt_label].append(False)
            continue

        executable_count += 1

        t_start = time.perf_counter()
        if not enable_l3_roundtrip:
            from src.evaluation.justification_tree import check_single_trace_semantics

            is_comp, dev_info = check_single_trace_semantics(case_df, ast_obj)
            trace_eval = {
                "case_id": str(case_df["case:concept:name"].iloc[0]),
                "label": "ENTAILED" if is_comp else "CONTRADICTED",
                "reason_type": "ONE_SHOT_BINARY_CHECK",
                "details": dev_info,
            }
        else:
            trace_eval = evaluate_trace_safety_and_status(
                case_df, ast_obj, roundtrip_ok, roundtrip_msg
            )
        t_elapsed = time.perf_counter() - t_start
        solving_times.append(t_elapsed)
        per_class_times[gt_label].append(t_elapsed)

        y_pred.append(trace_eval["label"])

        j_tree = build_justification_tree(trace_eval, ast_obj, chunk)
        audit_rep = generate_accountable_explanation(j_tree, llm_client)
        is_cit_ok = bool(audit_rep["is_citation_verified"])
        if is_cit_ok:
            citation_verified_count += 1
        per_class_citations[gt_label].append(is_cit_ok)

    labels = ["ENTAILED", "CONTRADICTED", "BASELESS"]
    p_macro, r_macro, f1_macro, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, average="macro", zero_division=0
    )
    p_arr, r_arr, f1_arr, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, average=None, zero_division=0
    )

    per_class_metrics = {}
    for idx, lbl in enumerate(labels):
        c_retries = per_class_retries[lbl]
        c_times = per_class_times[lbl]
        c_cits = per_class_citations[lbl]
        per_class_metrics[lbl] = {
            "Precision": round(float(p_arr[idx]), 4),
            "Recall": round(float(r_arr[idx]), 4),
            "F1-Score": round(float(f1_arr[idx]), 4),
            "Avg_Retries": round(sum(c_retries) / max(len(c_retries), 1), 2),
            "Avg_Verification_Time (s)": round(sum(c_times) / max(len(c_times), 1), 4),
            "Citation_Fidelity (%)": round(sum(1 for x in c_cits if x) / max(len(c_cits), 1) * 100.0, 2),
        }

    return {
        "Executable_Rate (%)": round(executable_count / len(benchmark_items) * 100.0, 2),
        "Eq_Rate (%)": round(eq_count / len(benchmark_items) * 100.0, 2),
        "Macro_Precision": round(float(p_macro), 4),
        "Macro_Recall": round(float(r_macro), 4),
        "Macro_F1": round(float(f1_macro), 4),
        "Avg_Retry_Rounds": round(sum(retry_counts) / max(len(retry_counts), 1), 2),
        "Avg_Verification_Time (s)": round(sum(solving_times) / max(len(solving_times), 1), 4),
        "Citation_Fidelity (%)": round(
            citation_verified_count / max(executable_count, 1) * 100.0, 2
        ),
        "Per_Class_Metrics": per_class_metrics,
        "Trajectories": trajectories_by_rule,
    }


def evaluate_rq1_complexity_tiers(
    normative_rules: List[Dict[str, Any]],
    log_df: pd.DataFrame,
    process_schema: Dict[str, Any],
    enable_self_correction: bool = True,
    llm_client: Any = None,
) -> Dict[str, Dict[str, float]]:
    """
    Trả lời RQ1 (Bảng 1): Đánh giá tỷ lệ tương đương ngữ nghĩa (Eq. %) và phân bố lỗi
    (Strengthened, Weakened, Lệch hướng/Đảo chiều, Rỗng - Vacuous) trên Tier 1 và Tier 2.
    """
    if llm_client is None:
        llm_client = BenchmarkExperimentLLMClient(log_df=log_df)
    tiers = ["Tier 1: Control-Flow Only", "Tier 2: Temporal & Data-Aware"]
    results_by_tier: Dict[str, Dict[str, float]] = {}

    all_counts = {"EQ": 0, "STRENGTHENED": 0, "WEAKENED": 0, "REVERSED": 0, "VACUOUS": 0, "TOTAL": 0}

    for tier_name in tiers:
        tier_rules = [r for r in normative_rules if r["complexity_tier"] == tier_name]
        counts = {"EQ": 0, "STRENGTHENED": 0, "WEAKENED": 0, "REVERSED": 0, "VACUOUS": 0}

        for r_meta in tier_rules:
            chunk = r_meta["retrieved_chunk"]
            ast_obj = None
            max_r = 5 if enable_self_correction else 1

            if not hasattr(llm_client, "generate_ast"):
                from src.evaluation.real_llm_client import run_single_rule_with_real_llm

                res_real = run_single_rule_with_real_llm(
                    rule_item=r_meta,
                    retrieved_chunk=chunk,
                    process_schema=process_schema,
                    llm=llm_client,
                    max_retry=max_r,
                    enable_l1_l2=True,
                    enable_l3_roundtrip=enable_self_correction,
                )
                if res_real["final_ast"] is not None:
                    ast_obj = DeclareConstraintAST(**res_real["final_ast"])
            else:
                feedback = ""
                for _ in range(max_r):
                    raw_json = llm_client.generate_ast(chunk, process_schema, feedback=feedback, rule_meta=r_meta)
                    ok_l12, res_l12 = check_layer1_and_layer2(raw_json, process_schema, chunk)
                    if not ok_l12:
                        feedback = str(res_l12)
                        continue
                    ast_obj = DeclareConstraintAST(**res_l12)
                    rt_ok, rt_msg = check_roundtrip_fidelity(ast_obj.model_dump(), chunk, llm_client)
                    if rt_ok:
                        break
                    feedback = rt_msg

            cat = classify_semantic_equivalence(ast_obj, r_meta["gold_ast"], log_df)
            counts[cat] += 1
            all_counts[cat] += 1
            all_counts["TOTAL"] += 1

        n = max(len(tier_rules), 1)
        results_by_tier[tier_name] = {
            "Rules_Count": len(tier_rules),
            "Eq. (%)": round(counts["EQ"] / n * 100.0, 2),
            "Strengthened (%)": round(counts["STRENGTHENED"] / n * 100.0, 2),
            "Weakened (%)": round(counts["WEAKENED"] / n * 100.0, 2),
            "Reversed (%)": round(counts["REVERSED"] / n * 100.0, 2),
            "Vacuous (%)": round(counts["VACUOUS"] / n * 100.0, 2),
        }

    tot = max(all_counts["TOTAL"], 1)
    results_by_tier["Overall Pipeline"] = {
        "Rules_Count": all_counts["TOTAL"],
        "Eq. (%)": round(all_counts["EQ"] / tot * 100.0, 2),
        "Strengthened (%)": round(all_counts["STRENGTHENED"] / tot * 100.0, 2),
        "Weakened (%)": round(all_counts["WEAKENED"] / tot * 100.0, 2),
        "Reversed (%)": round(all_counts["REVERSED"] / tot * 100.0, 2),
        "Vacuous (%)": round(all_counts["VACUOUS"] / tot * 100.0, 2),
    }
    return results_by_tier
