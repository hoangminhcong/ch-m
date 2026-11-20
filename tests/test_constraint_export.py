"""
v2 (docs/V2_DANG_KY_TRUOC.md thành phần 12): luật đã kiểm chứng → KG. Node VerifiedConstraint, cạnh GROUNDED_IN
(→ khoản luật căn cứ) và ON (→ Activity của tầng Tiến trình; nhóm '{A | B}' → mỗi thành viên). Chỉ khoản RULE.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.constraint_export import export_constraints  # noqa: E402

MAIL = "Payment application / Application / mail income"
GEO = "Geo parcel document / Declared / create"
PARCEL = "Parcel document / Main / initialize"


def _ast(nid, a, b=None, template="Response"):
    return {"article_id": nid, "template_name": template, "activation_activity": a, "target_activity": b,
            "activation_attr": None, "activation_op": None, "activation_val": None, "extra_conditions": [],
            "time_min": None, "time_max": None, "time_unit": None}


PREDS = {"config": "Z", "predictions": {
    "R1:Art1": {"outcome": "RULE", "ast": _ast("R1:Art1", MAIL, "{" + f"{GEO} | {PARCEL}" + "}"),
                "grounding": {"vacuous": False}, "process_checks": {"mass_violation": {"ratio": 0.01}}},
    "R1:Art2": {"outcome": "BASELESS", "ast": None},
    "R1:Art3": {"outcome": "FAILED", "ast": None}}}


class TestConstraintExport(unittest.TestCase):
    def setUp(self) -> None:
        self.g = export_constraints(PREDS)

    def test_only_rules_become_nodes(self) -> None:
        nodes = [n for n in self.g["nodes"] if n["label"] == "VerifiedConstraint"]
        self.assertEqual([n["id"] for n in nodes], ["Constraint:Z:R1:Art1"])
        self.assertIn("Response[", nodes[0]["props"]["decl"])
        self.assertEqual(nodes[0]["props"]["config"], "Z")

    def test_grounded_in_clause_and_on_each_group_member(self) -> None:
        edges = {(e["type"], e["target"]) for e in self.g["edges"]}
        self.assertIn(("GROUNDED_IN", "R1:Art1"), edges)
        self.assertEqual({t for k, t in edges if k == "ON"}, {f"Act:{MAIL}", f"Act:{GEO}", f"Act:{PARCEL}"})

    def test_flags_kept_for_review(self) -> None:
        props = self.g["nodes"][0]["props"]
        self.assertEqual((props["vacuous"], props["mass_violation_ratio"]), (False, 0.01))

    def test_set_level_conflict_becomes_edge_and_graph_conforms_to_metamodel(self) -> None:
        """Kiểm tập ràng buộc (2026-11-19): Existence(A) và Absence(A) từ hai khoản → cạnh CONFLICTS_WITH; đồ thị
        luật + tầng Pháp lý + tầng Tiến trình (hợp lại) tuân thủ metamodel."""
        from src.kg.metamodel import validate_graph

        preds = {"config": "Z", "predictions": {
            "R1:Art1": {"outcome": "RULE", "ast": _ast("R1:Art1", MAIL, template="Existence")},
            "R1:Art2": {"outcome": "RULE", "ast": _ast("R1:Art2", MAIL, template="Absence")}}}
        g = export_constraints(preds)
        self.assertEqual([(f["a"], f["b"], f["kind"]) for f in g["set_checks"]], [("R1:Art1", "R1:Art2", "CONFLICT")])
        conflict = [e for e in g["edges"] if e["type"] == "CONFLICTS_WITH"]
        self.assertEqual([(e["source"], e["target"]) for e in conflict], [("Constraint:Z:R1:Art1", "Constraint:Z:R1:Art2")])
        legal = [{"id": f"R1:Art{i}", "label": "Article", "props": {"doc_id": "R1", "in_scope": True, "title": "t"}}
                 for i in (1, 2)]
        act = [{"id": f"Act:{MAIL}", "label": "Activity",
                "props": {"name": MAIL, "case_count": 1, "event_count": 1, "case_ratio": 0.1}}]
        self.assertEqual(validate_graph({"nodes": g["nodes"] + legal + act, "edges": g["edges"]}), [])


def _oa(norm_type, action="The aid shall be paid", deadline=None):
    return {"duty_bearer": "paying_agency_case_processing", "observable_in_log": norm_type != "calculation",
            "evidence": "shall be paid", "norm_type": norm_type, "action": action, "deadline": deadline}


class TestNormLayer(unittest.TestCase):
    """Tầng Chuẩn tắc (2026-11-20): khung chuẩn tắc của cấu hình N → node Norm; GROUNDED_IN khoản; FORMALIZED_AS
    ràng buộc nếu khoản ra luật. Khoản không có khung (Y, X…) → không có Norm."""

    PREDS_N = {"config": "N", "predictions": {
        "R1:Art1": {"outcome": "RULE", "ast": _ast("R1:Art1", MAIL, template="Existence"),
                    "obligation_analysis": _oa("deadline", deadline="by 15 May")},
        "R1:Art2": {"outcome": "BASELESS", "ast": None, "obligation_analysis": _oa("calculation")},
        "R1:Art3": {"outcome": "BASELESS", "ast": None,
                    "obligation_analysis": {"duty_bearer": "commission", "observable_in_log": False}}}}

    def test_norm_nodes_and_edges(self) -> None:
        g = export_constraints(self.PREDS_N)
        norms = {n["id"]: n["props"] for n in g["nodes"] if n["label"] == "Norm"}
        self.assertEqual(set(norms), {"Norm:N:R1:Art1", "Norm:N:R1:Art2"})  # Art3 không có khung
        self.assertEqual((norms["Norm:N:R1:Art1"]["expressible"], norms["Norm:N:R1:Art2"]["expressible"]),
                         (True, False))
        self.assertEqual(norms["Norm:N:R1:Art1"]["deadline"], "by 15 May")
        formal = [(e["source"], e["target"]) for e in g["edges"] if e["type"] == "FORMALIZED_AS"]
        self.assertEqual(formal, [("Norm:N:R1:Art1", "Constraint:N:R1:Art1")])

    def test_norm_layer_conforms_to_metamodel(self) -> None:
        from src.kg.metamodel import validate_graph
        g = export_constraints(self.PREDS_N)
        legal = [{"id": f"R1:Art{i}", "label": "Article", "props": {"doc_id": "R1", "in_scope": True, "title": "t"}}
                 for i in (1, 2, 3)]
        act = [{"id": f"Act:{MAIL}", "label": "Activity",
                "props": {"name": MAIL, "case_count": 1, "event_count": 1, "case_ratio": 0.1}}]
        self.assertEqual(validate_graph({"nodes": g["nodes"] + legal + act, "edges": g["edges"]}), [])

    def test_config_without_frame_has_no_norms(self) -> None:
        self.assertFalse([n for n in export_constraints(PREDS)["nodes"] if n["label"] == "Norm"])


class TestFullKgMerge(unittest.TestCase):
    def test_same_node_twice_is_fine_but_conflicting_copy_is_refused(self) -> None:
        from scripts.build_full_kg import merge
        node = {"id": "A", "label": "Article", "props": {"doc_id": "R1", "in_scope": False}}
        g = merge({"x": {"nodes": [node], "edges": []}, "y": {"nodes": [dict(node)], "edges": []}})
        self.assertEqual(len(g["nodes"]), 1)
        with self.assertRaises(ValueError):
            merge({"x": {"nodes": [node], "edges": []},
                   "y": {"nodes": [{**node, "props": {"doc_id": "R2", "in_scope": False}}], "edges": []}})


if __name__ == "__main__":
    unittest.main()
