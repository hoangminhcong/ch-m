"""
Baseline 1: Vanilla RAG đọc thẳng lịch sử sự kiện của hồ sơ (BPIC2017).
Tách từ experiment_runner.py (2026-11-20, mục 7 — giảm kích thước file); nội dung hàm GIỮ NGUYÊN.
experiment_runner.py nhập lại các tên này nên mọi `from src.evaluation.experiment_runner import ...` cũ vẫn chạy.
"""

import json
from pathlib import Path
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




def serialize_trace_to_text(case_df: pd.DataFrame) -> str:
    """
    Chuyển đổi toàn bộ danh sách sự kiện, thuộc tính dữ liệu và mốc giờ của một hồ sơ vay (`case_df`)
    thành đoạn văn bản lịch sử thực thi để gửi lên LLM trong Baseline 1 (Vanilla RAG + LLM Direct QA).
    """
    if case_df.empty:
        return "Empty trace."

    case_id = str(case_df["case:concept:name"].iloc[0]) if "case:concept:name" in case_df.columns else "UnknownCase"
    req_amt = case_df["case:RequestedAmount"].dropna().iloc[0] if "case:RequestedAmount" in case_df.columns and not case_df["case:RequestedAmount"].dropna().empty else "N/A"
    loan_goal = case_df["case:LoanGoal"].dropna().iloc[0] if "case:LoanGoal" in case_df.columns and not case_df["case:LoanGoal"].dropna().empty else "N/A"

    lines = [
        f"Case ID: {case_id} | RequestedAmount: {req_amt} | LoanGoal: {loan_goal}",
        "Events Timeline:",
    ]
    for idx, (_, row) in enumerate(case_df.iterrows(), start=1):
        act = row.get("concept:name", "")
        ts = row.get("time:timestamp", "")
        extras = []
        for col in ("OfferedAmount", "CreditScore", "NumberOfTerms", "MonthlyCost"):
            if col in row and not pd.isna(row[col]):
                extras.append(f"{col}={row[col]}")
        extra_str = f" ({', '.join(extras)})" if extras else ""
        lines.append(f"  {idx}. [{ts}] {act}{extra_str}")

    return "\n".join(lines)


def run_vanilla_rag_baseline(
    benchmark_items: List[Dict[str, Any]],
    llm_client: Any = None,
    cache_file: str = "vanilla_rag_real_cache.json",
) -> Dict[str, Any]:
    """
    Baseline 1: Vanilla RAG + LLM Direct QA (Không dùng Declare4Py & Không có Tập điều kiện an toàn Φ).
    Đã xóa bỏ hoàn toàn các công thức modulo toán học nhân tạo (`idx % 8`, `idx % 3`).
    Gọi trực tiếp API của LLM thật (Groq / OpenAI) trên đoạn văn bản lịch sử sự kiện + văn bản điều khoản luật,
    và lưu toàn bộ phản hồi vào `vanilla_rag_real_cache.json` để không tốn quota khi chạy lại.
    """
    if llm_client is None:
        from src.evaluation.real_llm_client import RealLLMClient

        llm_client = RealLLMClient(cache_file=cache_file)

    cache_path = Path(cache_file)
    if not cache_path.is_absolute():
        cache_path = Path(__file__).resolve().parent.parent.parent / cache_path

    disk_cache: Dict[str, str] = {}
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                disk_cache = json.load(f)
        except Exception:
            disk_cache = {}

    y_true: List[str] = []
    y_pred: List[str] = []

    for idx, item in enumerate(benchmark_items, start=1):
        if idx % 10 == 0 or idx == len(benchmark_items):
            print(f"      [Vanilla RAG Baseline] Processing item {idx}/{len(benchmark_items)}...")
        gt = item["ground_truth_label"]
        chunk = item["retrieved_chunk"]
        case_df: pd.DataFrame = item["test_case_df"]
        y_true.append(gt)

        trace_text = serialize_trace_to_text(case_df)
        user_prompt = (
            "Dựa vào văn bản luật sau, hồ sơ này TUÂN THỦ (ENTAILED), VI PHẠM (CONTRADICTED) "
            "hay KHÔNG ĐỦ DỮ LIỆU (BASELESS)?\n\n"
            f"--- VĂN BẢN LUẬT ({chunk.get('article_id', '')}) ---\n"
            f"{chunk.get('text', '')}\n\n"
            f"--- LỊCH SỬ HỒ SƠ VAY (EVENT LOG TRACE) ---\n"
            f"{trace_text}\n\n"
            'Hãy trả lời bằng duy nhất một đối tượng JSON theo định dạng: '
            '{"label": "ENTAILED" | "CONTRADICTED" | "BASELESS", "rationale": "..."}'
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a direct legal compliance QA baseline. Read the legal clause and the process trace, "
                    "then classify the trace into strictly one of: ENTAILED, CONTRADICTED, or BASELESS. "
                    "Output valid JSON with key 'label'."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        # Kiểm tra cache riêng của Vanilla RAG (`vanilla_rag_real_cache.json`)
        import hashlib

        cache_key = hashlib.sha256(
            json.dumps(messages, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

        if cache_key in disk_cache:
            raw_res = disk_cache[cache_key]
        else:
            if hasattr(llm_client, "chat_json"):
                res_obj = llm_client.chat_json(messages, temperature=0.0)
                raw_res = res_obj if isinstance(res_obj, str) else json.dumps(res_obj, ensure_ascii=False)
            else:
                raw_res = llm_client.chat(messages, temperature=0.0)
            disk_cache[cache_key] = raw_res
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(disk_cache, f, indent=2, ensure_ascii=False)

        pred_label = "BASELESS"
        try:
            parsed = json.loads(raw_res) if isinstance(raw_res, str) else raw_res
            cand_lbl = str(parsed.get("label") or parsed.get("verdict") or "").upper().strip()
            if cand_lbl in ("ENTAILED", "CONTRADICTED", "BASELESS"):
                pred_label = cand_lbl
        except Exception:
            for valid_lbl in ("ENTAILED", "CONTRADICTED", "BASELESS"):
                if valid_lbl in str(raw_res).upper():
                    pred_label = valid_lbl
                    break

        y_pred.append(pred_label)

    labels = ["ENTAILED", "CONTRADICTED", "BASELESS"]
    p_macro, r_macro, f1_macro, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, average="macro", zero_division=0
    )
    return {
        "Configuration": "Baseline 1: Vanilla RAG + LLM Direct QA (Không dùng Declare4Py)",
        "Executable_Rate (%)": "N/A",
        "Eq_Rate (%)": "N/A",
        "Macro_Precision": round(float(p_macro), 4),
        "Macro_Recall": round(float(r_macro), 4),
        "Macro_F1": round(float(f1_macro), 4),
        "Cache_File": str(cache_path),
    }
