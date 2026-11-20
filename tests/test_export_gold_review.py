"""
Test cho scripts/export_gold_review.py: phiếu gán nhãn gold phải chép đúng nguyên văn luật
từ dữ liệu (không chép tay) và phủ đủ mọi rule.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_gold_review import build_review_markdown  # noqa: E402

RULES = [
    {"rule_id": "R01", "tier": "Tier1_ControlFlow", "article_id": "Article 8(1)",
     "template": "Precedence", "act_a": "A", "act_b": "B", "attr": None, "op": None,
     "val": None, "time_max": None, "is_trap": False, "description": "mô tả R01"},
    {"rule_id": "R02", "tier": "Tier3_BaselessTrap", "article_id": "Annex I(II)",
     "template": "Existence", "act_a": "A", "act_b": None, "attr": "X", "op": ">=",
     "val": 12, "time_max": None, "is_trap": True, "description": "mô tả R02"},
]
CHUNKS = {"Article 8(1)": {"article_id": "Article 8(1)", "text": "1. Member States shall ensure ..."}}
ANNEX = {"Annex I(II)": "(d) if there is no fixed timetable ..."}
NOTES = {
    "R01": {"verdict": "XEM", "suggest": "SỬA", "issue": "vấn đề 1", "fix_hint": "gợi ý 1"},
    "R02": {"verdict": "OK", "suggest": "GIỮ", "issue": "vấn đề 2", "fix_hint": ""},
}
DEV = {"R01"}


def setUpModule() -> None:
    """Bộ BPIC2017 đang tạm vô hiệu (src/datasets.py); mở lại: $env:NSAI_ENABLE_BPIC2017 = "1"."""
    from src.datasets import skip_module_unless_bpic2017

    skip_module_unless_bpic2017()


class TestBuildReviewMarkdown(unittest.TestCase):
    def setUp(self) -> None:
        self.md = build_review_markdown(RULES, CHUNKS, NOTES, DEV, hardcoded_texts=ANNEX)

    def test_contains_every_rule_section(self) -> None:
        self.assertIn("## R01", self.md)
        self.assertIn("## R02", self.md)

    def test_copies_law_text_verbatim_from_data(self) -> None:
        self.assertIn("1. Member States shall ensure ...", self.md)

    def test_marks_hardcoded_text_as_not_from_parsed_directive(self) -> None:
        self.assertIn("(d) if there is no fixed timetable ...", self.md)
        self.assertIn("viết cứng", self.md)

    def test_decision_table_has_one_row_per_rule(self) -> None:
        rows = [line for line in self.md.splitlines() if line.startswith("| R0")]
        self.assertEqual(len(rows), 2)

    def test_shows_split_and_assistant_opinion_separately(self) -> None:
        self.assertIn("dev", self.md)
        self.assertIn("heldout_test", self.md)
        self.assertIn("vấn đề 1", self.md)

    def test_missing_note_raises(self) -> None:
        with self.assertRaises(KeyError):
            build_review_markdown(RULES, CHUNKS, {"R01": NOTES["R01"]}, DEV, hardcoded_texts=ANNEX)

    def test_missing_law_text_raises(self) -> None:
        with self.assertRaises(KeyError):
            build_review_markdown(RULES, {}, NOTES, DEV, hardcoded_texts=ANNEX)


class TestBlindSheet(unittest.TestCase):
    """Phiếu cho người gán nhãn độc lập: không được lộ ý kiến của trợ lý (tránh dẫn dắt)."""

    def setUp(self) -> None:
        self.md = build_review_markdown(RULES, CHUNKS, {}, DEV, hardcoded_texts=ANNEX, blind=True)

    def test_hides_assistant_opinion(self) -> None:
        for leaked in ("vấn đề 1", "gợi ý 1", "SỬA |", "Trợ lý đề xuất", "Nhận xét sơ bộ"):
            self.assertNotIn(leaked, self.md)

    def test_still_has_law_gold_and_decision_table(self) -> None:
        self.assertIn("1. Member States shall ensure ...", self.md)
        self.assertIn("## R01", self.md)
        rows = [line for line in self.md.splitlines() if line.startswith("| R0")]
        self.assertEqual(len(rows), 2)

    def test_asks_for_confidence(self) -> None:
        self.assertIn("Độ chắc chắn", self.md)


if __name__ == "__main__":
    unittest.main()
