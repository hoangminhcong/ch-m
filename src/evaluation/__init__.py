"""
Evaluation, 3-Valued Safety Classification, Accountable Audit Trail & Benchmark Runner module (Bước 4 & Thực nghiệm RQ1-RQ3):
- Bước 4.1: evaluate_trace_safety_and_status (OVAS Value-Condition Separation <v, Φ> + RT4CHART 3-Valued Labeling)
- Bước 4.2: check_single_trace_semantics & build_justification_tree (xpSHACL Justification Tree + VERGE Minimal Correction)
- Bước 4.3: generate_accountable_explanation & verify_posthoc_grounding (CEUR Vol-4259 + Know Your Limits Grounding Guard)
- Thực nghiệm RQ1, RQ2, RQ3: build_normative_rule_benchmark, build_stratified_trace_benchmark, run_ablation_experiment

2026-11-21: mã BPIC2017 không dùng cho CAP (experiment_runner, benchmark_builder, justification_tree,
trace_safety_classifier, …) đã GỠ khỏi dự án (còn trong lịch sử git, commit 57757a4); chỉ còn grounded_auditor
(real_llm_client.chat dùng). Dòng mô tả Bước 4.1–4.3 / RQ1–RQ3 ở trên là lịch sử của gói.

Nạp LƯỜI (PEP 562, 2026-11-20, vấn đề A6): các tên dưới đây thuộc mã BPIC2017 cũ (experiment_runner, benchmark_builder
kéo theo sklearn…). Trước đây gói import sẵn tất cả, nên mọi module CAP (real_llm_client, cap_scoring…) đều kéo theo mã
cũ. Giờ chỉ nạp khi có người dùng đúng tên đó — `from src.evaluation import run_ablation_experiment` vẫn chạy như cũ.
"""

import importlib
from typing import Any

_EXPORTS = {
    "DeterministicAuditNarratorClient": "grounded_auditor",
    "generate_accountable_explanation": "grounded_auditor",
    "verify_posthoc_grounding": "grounded_auditor",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(f".{module}", __name__), name)
