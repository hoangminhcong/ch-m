"""
v2 (docs/V2_DANG_KY_TRUOC.md mục 4, thành phần 7–8): tầng Pháp lý giàu hơn —
  DefinedTerm + DEFINES / USES_TERM: định nghĩa thuật ngữ (kể cả định nghĩa văn bản khác được dẫn nhập);
  ScopeCondition: khoản chỉ áp cho một số quốc gia thành viên nêu tên → ghi chú phạm vi cho log thuộc Đức.
Văn bản tổng hợp nhỏ; không đọc gold, không gọi API.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.legal_enrichment import (  # noqa: E402
    LOG_COUNTRY,
    build_legal_enrichment,
    definitions_context,
    extract_cap_definitions,
    scope_note,
)

DEFS_A = ('1. For the purposes of this Regulation: (a) "farmer" means a natural person whose holding is situated '
          'within the Union; (b) "holding" means all the units used for agricultural activities; '
          '(c) "agricultural activity" means: (i) production; (ii) maintenance; '
          '(h) "permanent grassland" (together referred to as "grassland") means land used to grow grasses.')
DEFS_B = ("1. The definitions in Article 4(1) of Regulation A shall apply. The following definitions shall also apply: "
          "(1) ‘beneficiary’ means a farmer receiving support; (2) ‘act’ means an individual requirement.")
CHUNKS = [
    {"node_id": "RA:Art4(1)", "doc_id": "RA", "article_title": "Definitions", "text": DEFS_A, "refs": []},
    {"node_id": "RB:Art2(1)", "doc_id": "RB", "article_title": "Definitions", "text": DEFS_B,
     "refs": [{"target": "RA:Art4(1)", "kind": "external", "in_scope": True}]},
    {"node_id": "RA:Art9(1)", "doc_id": "RA", "article_title": "Active farmer",
     "text": "Direct payments shall be granted to farmers whose agricultural activity is not marginal.", "refs": []},
    {"node_id": "RB:Art5", "doc_id": "RB", "article_title": "Claims",
     "text": "Each beneficiary shall declare every holding. Farmers shall act in good faith.", "refs": []},
    {"node_id": "RC:Art1", "doc_id": "RC", "article_title": "Other",
     "text": "The farmer shall be informed.", "refs": []},
]


class TestExtractDefinitions(unittest.TestCase):
    def test_letters_numbers_colon_and_parenthetical(self) -> None:
        terms = [t for t, _ in extract_cap_definitions(DEFS_A)]
        self.assertEqual(terms, ["farmer", "holding", "agricultural activity", "permanent grassland"])
        self.assertEqual([t for t, _ in extract_cap_definitions(DEFS_B)], ["beneficiary", "act"])

    def test_definition_text_stops_at_next_term(self) -> None:
        d = dict(extract_cap_definitions(DEFS_A))
        self.assertEqual(d["farmer"], "a natural person whose holding is situated within the Union")
        self.assertIn("(i) production", d["agricultural activity"])


class TestEnrichment(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.e = build_legal_enrichment(CHUNKS)

    def test_terms_scoped_by_document_with_incorporation(self) -> None:
        """RB dẫn nhập định nghĩa của RA:Art4(1) → khoản RB dùng được 'holding'; RC không có định nghĩa nào."""
        self.assertEqual(self.e["uses"]["RA:Art9(1)"], ["agricultural activity", "farmer"])
        self.assertEqual(self.e["uses"]["RB:Art5"], ["beneficiary", "farmer", "holding"])
        self.assertNotIn("RC:Art1", self.e["uses"])

    def test_definition_clause_does_not_use_itself_and_short_terms_skipped(self) -> None:
        self.assertNotIn("RA:Art4(1)", self.e["uses"])
        self.assertNotIn("act", self.e["uses"]["RB:Art5"])  # thuật ngữ < 4 ký tự: quá dễ khớp nhầm ('act')

    def test_graph_nodes_and_edges(self) -> None:
        kinds = {(e["type"]) for e in self.e["graph"]["edges"]}
        self.assertEqual(kinds, {"DEFINES", "USES_TERM"})
        self.assertTrue(any(n["label"] == "DefinedTerm" for n in self.e["graph"]["nodes"]))

    def test_context_block_has_definitions_and_budget(self) -> None:
        text = definitions_context("RB:Art5", self.e)
        self.assertIn("‘beneficiary’ means a farmer receiving support", text)
        self.assertIn("[RA:Art4(1)]", text)
        self.assertEqual(definitions_context("RC:Art1", self.e), "")


class TestArticleScopedDefinitions(unittest.TestCase):
    def test_article_scoped_definition_only_applies_in_same_article(self) -> None:
        chunks = [*CHUNKS,
                  {"node_id": "RA:Art30(11)", "doc_id": "RA", "article_title": "Reserve",
                   "text": 'For the purposes of this Article, (a) "young farmers" means persons under 40.', "refs": []},
                  {"node_id": "RA:Art30(2)", "doc_id": "RA", "article_title": "Reserve",
                   "text": "Young farmers shall have priority.", "refs": []},
                  {"node_id": "RA:Art12", "doc_id": "RA", "article_title": "Other",
                   "text": "Young farmers may apply.", "refs": []}]
        e = build_legal_enrichment(chunks)
        self.assertIn("young farmers", e["uses"]["RA:Art30(2)"])
        self.assertNotIn("young farmers", e["uses"].get("RA:Art12", []))


class TestGraphContextV2(unittest.TestCase):
    def test_v2_context_adds_definitions_and_scope_note_after_refs(self) -> None:
        from scripts.build_cap_legal_v2 import build
        from src.neural.graph_context import LegalGraphIndex, graph_context_chunk, graph_context_chunk_v2
        derog = {"node_id": "RB:Art9", "doc_id": "RB", "article_title": "Dates",
                 "text": "Each beneficiary shall apply by 15 May; Estonia may fix a later date.", "refs": []}
        chunks = [*CHUNKS, derog]
        v1 = {"nodes": [{"id": c["node_id"], "label": "Paragraph", "props": {"text": c["text"]}} for c in chunks],
              "edges": []}
        v2 = build(chunks, v1)
        ctx = graph_context_chunk_v2(derog, LegalGraphIndex(v2), v2)
        self.assertTrue(ctx["text"].startswith(graph_context_chunk(derog, LegalGraphIndex(v1))["text"]))
        self.assertIn("‘beneficiary’ means", ctx["text"])
        self.assertIn("recorded in Germany", ctx["text"])
        self.assertEqual((ctx["definitions"], ctx["scope_note"]), (["beneficiary"], True))


class TestEnrichmentAuditM1(unittest.TestCase):
    """Rà soát 2026-11-18 M1 (chỉ ảnh hưởng v2)."""

    def test_comma_after_quote_and_last_definition_cut_at_sentence(self) -> None:
        text = ('1. For the purposes of this Regulation: (a) "farmer", means a person; (b) "holding" means all units. '
                "Member States shall notify the Commission.")
        defs = dict(extract_cap_definitions(text))
        self.assertEqual(list(defs), ["farmer", "holding"])
        self.assertEqual(defs["holding"], "all units")

    def test_chapter_or_purpose_scoped_definitions_stay_in_article(self) -> None:
        chunks = [{"node_id": "RA:Art91(3)", "doc_id": "RA", "article_title": "Principle",
                   "text": 'For the purposes of this Title: (a) "requirement" means each statutory requirement.',
                   "refs": []},
                  {"node_id": "RA:Art12", "doc_id": "RA", "article_title": "Other",
                   "text": "This requirement applies.", "refs": []}]
        self.assertNotIn("RA:Art12", build_legal_enrichment(chunks)["uses"])

    def test_import_by_article_prefix(self) -> None:
        chunks = [{"node_id": "RB:Art2(1)", "doc_id": "RB", "article_title": "Terms",
                   "text": 'The following definitions apply: (a) "holding" means as in Regulation A.',
                   "refs": [{"target": "RA:Art4", "kind": "external", "in_scope": True}]},
                  {"node_id": "RA:Art4(1)", "doc_id": "RA", "article_title": "Definitions",
                   "text": 'For the purposes of this Regulation: (a) "farmer" means a natural person.', "refs": []},
                  {"node_id": "RB:Art9", "doc_id": "RB", "article_title": "X", "text": "Each farmer shall apply.",
                   "refs": []}]
        self.assertIn("farmer", build_legal_enrichment(chunks)["uses"]["RB:Art9"])

    def test_scope_note_only_for_derogations(self) -> None:
        self.assertEqual(scope_note("In the case of Croatia, the reference shall be the year 2015."), "")
        self.assertIn("Estonia", scope_note("By way of derogation, Estonia may fix a later date."))


class TestScopeNote(unittest.TestCase):
    def test_named_states_without_log_country(self) -> None:
        note = scope_note("By way of derogation, Estonia, Latvia and Sweden may fix a later date.")
        self.assertIn(LOG_COUNTRY, note)
        self.assertIn("Estonia, Latvia, Sweden", note)

    def test_no_note_when_log_country_named_or_none(self) -> None:
        self.assertEqual(scope_note("Germany and France may decide."), "")
        self.assertEqual(scope_note("Member States shall decide."), "")


if __name__ == "__main__":
    unittest.main()
