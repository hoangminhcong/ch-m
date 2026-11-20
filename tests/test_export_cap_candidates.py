"""
Test cho scripts/export_cap_candidates.py: phiếu gán nhãn Phần B cho bộ CAP (BPIC2018 + 4 Quy định).

Đợt 1 = mọi khoản có dẫn chiếu sang văn bản khác TRONG bộ; Đợt 2 = mẫu ngẫu nhiên phân tầng theo văn bản
từ phần còn lại (seed cố định). Không lọc theo phạm vi hay từ ngữ nghĩa vụ: người gán nhãn quyết định.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_cap_candidates import (  # noqa: E402
    allocate,
    build_markdown,
    build_vocabulary_markdown,
    is_cross_document,
    referenced_texts,
    select_rounds,
)


def _chunk(node_id, text="Text.", refs=(), numeric=False):
    return {"node_id": node_id, "doc_id": node_id.split(":")[0], "article_title": "T",
            "text": text, "has_numeric_bound": numeric, "refs": list(refs)}


EXT_IN = {"target": "R1306:Art78", "kind": "external", "in_scope": True}
EXT_OUT = {"target": "1305/2013:Art28", "kind": "external", "in_scope": False}
INTERNAL = {"target": "R809:Art2(1)", "kind": "internal", "in_scope": True}

CHUNKS = [
    _chunk("R1306:Art78(1)", "1. Deadline A."),
    _chunk("R1306:Art78(2)", "2. Deadline B."),
    _chunk("R809:Art2(1)", "1. Internal target."),
    _chunk("R809:Art13(1)", "1. By 15 May, see Article 78 of Regulation (EU) No 1306/2013.", [EXT_IN], True),
    _chunk("R809:Art14", "Refers inside.", [INTERNAL]),
    _chunk("R640:Art5", "Refers outside the bundle.", [EXT_OUT]),
]


class TestCrossDocument(unittest.TestCase):
    def test_external_in_scope_is_cross_document(self) -> None:
        self.assertTrue(is_cross_document(CHUNKS[3]))

    def test_internal_or_out_of_bundle_is_not(self) -> None:
        self.assertFalse(is_cross_document(CHUNKS[4]))
        self.assertFalse(is_cross_document(CHUNKS[5]))


class TestReferencedTexts(unittest.TestCase):
    def setUp(self) -> None:
        self.index = {c["node_id"]: c for c in CHUNKS}

    def test_article_reference_joins_all_paragraphs(self) -> None:
        refs = referenced_texts(CHUNKS[3], self.index)
        self.assertEqual(refs[0]["target"], "R1306:Art78")
        self.assertEqual(refs[0]["text"], "1. Deadline A.\n\n2. Deadline B.")
        self.assertTrue(refs[0]["found"])

    def test_paragraph_reference_exact(self) -> None:
        self.assertEqual(referenced_texts(CHUNKS[4], self.index)[0]["text"], "1. Internal target.")

    def test_out_of_bundle_reference_has_no_text(self) -> None:
        ref = referenced_texts(CHUNKS[5], self.index)[0]
        self.assertFalse(ref["in_scope"])
        self.assertFalse(ref["found"])

    def test_missing_in_scope_target_is_flagged(self) -> None:
        chunk = _chunk("R809:Art1", refs=[{"target": "R1307:Art99", "kind": "external", "in_scope": True}])
        ref = referenced_texts(chunk, self.index)[0]
        self.assertTrue(ref["in_scope"])
        self.assertFalse(ref["found"])


class TestAllocate(unittest.TestCase):
    def test_largest_remainder_sums_to_total(self) -> None:
        sizes = {"R1306": 322, "R1307": 283, "R640": 63, "R809": 146}
        self.assertEqual(allocate(sizes, 60), {"R1306": 24, "R1307": 21, "R640": 4, "R809": 11})

    def test_never_more_than_available(self) -> None:
        alloc = allocate({"A": 1, "B": 100}, 50)
        self.assertLessEqual(alloc["A"], 1)
        self.assertEqual(sum(alloc.values()), 50)

    def test_sample_larger_than_population(self) -> None:
        self.assertEqual(allocate({"A": 2, "B": 3}, 10), {"A": 2, "B": 3})


class TestSelectRounds(unittest.TestCase):
    def setUp(self) -> None:
        self.chunks = CHUNKS + [_chunk(f"R1307:Art{i}") for i in range(1, 21)]

    def test_round1_is_every_cross_document_paragraph(self) -> None:
        round1, _ = select_rounds(self.chunks, 5, seed=1)
        self.assertEqual([c["node_id"] for c in round1], ["R809:Art13(1)"])

    def test_round2_excludes_round1_and_has_requested_size(self) -> None:
        round1, round2 = select_rounds(self.chunks, 5, seed=1)
        self.assertEqual(len(round2), 5)
        self.assertFalse({c["node_id"] for c in round1} & {c["node_id"] for c in round2})

    def test_seed_makes_sample_reproducible(self) -> None:
        a = [c["node_id"] for c in select_rounds(self.chunks, 5, seed=7)[1]]
        b = [c["node_id"] for c in select_rounds(self.chunks, 5, seed=7)[1]]
        self.assertEqual(a, b)

    def test_rounds_sorted_by_document_then_number(self) -> None:
        _, round2 = select_rounds(self.chunks, 26, seed=1)
        ids = [c["node_id"] for c in round2 if c["doc_id"] == "R1307"]
        self.assertEqual(ids[:3], ["R1307:Art1", "R1307:Art2", "R1307:Art3"])


class TestMarkdown(unittest.TestCase):
    def setUp(self) -> None:
        index = {c["node_id"]: c for c in CHUNKS}
        self.round1 = [CHUNKS[3]]
        self.round2 = [CHUNKS[5]]
        self.md = build_markdown(self.round1, self.round2, index, seed=42)

    def test_answer_lines_for_every_paragraph(self) -> None:
        self.assertIn("R809:Art13(1): **Quan sát được:** ___", self.md)
        self.assertIn("R640:Art5: **Quan sát được:** ___", self.md)

    def test_referenced_text_included(self) -> None:
        self.assertIn("Khoản được dẫn chiếu: <b>R1306:Art78</b>", self.md)
        self.assertIn("2. Deadline B.", self.md)

    def test_round_headings_and_seed(self) -> None:
        self.assertIn("Đợt 1", self.md)
        self.assertIn("Đợt 2", self.md)
        self.assertIn("seed = 42", self.md)

    def test_no_gold_or_opinion(self) -> None:
        for word in ("gold", "Gold", "đáp án đúng"):
            self.assertNotIn(word, self.md)


class TestVocabulary(unittest.TestCase):
    GRAPH = {"nodes": [
        {"id": "Act:main / mail income", "label": "Activity",
         "props": {"name": "main / mail income", "event_count": 9, "case_count": 5, "case_ratio": 0.5}},
        {"id": "Act:entitlement / finish payment", "label": "Activity",
         "props": {"name": "entitlement / finish payment", "event_count": 3, "case_count": 2, "case_ratio": 0.2}},
        {"id": "Attr:case:young farmer", "label": "Attribute",
         "props": {"name": "case:young farmer", "level": "case", "type": "boolean", "values": ["false", "true"]}},
        {"id": "Attr:case:area", "label": "Attribute",
         "props": {"name": "case:area", "level": "case", "type": "number", "min": 0.0, "max": 9.5}},
    ], "edges": []}

    def test_lists_activities_and_attributes(self) -> None:
        md = build_vocabulary_markdown(self.GRAPH)
        self.assertIn("`main / mail income`", md)
        self.assertIn("`case:young farmer`", md)
        self.assertIn("0.0 – 9.5", md)

    def test_activities_sorted_by_name(self) -> None:
        md = build_vocabulary_markdown(self.GRAPH)
        self.assertLess(md.index("entitlement / finish payment"), md.index("main / mail income"))


if __name__ == "__main__":
    unittest.main()
