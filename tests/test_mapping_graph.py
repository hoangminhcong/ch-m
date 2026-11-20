"""
A4 — tầng Cầu nối của KG (src/kg/mapping_graph_builder.py): ontology loại giấy tờ đã duyệt → DocumentType, OF_DOCTYPE,
RELATED_DOCTYPE, MAPS_TO (khoản luật → loại giấy tờ, đăng ký trước v2 thành phần 9); tuân thủ metamodel trên hợp ba
đồ thị; và MAPS_TO trong KG trùng đúng với dòng gợi ý mà cấu hình Z đưa vào prompt.
"""

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_mapping_graph import union  # noqa: E402
from src.kg.mapping_graph_builder import build_mapping_graph, doctype_node_id  # noqa: E402
from src.kg.metamodel import validate_graph  # noqa: E402
from src.kg.ontology_mapping import doctype_mentions, load_ontology  # noqa: E402

ONTO = {"status": "approved", "approved_by": "reviewer", "approved_at": "2026-11-20",
        "doctypes": {
            "Payment application": {"meaning": "yearly aid application", "confidence": "high",
                                    "legal_terms": ["aid application", "payment claim"]},
            "Inspection": {"meaning": "on-the-spot checks", "confidence": "high",
                           "legal_terms": ["on-the-spot check"]}},
        "relations": [{"from": "Inspection", "to": "Payment application", "type": "checks", "confidence": "medium",
                       "years": [2016]}]}
ACT = {"case_count": 3, "event_count": 4, "case_ratio": 0.5}
PROCESS = {"nodes": [
    {"id": "Act:Payment application / Application / mail income", "label": "Activity",
     "props": {"name": "Payment application / Application / mail income", **ACT}},
    {"id": "Act:Inspection / On-Site / performed", "label": "Activity",
     "props": {"name": "Inspection / On-Site / performed", **ACT}},
    {"id": "Act:Other / X / y", "label": "Activity", "props": {"name": "Other / X / y", **ACT}}], "edges": []}
LEGAL = {"nodes": [
    {"id": "R1:Art1(1)", "label": "Paragraph", "props": {"doc_id": "R1", "in_scope": True,
                                                         "text": "Aid applications and on-the-spot checks."}},
    {"id": "R1:Art2(1)", "label": "Paragraph", "props": {"doc_id": "R1", "in_scope": True,
                                                         "text": "The Commission shall report."}},
    {"id": "R1:Art3", "label": "Article", "props": {"doc_id": "R1", "in_scope": False}}], "edges": []}


def _edges(g, kind):
    return [e for e in g["edges"] if e["type"] == kind]


class TestBuildMappingGraph(unittest.TestCase):
    def setUp(self) -> None:
        self.bridge = build_mapping_graph(ONTO, LEGAL, PROCESS)

    def test_unapproved_ontology_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            build_mapping_graph({**ONTO, "status": "draft"}, LEGAL, PROCESS)
        with self.assertRaises(ValueError):
            build_mapping_graph({**ONTO, "approved_by": None}, LEGAL, PROCESS)

    def test_maps_to_records_matched_terms_and_approver(self) -> None:
        maps = {(e["source"], e["target"]): e["props"] for e in _edges(self.bridge, "MAPS_TO")}
        self.assertEqual(maps[("R1:Art1(1)", doctype_node_id("Payment application"))],
                         {"approved_by": "reviewer", "terms": ["aid application"]})
        self.assertIn(("R1:Art1(1)", doctype_node_id("Inspection")), maps)
        self.assertFalse(any(src == "R1:Art2(1)" for src, _ in maps))  # không nhắc thuật ngữ → không có cạnh

    def test_activity_belongs_to_doctype_of_its_name_prefix(self) -> None:
        of = {e["source"]: e["target"] for e in _edges(self.bridge, "OF_DOCTYPE")}
        self.assertEqual(of["Act:Inspection / On-Site / performed"], doctype_node_id("Inspection"))
        self.assertEqual(self.bridge["meta"]["unmapped_activities"], ["Other / X / y"])

    def test_approved_relations_keep_years(self) -> None:
        (rel,) = _edges(self.bridge, "RELATED_DOCTYPE")
        self.assertEqual(rel["props"], {"kind": "checks", "confidence": "medium", "approved_by": "reviewer",
                                        "years": [2016]})

    def test_conforms_to_metamodel_on_union_only(self) -> None:
        self.assertEqual(validate_graph(union(LEGAL, PROCESS, self.bridge)), [])
        alone = validate_graph(self.bridge)
        self.assertTrue(any("node nguồn không tồn tại" in v for v in alone))

    def test_maps_to_without_approval_or_terms_violates_metamodel(self) -> None:
        bad = {**self.bridge, "edges": [{**e, "props": {}} if e["type"] == "MAPS_TO" else e
                                        for e in self.bridge["edges"]]}
        v = validate_graph(union(LEGAL, PROCESS, bad))
        self.assertTrue(any("'approved_by'" in x for x in v))
        self.assertTrue(any("'terms'" in x for x in v))


