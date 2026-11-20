"""
Test cho M1 Legal Graph Builder (T1.2): dựng tầng Pháp lý của KG từ directive_chunks.json.
"""

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.legal_graph_builder import (  # noqa: E402
    build_legal_graph,
    extract_definitions,
    extract_references,
    find_mentions,
    paragraph_node_id,
    parse_paragraph_id,
)
from src.kg.schema import EdgeType, KnowledgeGraph, NodeLabel  # noqa: E402

CHUNKS_PATH = PROJECT_ROOT / "data" / "processed" / "directive_chunks.json"


class TestParagraphIds(unittest.TestCase):
    def test_parses_article_with_paragraph(self) -> None:
        self.assertEqual(parse_paragraph_id("Article 14(1)"), (14, 1))

    def test_parses_article_without_paragraph(self) -> None:
        self.assertEqual(parse_paragraph_id("Article 7"), (7, None))

    def test_builds_stable_node_ids(self) -> None:
        self.assertEqual(paragraph_node_id(14, 1), "Art14(1)")
        self.assertEqual(paragraph_node_id(7, None), "Art7")


class TestExtractReferences(unittest.TestCase):
    def test_single_article_reference(self) -> None:
        text = "information in accordance with Article 10, if that day is later"
        self.assertEqual(extract_references(text, current_article=14), [(10, None)])

    def test_article_with_paragraph_reference(self) -> None:
        text = "as referred to in Article 10(2) and Article 15."
        self.assertEqual(extract_references(text, 14), [(10, 2), (15, None)])

    def test_expands_ranges_and_lists(self) -> None:
        text = "only Articles 1 to 3, 18 and 20 shall apply."
        self.assertEqual(
            extract_references(text, 5),
            [(1, None), (2, None), (3, None), (18, None), (20, None)],
        )

    def test_range_containing_current_article_drops_only_itself(self) -> None:
        self.assertEqual(extract_references("Articles 1 to 3 apply", 2), [(1, None), (3, None)])

    def test_intra_article_paragraphs_resolve_to_current_article(self) -> None:
        text = "the information referred to in paragraphs 1 and 3 shall be given"
        self.assertEqual(extract_references(text, 6), [(6, 1), (6, 3)])

    def test_paragraph_of_other_article_resolves_to_that_article(self) -> None:
        text = "the information referred to in paragraph 2 of Article 10 shall"
        self.assertEqual(extract_references(text, 14), [(10, 2)])

    def test_paragraph_of_this_article_stays_local(self) -> None:
        self.assertEqual(extract_references("paragraph 1 of this Article", 6, 3), [(6, 1)])

    def test_skips_references_to_other_legal_acts(self) -> None:
        text = (
            "complies with Article 3(3) of Directive 2002/65/EC, and "
            "Articles 6 and 7 of Directive 2002/65/ EC and Article 5 of Council Directive"
        )
        self.assertEqual(extract_references(text, 5), [])

    def test_skips_self_reference(self) -> None:
        self.assertEqual(extract_references("see Article 14", current_article=14), [])


class TestDefinitionsAndMentions(unittest.TestCase):
    ART3 = (
        "For the purposes of this Directive, the following definitions shall apply: "
        "(a) ‘consumer’ means a natural person who is acting outside his trade; "
        "(b) ‘credit agreement’ means an agreement whereby a creditor grants credit; "
        "(c) ‘credit’ means money lent."
    )

    def test_extracts_quoted_definitions(self) -> None:
        defs = extract_definitions(self.ART3)
        self.assertEqual([d[0] for d in defs], ["consumer", "credit agreement", "credit"])
        self.assertTrue(defs[0][1].startswith("a natural person"))

    def test_mentions_prefer_longest_term(self) -> None:
        terms = ["credit", "credit agreement", "consumer"]
        found = find_mentions("The consumer may withdraw from the credit agreement.", terms)
        self.assertEqual(found, {"consumer", "credit agreement"})


