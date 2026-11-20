"""
Evaluation, 3-Valued Safety Classification, Accountable Audit Trail & Benchmark Runner module (Bước 4 & Thực nghiệm RQ1-RQ3):
- Bước 4.1: evaluate_trace_safety_and_status (OVAS Value-Condition Separation <v, Φ> + RT4CHART 3-Valued Labeling)
- Bước 4.2: check_single_trace_semantics & build_justification_tree (xpSHACL Justification Tree + VERGE Minimal Correction)
- Bước 4.3: generate_accountable_explanation & verify_posthoc_grounding (CEUR Vol-4259 + Know Your Limits Grounding Guard)
- Thực nghiệm RQ1, RQ2, RQ3: build_normative_rule_benchmark, build_stratified_trace_benchmark, run_ablation_experiment

Nạp LƯỜI (PEP 562, 2026-11-20, vấn đề A6): các tên dưới đây thuộc mã BPIC2017 cũ (experiment_runner, benchmark_builder
kéo theo sklearn…). Trước đây gói import sẵn tất cả, nên mọi module CAP (real_llm_client, cap_scoring…) đều kéo theo mã
cũ. Giờ chỉ nạp khi có người dùng đúng tên đó — `from src.evaluation import run_ablation_experiment` vẫn chạy như cũ.
"""

import importlib
from typing import Any

_EXPORTS = {
    "evaluate_trace_safety_and_status": "trace_safety_classifier",
    "check_single_trace_semantics": "justification_tree",
    "build_justification_tree": "justification_tree",
    "DeterministicAuditNarratorClient": "grounded_auditor",
    "generate_accountable_explanation": "grounded_auditor",
    "verify_posthoc_grounding": "grounded_auditor",
    "build_normative_rule_benchmark": "benchmark_builder",
    "build_stratified_trace_benchmark": "benchmark_builder",
    "BenchmarkExperimentLLMClient": "experiment_runner",
    "check_layer1_and_layer2": "experiment_runner",
    "classify_semantic_equivalence": "experiment_runner",
    "evaluate_rq1_complexity_tiers": "experiment_runner",
    "run_ablation_experiment": "experiment_runner",
    "run_vanilla_rag_baseline": "experiment_runner",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(f".{module}", __name__), name)
