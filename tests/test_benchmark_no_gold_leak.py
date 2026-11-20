"""
Test chống rò rỉ đáp án (gold leak) vào đầu vào của hệ thống.

Đầu vào cho LLM phải là văn bản luật thật. Nếu thiếu văn bản luật của một rule, bộ đề phải
báo lỗi rõ ràng, tuyệt đối không được lấy `description` của rule gold làm văn bản luật.
"""

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.benchmark_builder import (  # noqa: E402
    BENCHMARK_RULES,
    build_normative_rule_benchmark,
)

CHUNKS_PATH = PROJECT_ROOT / "data" / "processed" / "directive_chunks.json"


def _load_chunks_by_id() -> dict:
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        return {c["article_id"]: c for c in json.load(f)}


def setUpModule() -> None:
    """Bộ BPIC2017 đang tạm vô hiệu (src/datasets.py); mở lại: $env:NSAI_ENABLE_BPIC2017 = "1"."""
    from src.datasets import skip_module_unless_bpic2017

    skip_module_unless_bpic2017()


@unittest.skipUnless(CHUNKS_PATH.exists(), "cần data/processed/directive_chunks.json")
class TestNoGoldLeak(unittest.TestCase):
    def test_missing_clause_raises_instead_of_using_gold_description(self) -> None:
        chunks = _load_chunks_by_id()
        chunks.pop("Article 14(1)")
        with self.assertRaises(KeyError) as ctx:
            build_normative_rule_benchmark(chunks)
        self.assertIn("Article 14(1)", str(ctx.exception))

    def test_no_rule_input_equals_its_gold_description(self) -> None:
        rules = build_normative_rule_benchmark(_load_chunks_by_id())
        leaked = [
            r["rule_id"] for r in rules
            if r["retrieved_chunk"]["text"].strip() == r["description"].strip()
        ]
        self.assertEqual(leaked, [])

    def test_every_rule_gets_a_clause(self) -> None:
        rules = build_normative_rule_benchmark(_load_chunks_by_id())
        self.assertEqual(len(rules), len(BENCHMARK_RULES))


if __name__ == "__main__":
    unittest.main()