class TestBuildLegalGraph(unittest.TestCase):
    CHUNKS = [
        {"article_id": "Article 3", "article_title": "Definitions",
         "text": TestDefinitionsAndMentions.ART3, "has_numeric_bound": False},
        {"article_id": "Article 10(1)", "article_title": "Information in credit agreements",
         "text": "1. Credit agreements shall be drawn up on paper.", "has_numeric_bound": False},
        {"article_id": "Article 14(1)", "article_title": "Right of withdrawal",
         "text": "1. The consumer shall have 14 calendar days to withdraw from the credit "
                 "agreement, from the day the consumer receives information in accordance "
                 "with Article 10.", "has_numeric_bound": True},
    ]

    def setUp(self) -> None:
        self.graph = build_legal_graph(self.CHUNKS)

    def test_graph_is_referentially_valid(self) -> None:
        self.assertEqual(self.graph.validate(), [])

    def test_creates_article_and_paragraph_nodes(self) -> None:
        index = self.graph.node_index()
        self.assertEqual(index["Art14"].label, NodeLabel.ARTICLE)
        self.assertEqual(index["Art14(1)"].label, NodeLabel.PARAGRAPH)
        self.assertTrue(index["Art14(1)"].props["has_numeric_bound"])

    def test_every_article_and_paragraph_has_in_scope_flag(self) -> None:
        legal_nodes = [
            n for n in self.graph.nodes if n.label in (NodeLabel.ARTICLE, NodeLabel.PARAGRAPH)
        ]
        missing = [n.id for n in legal_nodes if "in_scope" not in n.props]
        self.assertEqual(missing, [])
        self.assertTrue(self.graph.node_index()["Art14(1)"].props["in_scope"])

    def test_links_reference_to_whole_article(self) -> None:
        refs = {e.target for e in self.graph.out_edges("Art14(1)", EdgeType.REFERS_TO)}
        self.assertEqual(refs, {"Art10"})

    def test_links_definitions_and_mentions(self) -> None:
        defined = {e.target for e in self.graph.out_edges("Art3", EdgeType.DEFINES)}
        self.assertIn("Concept:credit agreement", defined)
        mentioned = {e.target for e in self.graph.out_edges("Art14(1)", EdgeType.MENTIONS)}
        self.assertEqual(mentioned, {"Concept:consumer", "Concept:credit agreement"})

    def test_roundtrips_through_json(self) -> None:
        restored = KnowledgeGraph.from_dict(json.loads(json.dumps(self.graph.to_dict())))
        self.assertEqual(len(restored.nodes), len(self.graph.nodes))
        self.assertEqual(len(restored.edges), len(self.graph.edges))


from src.datasets import skip_unless_bpic2017  # noqa: E402  (bộ BPIC2017 đang tạm vô hiệu)


@skip_unless_bpic2017
@unittest.skipUnless(CHUNKS_PATH.exists(), "cần data/processed/directive_chunks.json")
class TestRealDirective(unittest.TestCase):
    def setUp(self) -> None:
        with open(CHUNKS_PATH, encoding="utf-8") as f:
            self.graph = build_legal_graph(json.load(f))

    def test_real_graph_is_valid(self) -> None:
        self.assertEqual(self.graph.validate(), [])

    def test_article_14_1_refers_to_article_10(self) -> None:
        refs = {e.target for e in self.graph.out_edges("Art14(1)", EdgeType.REFERS_TO)}
        self.assertIn("Art10", refs)

    def test_article_3_defines_many_concepts(self) -> None:
        self.assertGreaterEqual(len(self.graph.out_edges("Art3", EdgeType.DEFINES)), 10)

    def test_no_edge_to_external_directive_article(self) -> None:
        refs = {e.target for e in self.graph.out_edges("Art5(2)", EdgeType.REFERS_TO)}
        self.assertNotIn("Art3(3)", refs)


if __name__ == "__main__":
    unittest.main()
