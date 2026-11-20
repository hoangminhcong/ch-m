"""
Metamodel KG (src/kg/metamodel.py): thế giới đóng — lớp / quan hệ / cặp lớp không khai báo, thiếu thuộc tính bắt buộc,
sai miền, cạnh treo, nguồn gốc định nghĩa sai đều là vi phạm; và mọi đồ thị thật đã dựng phải tuân thủ.
"""

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.metamodel import drift, observed_triples, validate_graph  # noqa: E402

PARA = {"id": "R1:Art1(1)", "label": "Paragraph", "props": {"doc_id": "R1", "text": "1. Text.", "title": "T",
                                                             "has_numeric_bound": False, "in_scope": True}}
ART = {"id": "R1:Art2", "label": "Article", "props": {"doc_id": "R1", "in_scope": True, "title": "Scope"}}
TERM = {"id": "Term:R1:Art1(1):farmer", "label": "DefinedTerm",
        "props": {"term": "farmer", "definition": "a person", "source": "R1:Art1(1)", "scope": "document"}}
REF = {"source": "R1:Art1(1)", "target": "R1:Art2", "type": "REFERS_TO",
       "props": {"cited_as": "R1:Art2", "kind": "internal", "in_scope": True}}


def _g(nodes, edges):
    return {"nodes": nodes, "edges": edges}


class TestMetamodelViolations(unittest.TestCase):
    def test_valid_graph_has_no_violation(self) -> None:
        defines = {"source": "R1:Art1(1)", "target": TERM["id"], "type": "DEFINES", "props": {}}
        self.assertEqual(validate_graph(_g([PARA, ART, TERM], [REF, defines])), [])

    def test_undeclared_class_relation_and_endpoint(self) -> None:
        v = validate_graph(_g([PARA, ART, {"id": "X", "label": "LegalConcept", "props": {}}],
                              [{**REF, "type": "AMENDS"},
                               {"source": "R1:Art2", "target": "R1:Art1(1)", "type": "HAS_PARAGRAPH", "props": {}},
                               {"source": "R1:Art1(1)", "target": "R1:Art2", "type": "HAS_PARAGRAPH", "props": {}}]))
        self.assertTrue(any("lớp không có trong metamodel" in x for x in v))
        self.assertTrue(any("quan hệ không có trong metamodel" in x for x in v))
        self.assertTrue(any("lớp nguồn không được phép = Paragraph" in x for x in v))
        self.assertEqual(sum("không được phép" in x for x in v), 2)  # Paragraph→Article: cả nguồn lẫn đích sai

    def test_missing_and_ill_typed_properties(self) -> None:
        bad = {**PARA, "props": {"doc_id": "R1", "in_scope": "yes"}}
        v = validate_graph(_g([bad, ART], [{**REF, "props": {"kind": "other", "in_scope": True}}]))
        self.assertTrue(any("thiếu thuộc tính bắt buộc 'text'" in x for x in v))
        self.assertTrue(any("'in_scope' sai kiểu" in x for x in v))
        self.assertTrue(any("thiếu thuộc tính bắt buộc 'cited_as'" in x for x in v))
        self.assertTrue(any("'kind' sai kiểu" in x for x in v))

    def test_closed_world_rejects_undeclared_property(self) -> None:
        v = validate_graph(_g([{**ART, "props": {**ART["props"], "secret": 1}}], []))
        self.assertEqual(v, ["node R1:Art2 [Article]: thuộc tính không khai báo 'secret'"])

    def test_dangling_edge_only_when_out_of_scope(self) -> None:
        out = {**REF, "target": "1305/2013:Art28", "props": {**REF["props"], "kind": "external", "in_scope": False}}
        self.assertEqual(validate_graph(_g([PARA], [out])), [])
        inside = {**REF, "target": "R1:Art99"}
        self.assertTrue(any("node đích không tồn tại" in x for x in validate_graph(_g([PARA], [inside]))))

    def test_in_scope_article_needs_title_placeholder_may_be_empty(self) -> None:
        placeholder = {"id": "R1:Art99", "label": "Article", "props": {"doc_id": "R1", "in_scope": False}}
        self.assertEqual(validate_graph(_g([placeholder], [])), [])
        empty = {"id": "R1:Art98", "label": "Article", "props": {"doc_id": "R1", "in_scope": True}}
        self.assertTrue(any("không có title" in x for x in validate_graph(_g([empty], []))))

    def test_definitional_provenance(self) -> None:
        wrong = {"source": "R1:Art2", "target": TERM["id"], "type": "DEFINES", "props": {}}
        self.assertTrue(any("nguồn gốc sai" in x for x in validate_graph(_g([PARA, ART, TERM], [wrong]))))

    def test_maps_to_requires_approval(self) -> None:
        """MAPS_TO = khoản luật → loại giấy tờ (đăng ký trước v2, thành phần 9), chỉ từ ontology đã duyệt."""
        doc = {"id": "Doc:Inspection", "label": "DocumentType",
               "props": {"name": "Inspection", "meaning": "on-the-spot checks", "confidence": "high"}}
        edge = {"source": PARA["id"], "target": doc["id"], "type": "MAPS_TO", "props": {}}
        v = validate_graph(_g([PARA, doc], [edge]))
        self.assertTrue(any("'approved_by'" in x for x in v))
        ok = {**edge, "props": {"approved_by": "reviewer", "terms": ["on-the-spot check"]}}
        self.assertEqual(validate_graph(_g([PARA, doc], [ok])), [])
        act = {"id": "Act:A", "label": "Activity",
               "props": {"name": "A", "case_count": 3, "event_count": 4, "case_ratio": 0.5}}
        wrong = {"source": TERM["id"], "target": act["id"], "type": "MAPS_TO", "props": ok["props"]}
        self.assertTrue(any("không được phép" in x for x in validate_graph(_g([TERM, act], [wrong]))))

    def test_drift_reports_undeclared_triples_and_unused(self) -> None:
        g = _g([PARA, ART], [REF, {"source": "R1:Art2", "target": "R1:Art1(1)", "type": "MENTIONS", "props": {}}])
        self.assertEqual(observed_triples(g)[("Paragraph", "REFERS_TO", "Article")], 1)
        d = drift({"g": g})
        self.assertIn(("Article", "MENTIONS", "Paragraph"), d["undeclared_triples"])
        self.assertIn("MAPS_TO", d["unused_relations"])


class TestBuiltGraphsConform(unittest.TestCase):
    """Mọi đồ thị đã dựng trong data/processed phải tuân thủ metamodel (bỏ qua file chưa dựng)."""

    def test_all_built_graphs(self) -> None:
        names = ("cap_legal_graph.json", "cap_legal_graph_v2.json", "de_legal_graph.json",
                 "bpic2018_process_graph.json")
        paths = [PROJECT_ROOT / "data" / "processed" / n for n in names]
        present = [p for p in paths if p.exists()]
        if not present:
            self.skipTest("chưa dựng đồ thị nào")
        for p in present:
            with self.subTest(graph=p.name):
                violations = validate_graph(json.loads(p.read_text(encoding="utf-8")))
                self.assertEqual(violations[:5], [], f"{len(violations)} vi phạm")


if __name__ == "__main__":
    unittest.main()
