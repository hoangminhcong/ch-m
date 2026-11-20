"""
Test cho src/mde/schema_from_kg.py: dựng môi trường kiểu Γ (Tầng 2 của MDE) từ tầng Tiến trình của KG,
thay cho process_schema.json sinh riêng cho BPIC2017. Đây là chỗ "KG thay vai trò UML" thành code.
"""

import json
import sys
import unittest
import unittest.mock
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg import metamodel  # noqa: E402
from src.mde.schema_from_kg import (  # noqa: E402
    READS_NODE_PROPS, MetamodelViolation, contract_errors, gamma_from_kg, process_schema_from_graph)
from src.mde.typing_environment import ProcessTypingEnvironment  # noqa: E402

GRAPH = {
    "nodes": [
        {"id": "Act:A_Submitted", "label": "Activity", "props": {"name": "A_Submitted", "origin": "Application"}},
        {"id": "Act:O_Accepted", "label": "Activity", "props": {"name": "O_Accepted", "origin": "Offer"}},
        {"id": "Act:Payment application / Application / mail income", "label": "Activity",
         "props": {"name": "Payment application / Application / mail income"}},
        {"id": "Act:loose", "label": "Activity", "props": {"name": "loose"}},
        {"id": "Attr:case:ApplicationType", "label": "Attribute", "props": {
            "name": "case:ApplicationType", "level": "case", "type": "string", "values": ["Limit raise", "New credit"]}},
        {"id": "Attr:case:young farmer", "label": "Attribute", "props": {
            "name": "case:young farmer", "level": "case", "type": "boolean", "values": ["False", "True"]}},
        {"id": "Attr:case:area", "label": "Attribute", "props": {
            "name": "case:area", "level": "case", "type": "number", "min": 0.0, "max": 576.07}},
        {"id": "Attr:OfferedAmount", "label": "Attribute", "props": {
            "name": "OfferedAmount", "level": "event", "type": "number", "min": 5000.0, "max": 75000.0}},
        {"id": "Attr:note", "label": "Attribute", "props": {
            "name": "note", "level": "event", "type": "string", "distinct_count": 138}},
    ],
    "edges": [
        {"source": "Act:A_Submitted", "target": "Act:O_Accepted", "type": "DIRECTLY_FOLLOWS", "props": {"count": 5}},
        {"source": "Act:O_Accepted", "target": "Act:loose", "type": "DIRECTLY_FOLLOWS", "props": {"count": 9}},
        {"source": "Act:A_Submitted", "target": "Attr:note", "type": "HAS_ATTRIBUTE", "props": {"count": 1}},
    ],
}