class TestBuiltBridgeMatchesPromptHint(unittest.TestCase):
    """MAPS_TO trong KG = loại giấy tờ mà dòng gợi ý của Z nêu cho đúng khoản đó (không lệch KG ↔ prompt)."""

    def test_cap_and_de(self) -> None:
        onto = load_ontology(PROJECT_ROOT / "data" / "review" / "bpic2018_ontology.json")
        if onto is None:
            self.skipTest("ontology chưa duyệt")
        for ds in ("cap", "de"):
            items = PROJECT_ROOT / "data" / "review" / f"{ds}_item_candidates.json"
            bridge = PROJECT_ROOT / "data" / "processed" / f"{ds}_mapping_graph.json"
            if not (items.exists() and bridge.exists()):
                continue
            maps = {}
            for e in json.loads(bridge.read_text(encoding="utf-8"))["edges"]:
                if e["type"] == "MAPS_TO":
                    maps.setdefault(e["source"], set()).add(e["target"][len("Doc:"):])
            for clause in json.loads(items.read_text(encoding="utf-8")):
                with self.subTest(ds=ds, clause=clause["node_id"]):
                    self.assertEqual(set(doctype_mentions(clause["text"], onto)), maps.get(clause["node_id"], set()))


class TestBridgeIsSingleSource(unittest.TestCase):
    """Lúc sinh, gợi ý Z và kiểm N4 đọc MAPS_TO từ KG cầu nối (load_bridge) — phải trùng từng chữ với cách tính cũ từ
    ontology, để đổi nguồn không đổi prompt nào."""

    def test_bridge_hint_and_doctypes_equal_ontology_route(self) -> None:
        from src.kg.mapping_graph_builder import load_bridge
        from src.kg.ontology_mapping import generation_hint, hint_from_doctypes
        onto = load_ontology(PROJECT_ROOT / "data" / "review" / "bpic2018_ontology.json")
        if onto is None:
            self.skipTest("ontology chưa duyệt")
        for ds in ("cap", "de"):
            bridge_path = PROJECT_ROOT / "data" / "processed" / f"{ds}_mapping_graph.json"
            items_path = PROJECT_ROOT / "data" / "review" / f"{ds}_item_candidates.json"
            if not (bridge_path.exists() and items_path.exists()):
                continue
            bridge = load_bridge(json.loads(bridge_path.read_text(encoding="utf-8")))
            for c in json.loads(items_path.read_text(encoding="utf-8")):
                with self.subTest(ds=ds, clause=c["node_id"]):
                    self.assertEqual(hint_from_doctypes(bridge.doctypes(c["node_id"]), bridge.meanings),
                                     generation_hint(c["text"], onto))
                    self.assertEqual(bridge.doctypes(c["node_id"]), frozenset(doctype_mentions(c["text"], onto)))

    def test_toy_bridge(self) -> None:
        from src.kg.mapping_graph_builder import load_bridge
        bridge = load_bridge(build_mapping_graph(ONTO, LEGAL, PROCESS))
        self.assertEqual(bridge.doctypes("R1:Art1(1)"), frozenset({"Payment application", "Inspection"}))
        self.assertEqual(bridge.doctypes("R1:Art2(1)"), frozenset())
        self.assertEqual(bridge.meanings["Inspection"], "on-the-spot checks")


if __name__ == "__main__":
    unittest.main()
