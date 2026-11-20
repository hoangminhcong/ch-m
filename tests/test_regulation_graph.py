"""
Test cho src/kg/regulation_graph_builder.py: tầng Pháp lý của KG cho bộ 4 Quy định CAP (BPIC2018),
dựng từ data/processed/cap_chunks.json (mã khoản có tiền tố văn bản, dẫn chiếu trong / ngoài văn bản).
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.regulation_graph_builder import build_regulation_graph  # noqa: E402
from src.kg.schema import EdgeType, NodeLabel  # noqa: E402

CHUNKS = [
    {"node_id": "R1306:Art75(1)", "doc_id": "R1306", "article_title": "Payment to beneficiaries",
     "text": "1. Payments ... referred to in Article 67(2) ...", "has_numeric_bound": True,
     "refs": [{"target": "R1306:Art67(2)", "kind": "internal", "in_scope": True}]},
    {"node_id": "R1306:Art75(2)", "doc_id": "R1306", "article_title": "Payment to beneficiaries",
     "text": "2. ... pursuant to Article 74 ... paragraph of Article 75(1)", "has_numeric_bound": False,
     "refs": [{"target": "R1306:Art74", "kind": "internal", "in_scope": True},
              {"target": "R1306:Art75(2)", "kind": "internal", "in_scope": True}]},
    {"node_id": "R1306:Art74", "doc_id": "R1306", "article_title": "Verification of eligibility conditions",
     "text": "In accordance with Article 59 ...", "has_numeric_bound": False, "refs": []},
    {"node_id": "R640:Art13(1)", "doc_id": "R640", "article_title": "Late submission",
     "text": "1. ... Article 78(b) of Regulation (EU) No 1306/2013 ... Article 28 of Regulation (EU) No 1305/2013",
     "has_numeric_bound": True,
     "refs": [{"target": "R1306:Art78", "kind": "external", "in_scope": True},
              {"target": "1305/2013:Art28", "kind": "external", "in_scope": False},
              {"target": "R1306:Art75(1)", "kind": "external", "in_scope": True}]},
]


class TestRegulationGraph(unittest.TestCase):
    def setUp(self) -> None:
        self.g = build_regulation_graph(CHUNKS)
        self.nodes = self.g.node_index()
        self.refs = {(e.source, e.target): e for e in self.g.edges_of_type(EdgeType.REFERS_TO)}

    def test_article_and_paragraph_nodes(self) -> None:
        self.assertEqual(self.nodes["R1306:Art75"].label, NodeLabel.ARTICLE)
        self.assertEqual(self.nodes["R1306:Art75"].props["title"], "Payment to beneficiaries")
        para = self.nodes["R1306:Art75(1)"]
        self.assertEqual(para.label, NodeLabel.PARAGRAPH)
        self.assertEqual(para.props["doc_id"], "R1306")
        self.assertTrue(para.props["has_numeric_bound"])

    def test_has_paragraph_edges(self) -> None:
        pairs = {(e.source, e.target) for e in self.g.edges_of_type(EdgeType.HAS_PARAGRAPH)}
        self.assertEqual(pairs, {("R1306:Art75", "R1306:Art75(1)"), ("R1306:Art75", "R1306:Art75(2)"),
                                 ("R640:Art13", "R640:Art13(1)")})

    def test_article_without_paragraphs_carries_text(self) -> None:
        art = self.nodes["R1306:Art74"]
        self.assertEqual(art.label, NodeLabel.ARTICLE)
        self.assertIn("Article 59", art.props["text"])

    def test_reference_to_existing_paragraph(self) -> None:
        edge = self.refs[("R640:Art13(1)", "R1306:Art75(1)")]
        self.assertEqual(edge.props["kind"], "external")

    def test_missing_paragraph_falls_back_to_article(self) -> None:
        self.assertIn(("R1306:Art75(1)", "R1306:Art67"), self.refs)
        self.assertFalse(self.nodes["R1306:Art67"].props["in_scope"])  # điều không có trong dữ liệu đã tách

    def test_out_of_scope_regulation_node(self) -> None:
        self.assertIn(("R640:Art13(1)", "1305/2013:Art28"), self.refs)
        self.assertFalse(self.nodes["1305/2013:Art28"].props["in_scope"])

    def test_reference_to_parsed_article(self) -> None:
        self.assertIn(("R1306:Art75(2)", "R1306:Art74"), self.refs)
        self.assertTrue(self.nodes["R1306:Art74"].props["in_scope"])

    def test_self_reference_dropped(self) -> None:
        self.assertNotIn(("R1306:Art75(2)", "R1306:Art75(2)"), self.refs)

    def test_cross_document_count(self) -> None:
        cross = [e for e in self.refs.values() if e.props["kind"] == "external" and e.props["in_scope"]]
        self.assertEqual(len(cross), 2)


if __name__ == "__main__":
    unittest.main()