class TestSchemaFromGraph(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = process_schema_from_graph(GRAPH, dataset="test")

    def test_activities_sorted(self) -> None:
        self.assertEqual(self.schema["valid_activities"], [
            "A_Submitted", "O_Accepted", "Payment application / Application / mail income", "loose"])

    def test_origin_from_prop_then_composite_prefix_then_process(self) -> None:
        origins = self.schema["activities_by_origin"]
        self.assertEqual(origins["Application"], ["A_Submitted"])
        self.assertEqual(origins["Payment application"], ["Payment application / Application / mail income"])
        self.assertEqual(origins["Process"], ["loose"])

    def test_attribute_types_mapped_to_gamma_names(self) -> None:
        case, event = self.schema["case_attributes"], self.schema["event_attributes"]
        self.assertEqual(case["case:ApplicationType"], {"type": "String", "samples": ["Limit raise", "New credit"],
                                                        "domain": {"values": ["Limit raise", "New credit"]}})
        self.assertEqual(case["case:young farmer"]["type"], "Boolean")
        self.assertEqual(case["case:area"], {"type": "Float", "samples": [0.0, 576.07],
                                             "domain": {"min": 0.0, "max": 576.07}})
        self.assertEqual(event["OfferedAmount"]["type"], "Float")
        self.assertEqual(event["note"], {"type": "String", "samples": []})

    def test_frequent_transitions_by_count(self) -> None:
        self.assertEqual(self.schema["frequent_transitions"], [
            {"from": "O_Accepted", "to": "loose", "count": 9},
            {"from": "A_Submitted", "to": "O_Accepted", "count": 5},
        ])

    def test_provenance_recorded(self) -> None:
        self.assertEqual(self.schema["dataset"], "test")
        self.assertEqual(self.schema["source"], "knowledge_graph")

    def test_gamma_accepts_kg_activity_and_types(self) -> None:
        gamma = ProcessTypingEnvironment(self.schema)
        self.assertTrue(gamma.delta_activity("Payment application / Application / mail income")[0])
        self.assertFalse(gamma.delta_activity("A_Approved")[0])
        self.assertTrue(gamma.check_type_conformance("case:area", ">", 10)[0])
        self.assertFalse(gamma.check_type_conformance("case:young farmer", ">", 1)[0])


GRAPH_2017 = PROJECT_ROOT / "data" / "processed" / "process_graph.json"
SCHEMA_2017 = PROJECT_ROOT / "data" / "processed" / "process_schema.json"


from src.datasets import skip_unless_bpic2017  # noqa: E402  (bộ BPIC2017 đang tạm vô hiệu)


@skip_unless_bpic2017
@unittest.skipUnless(GRAPH_2017.exists() and SCHEMA_2017.exists(), "cần process_graph.json và process_schema.json")
class TestBPIC2017Equivalence(unittest.TestCase):
    """Γ dựng từ KG phải có ĐÚNG tập activity và nhóm origin như Γ cũ (process_schema.json)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.kg = process_schema_from_graph(json.loads(GRAPH_2017.read_text(encoding="utf-8")), dataset="BPIC2017")
        cls.old = json.loads(SCHEMA_2017.read_text(encoding="utf-8"))

    def test_same_activities(self) -> None:
        self.assertEqual(set(self.kg["valid_activities"]), set(self.old["valid_activities"]))

    def test_same_origin_groups(self) -> None:
        self.assertEqual({k: sorted(v) for k, v in self.kg["activities_by_origin"].items()},
                         {k: sorted(v) for k, v in self.old["activities_by_origin"].items()})

    def test_business_attributes_kept_with_same_type(self) -> None:
        old_attrs = {**self.old["case_attributes"], **self.old["event_attributes"]}
        kg_attrs = {**self.kg["case_attributes"], **self.kg["event_attributes"]}
        for name in ("case:ApplicationType", "case:LoanGoal", "case:RequestedAmount", "OfferedAmount", "CreditScore"):
            self.assertEqual(kg_attrs[name]["type"], old_attrs[name]["type"], name)


def _conforming_graph() -> dict:
    act = {"case_count": 3, "event_count": 4, "case_ratio": 0.5}
    return {"nodes": [
        {"id": "Act:a / s / x", "label": "Activity", "props": {"name": "a / s / x", **act}},
        {"id": "Act:a / s / y", "label": "Activity", "props": {"name": "a / s / y", **act}},
        {"id": "Attr:case:year", "label": "Attribute", "props": {
            "name": "case:year", "level": "case", "type": "number", "non_null_ratio": 1.0, "min": 2015, "max": 2017}},
        {"id": "Attr:success", "label": "Attribute", "props": {
            "name": "success", "level": "event", "type": "boolean", "non_null_ratio": 1.0,
            "values": ["False", "True"]}},
    ], "edges": [
        {"source": "Act:a / s / x", "target": "Act:a / s / y", "type": "DIRECTLY_FOLLOWS", "props": {"count": 2}},
        {"source": "Act:a / s / x", "target": "Attr:success", "type": "HAS_ATTRIBUTE",
         "props": {"count": 4, "non_null_ratio": 1.0}},
    ]}


class TestMetamodelGate(unittest.TestCase):
    """A1: Γ chỉ được dựng từ KG đã qua kiểm metamodel; phép chiếu chỉ đọc thứ metamodel khai báo."""

    def test_projection_contract_matches_metamodel(self) -> None:
        self.assertEqual(contract_errors(), [])
        for label, props in READS_NODE_PROPS.items():
            cls = metamodel.NODE_CLASSES[label]
            declared = {k for k, _ in cls.required} | {k for k, _ in cls.optional}
            self.assertLessEqual(set(props), declared, label)

    def test_conforming_graph_gives_same_gamma_as_plain_projection(self) -> None:
        g = _conforming_graph()
        self.assertEqual(gamma_from_kg(g, "T"), process_schema_from_graph(g, "T"))

    def test_missing_required_prop_blocks_gamma(self) -> None:
        g = _conforming_graph()
        del g["nodes"][0]["props"]["case_count"]
        with self.assertRaisesRegex(MetamodelViolation, "case_count"):
            gamma_from_kg(g, "T")

    def test_attribute_type_outside_metamodel_blocks_gamma(self) -> None:
        g = _conforming_graph()
        g["nodes"][2]["props"]["type"] = "integer"  # trước đây lặng lẽ thành 'String' trong Γ
        with self.assertRaisesRegex(MetamodelViolation, "type"):
            gamma_from_kg(g, "T")

    def test_legal_layer_node_in_process_graph_blocks_gamma(self) -> None:
        g = _conforming_graph()
        g["nodes"].append({"id": "R1306:Art7", "label": "Article", "props": {"doc_id": "R1306", "in_scope": False}})
        with self.assertRaisesRegex(MetamodelViolation, "tầng Tiến trình"):
            gamma_from_kg(g, "T")

    def test_contract_breaks_when_metamodel_drops_a_read_prop(self) -> None:
        cls = metamodel.NODE_CLASSES["Activity"]
        stripped = metamodel.NodeClass(cls.name, cls.layer, cls.required, (), cls.doc)  # bỏ 'origin'
        with unittest.mock.patch.dict(metamodel.NODE_CLASSES, {"Activity": stripped}):
            self.assertIn("Activity.origin không được metamodel khai báo", contract_errors())


class TestGammaOnDiskIsKgProjection(unittest.TestCase):
    """Γ dùng trong thực nghiệm (gamma_bpic2018.json) phải đúng là phép chiếu đã kiểm của KG hiện tại."""

    def test_bpic2018(self) -> None:
        graph = PROJECT_ROOT / "data" / "processed" / "bpic2018_process_graph.json"
        gamma = PROJECT_ROOT / "data" / "processed" / "gamma_bpic2018.json"
        if not (graph.exists() and gamma.exists()):
            self.skipTest("chưa có KG / Γ BPIC2018")
        self.assertEqual(gamma_from_kg(json.loads(graph.read_text(encoding="utf-8")), "BPIC2018"),
                         json.loads(gamma.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
