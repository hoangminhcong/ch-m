"""
v2 — luật đã kiểm chứng vào KG (docs/V2_DANG_KY_TRUOC.md thành phần 12): truy vết luật ↔ điều khoản ↔ activity
(phần "traceability" mà UML có khi thiết kế, KG v1 chưa có).

  VerifiedConstraint  mỗi khoản có outcome RULE của một cấu hình (dòng .decl + cờ kiểm)
  GROUNDED_IN         → khoản luật căn cứ (id node của tầng Pháp lý)
  ON                  → Activity của tầng Tiến trình (id 'Act:<tên>' như process_graph_builder; nhóm → từng thành viên)
  CONFLICTS_WITH / IMPLIES / DUPLICATE_OF  giữa hai VerifiedConstraint — kiểm TẬP ràng buộc
                      (src/symbolic/constraint_set_checks.py, 2026-11-19); chỉ để người xem xét, không xoá luật nào
  Norm                tầng Chuẩn tắc (2026-11-20): khung chuẩn tắc của khoản (cấu hình N) —
                      GROUNDED_IN → khoản; FORMALIZED_AS → VerifiedConstraint nếu khoản ra luật
"""

from typing import Any, Dict, List, Mapping, Tuple

from ..mde.constraint_ast import DeclareConstraintAST, activity_members
from ..symbolic.constraint_set_checks import METHOD as SET_CHECK_METHOD
from ..symbolic.constraint_set_checks import check_constraint_set
from ..symbolic.norm_frame import EXPRESSIBLE
from .metamodel import NORM_TYPES
from .process_graph_builder import activity_node_id

RULE = "RULE"
SET_EDGE = {"CONFLICT": "CONFLICTS_WITH", "CONFLICT_IF_ACTIVATED": "CONFLICTS_WITH", "IMPLIES": "IMPLIES",
            "DUPLICATE": "DUPLICATE_OF"}


def export_constraints(predictions_doc: Mapping[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    config = predictions_doc.get("config", "?")
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for nid, p in sorted(predictions_doc.get("predictions", {}).items()):
        if p.get("outcome") != RULE or not p.get("ast"):
            continue
        ast = p["ast"]
        cid = f"Constraint:{config}:{nid}"
        mass = ((p.get("process_checks") or {}).get("mass_violation") or {}).get("ratio")
        nodes.append({"id": cid, "label": "VerifiedConstraint", "props": {
            "config": config, "clause": nid, "template": ast.get("template_name"),
            "decl": DeclareConstraintAST.model_validate(dict(ast)).to_declare4py_line().strip(),
            "vacuous": (p.get("grounding") or {}).get("vacuous"), "mass_violation_ratio": mass}})
        edges.append({"source": cid, "target": nid, "type": "GROUNDED_IN", "props": {}})
        acts = sorted({m for side in (ast.get("activation_activity"), ast.get("target_activity")) if side
                       for m in activity_members(side)})
        edges += [{"source": cid, "target": activity_node_id(a), "type": "ON", "props": {}} for a in acts]
    rules = {n["props"]["clause"]: predictions_doc["predictions"][n["props"]["clause"]]["ast"] for n in nodes}
    findings = check_constraint_set(rules)
    edges += [{"source": f"Constraint:{config}:{f['a']}", "target": f"Constraint:{config}:{f['b']}",
               "type": SET_EDGE[f["kind"]], "props": {"kind": f["kind"], "note": f["note"],
                                                      "method": SET_CHECK_METHOD}}
              for f in findings]
    norm_nodes, norm_edges = _norms(config, predictions_doc.get("predictions", {}),
                                    {n["props"]["clause"] for n in nodes})
    return {"nodes": nodes + norm_nodes, "edges": edges + norm_edges, "set_checks": findings}


def _norms(config: str, predictions: Mapping[str, Mapping[str, Any]],
           formalized: set) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Tầng Chuẩn tắc: một Norm cho mỗi khoản có khung chuẩn tắc hợp lệ (cấu hình N), KỂ CẢ khi không thành ràng
    buộc — để KG ghi lại "khoản này là quy định nội dung / tính toán…, không diễn đạt được bằng DECLARE"."""
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for nid, p in sorted(predictions.items()):
        oa = p.get("obligation_analysis") or {}
        if oa.get("norm_type") not in NORM_TYPES or not isinstance(oa.get("action"), str) or not oa["action"].strip():
            continue
        props: Dict[str, Any] = {"config": config, "clause": nid, "norm_type": oa["norm_type"], "action": oa["action"],
                                 "deadline": oa.get("deadline") if isinstance(oa.get("deadline"), str) else None,
                                 "expressible": oa["norm_type"] in EXPRESSIBLE}
        if isinstance(oa.get("duty_bearer"), str) and oa["duty_bearer"].strip():
            props["duty_bearer"] = oa["duty_bearer"]
        if isinstance(oa.get("observable_in_log"), bool):
            props["observable_in_log"] = oa["observable_in_log"]
        if isinstance(oa.get("evidence"), str):
            props["evidence"] = oa["evidence"]
        norm_id = f"Norm:{config}:{nid}"
        nodes.append({"id": norm_id, "label": "Norm", "props": props})
        edges.append({"source": norm_id, "target": nid, "type": "GROUNDED_IN", "props": {}})
        if nid in formalized:
            edges.append({"source": norm_id, "target": f"Constraint:{config}:{nid}", "type": "FORMALIZED_AS",
                          "props": {}})
    return nodes, edges
