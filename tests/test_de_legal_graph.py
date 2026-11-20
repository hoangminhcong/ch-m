"""
Đồ thị Pháp lý cho tập Đức: đồ thị CAP v1 (không đổi) + node khoản tiếng Đức + REFERS_TO tới điều khoản EU
(khoản nếu có, không thì Article) và tới § Đức của phiên bản trùng năm nhiều nhất. Ngữ cảnh Y đọc được qua
LegalGraphIndex như bộ CAP.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.de_legal_graph import build_de_legal_graph  # noqa: E402
from src.neural.graph_context import LegalGraphIndex, graph_context_chunk  # noqa: E402

CAP = {"nodes": [{"id": "R640:Art11", "label": "Article", "props": {"text": ""}},
                 {"id": "R640:Art11(1)", "label": "Paragraph", "props": {"text": "The single application …"}}],
       "edges": [{"source": "R640:Art11", "target": "R640:Art11(1)", "type": "HAS_PARAGRAPH", "props": {}}]}
DE = [
    {"node_id": "DE-InVeKoSV:§7(1)@2016", "years": [2016], "text": "Antrag (2016) nach Artikel 11 …",
     "refs": [{"target": "R640:Art11", "in_scope": True, "kind": "eu"},
              {"target": "DE-InVeKoSV:§19", "in_scope": True, "kind": "internal"},
              {"target": "EU-1303/2013:Art2", "in_scope": False, "kind": "eu"}]},
    {"node_id": "DE-InVeKoSV:§19(1)@2015", "years": [2015], "text": "LE 2015 (1)", "refs": []},
    {"node_id": "DE-InVeKoSV:§19(1)@2016-2017", "years": [2016, 2017], "text": "LE 2016 (1)", "refs": []},
    {"node_id": "DE-InVeKoSV:§19(2)@2016-2017", "years": [2016, 2017], "text": "LE 2016 (2)", "refs": []},
]


class TestDeLegalGraph(unittest.TestCase):
    def setUp(self) -> None:
        self.g = build_de_legal_graph(DE, CAP)

    def test_cap_graph_kept_and_german_nodes_added(self) -> None:
        ids = {n["id"] for n in self.g["nodes"]}
        self.assertTrue({"R640:Art11", "R640:Art11(1)", "DE-InVeKoSV:§7(1)@2016"} <= ids)

    def test_section_reference_resolves_to_same_year_version(self) -> None:
        targets = [e["target"] for e in self.g["edges"]
                   if e["type"] == "REFERS_TO" and e["source"] == "DE-InVeKoSV:§7(1)@2016"]
        self.assertEqual(targets, ["R640:Art11", "DE-InVeKoSV:§19(1)@2016-2017", "DE-InVeKoSV:§19(2)@2016-2017",
                                   "EU-1303/2013:Art2"])

    def test_context_reads_eu_and_german_text_and_skips_out_of_scope(self) -> None:
        ctx = graph_context_chunk(DE[0], LegalGraphIndex(self.g))
        self.assertIn("The single application", ctx["text"])
        self.assertIn("LE 2016 (2)", ctx["text"])
        self.assertNotIn("LE 2015", ctx["text"])
        self.assertEqual(ctx["skipped_refs"], ["EU-1303/2013:Art2"])
        self.assertEqual(ctx["years"], [2016])


class TestVersionLinking(unittest.TestCase):
    def test_multi_year_source_links_every_overlapping_version_once(self) -> None:
        """Rà soát M3: khoản 2015–2017 dẫn §19 → nối cả phiên bản 2015 lẫn 2016–2017; không cạnh trùng."""
        src = {**DE[0], "node_id": "DE-InVeKoSV:§7(1)", "years": [2015, 2016, 2017],
               "refs": [{"target": "DE-InVeKoSV:§19(1)", "in_scope": True, "kind": "internal"},
                        {"target": "DE-InVeKoSV:§19(1)", "in_scope": True, "kind": "internal"}]}
        g = build_de_legal_graph([src, *DE[1:]], CAP)
        targets = [e["target"] for e in g["edges"] if e["type"] == "REFERS_TO" and e["source"] == src["node_id"]]
        self.assertEqual(targets, ["DE-InVeKoSV:§19(1)@2015", "DE-InVeKoSV:§19(1)@2016-2017"])


class TestMissingAbsatzFallback(unittest.TestCase):
    def test_missing_absatz_falls_back_to_whole_section(self) -> None:
        """Rà soát MEDIUM-4: '§19(5)' không có khoản riêng → dùng cả §19 (phiên bản cùng năm) thay vì bỏ ngữ cảnh."""
        src = {**DE[0], "refs": [{"target": "DE-InVeKoSV:§19(5)", "in_scope": True, "kind": "internal"}]}
        g = build_de_legal_graph([src, *DE[1:]], CAP)
        targets = [e["target"] for e in g["edges"] if e["type"] == "REFERS_TO" and e["source"] == src["node_id"]]
        self.assertEqual(targets, ["DE-InVeKoSV:§19(1)@2016-2017", "DE-InVeKoSV:§19(2)@2016-2017"])
        from scripts.export_de_candidates import _de_text
        self.assertIn("LE 2016 (2)", _de_text("DE-InVeKoSV:§19(5)", [2016], DE))


class TestGermanProfile(unittest.TestCase):
    def test_only_source_description_changes(self) -> None:
        """Tập Đức: prompt nêu đúng nguồn văn bản (luật thực thi Đức, tiếng Đức); không thêm quy tắc nào."""
        from src.symbolic.domain_profiles import CAP_PROFILE, CAP_PROFILE_NO_DUTY, german_profile
        for base in (CAP_PROFILE, CAP_PROFILE_NO_DUTY):
            de = german_profile(base)
            self.assertIn("InVeKoS-Verordnung", de.generator_system)
            self.assertNotIn("Regulations (EU) No 1306/2013, 1307/2013, 640/2014, 809/2014) into",
                             de.generator_system)
            self.assertIn("German", de.judge_clause_phrase)
            self.assertEqual((de.examples, de.judge_context, de.abstain_enabled),
                             (base.examples, base.judge_context, base.abstain_enabled))
            self.assertEqual(de.name, base.name + "-de")
            tail = base.generator_system.split("into a formal DECLARE constraint", 1)[1]
            self.assertTrue(de.generator_system.endswith(tail))

    def test_generation_uses_german_profile_only_for_german_dataset(self) -> None:
        from scripts.run_cap_generation import profile_for
        self.assertEqual(profile_for("Y", "cap").name, "cap")
        self.assertEqual(profile_for("Y", "de").name, "cap-de")
        self.assertEqual(profile_for("Y-noDuty", "de").name, "cap-noduty-de")


if __name__ == "__main__":
    unittest.main()
