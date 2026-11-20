"""
Đăng ký bổ sung (docs/V2_DANG_KY_TRUOC.md, duyệt 2026-11-19):
  B1 chấm theo thành phần lồng nhau (issue ⊇ rule ⊇ application ⊇ conclusion)
  B4 cấu hình R: ngữ cảnh BM25, ngân sách ký tự khớp Y TỪNG KHOẢN, không lấy chính khoản / phiên bản năm khác
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from src.evaluation.cap_scoring import component_depth, component_rates, score_config  # noqa: E402
from src.neural.graph_context import (  # noqa: E402
    BM25ClauseIndex, LegalGraphIndex, graph_context_chunk, rag_context_chunk)


def _ast(t, a, b=None, cond=None):
    d = {"article_id": "x", "template_name": t, "activation_activity": a, "target_activity": b}
    if cond:
        d.update(activation_attr=cond[0], activation_op=cond[1], activation_val=cond[2])
    return d


GOLD = {"kind": "positive", "tier4": False, "gold": [_ast("Response", "A", "B", ("case:year", "==", 2016))]}


class TestComponentScoring(unittest.TestCase):
    def test_nested_levels(self) -> None:
        cases = [({"outcome": "BASELESS"}, 0),
                 ({"outcome": "RULE", "ast": _ast("Precedence", "A", "B")}, 1),      # nhận ra nghĩa vụ, sai mẫu
                 ({"outcome": "RULE", "ast": _ast("Response", "A", "C")}, 2),        # đúng mẫu, sai activity
                 ({"outcome": "RULE", "ast": _ast("Response", "A", "B")}, 3),        # thiếu điều kiện
                 ({"outcome": "RULE", "ast": _ast("Response", "A", "B", ("case:year", "==", "2016"))}, 4)]
        for pred, depth in cases:
            with self.subTest(pred=pred):
                self.assertEqual(component_depth(GOLD, pred), depth)

    def test_rates_with_wilson_and_in_score_config(self) -> None:
        golds = {"p1": GOLD, "p2": GOLD, "t1": {"kind": "trap", "tier4": False, "gold": []}}
        preds = {"p1": {"outcome": "RULE", "ast": _ast("Precedence", "A", "B")}, "p2": {"outcome": "BASELESS"},
                 "t1": {"outcome": "BASELESS"}}
        comp = component_rates(golds, preds)
        self.assertEqual([comp[lv]["correct"] for lv in ("issue", "rule", "application", "conclusion")], [1, 0, 0, 0])
        self.assertEqual(comp["issue"]["n"], 2)  # chỉ khoản positive
        self.assertIn("components", score_config(golds, preds))


GRAPH = {"nodes": [
    {"id": "D:§1(1)", "label": "Paragraph", "props": {"text": "Der Antrag nach Artikel 5 ist bis zum 15. Mai zu stellen.",
                                                       "years": [2016]}},
    {"id": "R1:Art5", "label": "Paragraph", "props": {"text": "The aid application shall be submitted by 15 May."}},
    {"id": "R1:Art6", "label": "Paragraph", "props": {"text": "Antrag Antrag Mai Mai stellen stellen " * 3}},
    {"id": "D:§1(1)@2017", "label": "Paragraph", "props": {"text": "Der Antrag ist bis zum 15. Mai zu stellen.",
                                                            "years": [2017]}},
    {"id": "D:§2", "label": "Paragraph", "props": {"text": "Antrag Mai stellen.", "years": [2015]}}],
    "edges": [{"source": "D:§1(1)", "target": "R1:Art5", "type": "REFERS_TO", "props": {"in_scope": True}}]}


class TestRagBaseline(unittest.TestCase):
    def setUp(self) -> None:
        self.index = LegalGraphIndex(GRAPH)
        self.bm25 = BM25ClauseIndex(self.index)
        self.chunk = {"node_id": "D:§1(1)", "text": GRAPH["nodes"][0]["props"]["text"], "years": [2016]}

    def test_budget_matches_graph_context_per_clause(self) -> None:
        y = graph_context_chunk(self.chunk, self.index)
        r = rag_context_chunk(self.chunk, self.index, self.bm25)
        self.assertLessEqual(abs(len(r["text"]) - len(y["text"])), 20)
        self.assertEqual(r["budget_chars"], len(y["text"]) - len(self.chunk["text"]))

    def test_excludes_itself_other_year_versions_and_disjoint_years(self) -> None:
        ranked = self.bm25.ranked(self.chunk)
        self.assertNotIn("D:§1(1)", ranked)
        self.assertNotIn("D:§1(1)@2017", ranked)   # phiên bản năm khác của chính khoản
        self.assertNotIn("D:§2", ranked)           # chỉ có năm 2015, không giao 2016
        self.assertEqual(ranked[0], "R1:Art6")     # BM25 thuần chữ: không biết cạnh dẫn chiếu

    def test_no_graph_context_means_no_rag_context(self) -> None:
        chunk = {"node_id": "R1:Art5", "text": "The aid application shall be submitted by 15 May."}
        r = rag_context_chunk(chunk, self.index, self.bm25)
        self.assertEqual((r["text"], r["context_refs"], r["budget_chars"]), (chunk["text"], [], 0))


class TestScoreCapB4(unittest.TestCase):
    def test_config_r_registered_and_eu_subset(self) -> None:
        import run_cap_generation
        import score_cap

        self.assertEqual(run_cap_generation.CONFIGS["R"]["rag"], "bm25")
        self.assertIn("R", score_cap.CONFIG_ORDER)
        subset = score_cap.eu_ref_subset()
        if subset:
            self.assertTrue(all(s.startswith("DE-") for s in subset))


if __name__ == "__main__":
    unittest.main()
