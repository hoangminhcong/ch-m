"""
Test cho scripts/export_item_candidates.py: phiếu soạn câu mới (rà lại Directive + ứng viên Tier 4).
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_item_candidates import (  # noqa: E402
    build_candidates,
    build_markdown,
    has_numeric_bound,
    is_obligation,
    referenced_texts,
)

GRAPH = {
    "nodes": [
        {"id": "Art2", "label": "Article", "props": {"number": 2, "in_scope": True}},
        {"id": "Art2(2)", "label": "Paragraph", "props": {"text": "2. This Directive shall not apply to X.", "in_scope": True}},
        {"id": "Art10", "label": "Article", "props": {"number": 10, "in_scope": True}},
        {"id": "Art10(1)", "label": "Paragraph", "props": {"text": "1. Agreements shall be on paper.", "in_scope": True}},
        {"id": "Art10(2)", "label": "Paragraph", "props": {"text": "2. Agreements shall specify Y.", "in_scope": True}},
        {"id": "Art14", "label": "Article", "props": {"number": 14, "in_scope": True}},
        {"id": "Art14(1)", "label": "Paragraph", "props": {
            "text": "1. The consumer shall have 14 calendar days, from information under Article 10.", "in_scope": True}},
        {"id": "Art14(2)", "label": "Paragraph", "props": {"text": "2. The consumer may withdraw as in paragraph 1.", "in_scope": True}},
        {"id": "Art14(3)", "label": "Paragraph", "props": {"text": "3. The creditor shall act as in paragraph 1.", "in_scope": True}},
        {"id": "Art15", "label": "Article", "props": {"number": 15, "in_scope": True}},
        {"id": "Art15(1)", "label": "Paragraph", "props": {"text": "1. The creditor shall inform.", "in_scope": True}},
        {"id": "Art25", "label": "Article", "props": {"number": 25, "in_scope": False}},
    ],
    "edges": [
        {"source": "Art14(1)", "target": "Art10", "type": "REFERS_TO", "props": {}},
        {"source": "Art14(2)", "target": "Art14(1)", "type": "REFERS_TO", "props": {}},
        {"source": "Art14(3)", "target": "Art14(1)", "type": "REFERS_TO", "props": {}},
        {"source": "Art15(1)", "target": "Art25", "type": "REFERS_TO", "props": {}},
    ],
}
USED = {"Art14(1)": ["R15"]}


def setUpModule() -> None:
    """Bộ BPIC2017 đang tạm vô hiệu (src/datasets.py); mở lại: $env:NSAI_ENABLE_BPIC2017 = "1"."""
    from src.datasets import skip_module_unless_bpic2017

    skip_module_unless_bpic2017()


class TestHeuristics(unittest.TestCase):
    def test_obligation_words(self) -> None:
        self.assertTrue(is_obligation("The creditor shall inform the consumer."))
        self.assertTrue(is_obligation("Member States must ensure ..."))
        self.assertFalse(is_obligation("The consumer may withdraw."))
        self.assertFalse(is_obligation("This Directive shall not apply to X."))

    def test_numeric_bounds_digits_and_words(self) -> None:
        self.assertTrue(has_numeric_bound("within 14 calendar days"))
        self.assertTrue(has_numeric_bound("exceeding a period of one month"))
        self.assertTrue(has_numeric_bound("not exceed EUR 10 000"))
        self.assertTrue(has_numeric_bound("may not exceed 1 % of the amount"))
        self.assertFalse(has_numeric_bound("Article 10 and paragraph 2"))


class TestCandidates(unittest.TestCase):
    def setUp(self) -> None:
        self.cands = build_candidates(GRAPH, USED, excluded_articles={2})
        self.by_id = {c["node_id"]: c for c in self.cands}

    def test_keeps_only_obligations_outside_excluded_articles(self) -> None:
        self.assertEqual(set(self.by_id), {"Art10(1)", "Art10(2)", "Art14(1)", "Art14(3)", "Art15(1)"})

    def test_cross_article_references_come_first(self) -> None:
        self.assertEqual(self.cands[0]["node_id"], "Art14(1)")
        self.assertEqual(self.cands[0]["ref_group"], "cross")
        self.assertEqual(self.by_id["Art14(3)"]["ref_group"], "intra")
        self.assertEqual(self.by_id["Art10(1)"]["ref_group"], "none")

    def test_whole_article_reference_expands_to_its_paragraphs(self) -> None:
        refs = referenced_texts(GRAPH, "Art14(1)")
        self.assertEqual([r["target"] for r in refs], ["Art10"])
        self.assertIn("1. Agreements shall be on paper.", refs[0]["text"])
        self.assertIn("2. Agreements shall specify Y.", refs[0]["text"])

    def test_out_of_scope_reference_is_marked_not_counted_as_cross(self) -> None:
        refs = referenced_texts(GRAPH, "Art15(1)")
        self.assertFalse(refs[0]["in_scope"])
        self.assertEqual(self.by_id["Art15(1)"]["ref_group"], "none")

    def test_flags_numeric_and_previous_use(self) -> None:
        self.assertTrue(self.by_id["Art14(1)"]["has_numeric"])
        self.assertEqual(self.by_id["Art14(1)"]["used_by"], ["R15"])


class TestMarkdown(unittest.TestCase):
    def setUp(self) -> None:
        self.md = build_markdown(build_candidates(GRAPH, USED, excluded_articles={2}))

    def test_has_section_per_candidate_with_referenced_text(self) -> None:
        self.assertIn("## Art14(1)", self.md)
        self.assertIn("1. Agreements shall be on paper.", self.md)

    def test_has_answer_template_line_per_candidate(self) -> None:
        lines = [ln for ln in self.md.splitlines() if ln.startswith("Art") and "**Quan sát được:**" in ln]
        self.assertEqual(len(lines), 5)

    def test_does_not_reveal_any_gold_constraint(self) -> None:
        for leaked in ("Precedence(", "Response(", "O_Returned", "O_Accepted"):
            self.assertNotIn(leaked, self.md)


if __name__ == "__main__":
    unittest.main()
