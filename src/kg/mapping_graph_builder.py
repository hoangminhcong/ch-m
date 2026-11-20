"""
Tầng Cầu nối của KG (A4; đăng ký trước v2, thành phần 6 + 9): ontology loại giấy tờ ĐÃ DUYỆT → node + cạnh của KG.

  DocumentType       8 loại giấy tờ (nghĩa, độ tin cậy) — từ ontology đã duyệt
  OF_DOCTYPE         Activity → DocumentType (phần đầu tên ghép; cấu trúc, không suy đoán)
  RELATED_DOCTYPE    DocumentType → DocumentType (quan hệ đã duyệt, VD Payment application declares_parcels_in …)
  MAPS_TO            khoản luật → DocumentType khi khoản nhắc thuật ngữ pháp lý của loại đó (cùng hàm khớp với
                     dòng gợi ý của cấu hình Z — src/kg/ontology_mapping.py — nên đồ thị và prompt không lệch nhau)

Cạnh trỏ vào node của đồ thị luật / tiến trình (không chép lại node) → kiểm metamodel trên HỢP ba đồ thị.
Ontology chưa duyệt → không dựng (ValueError).
"""

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Mapping, Optional

from src.mde.schema_from_kg import COMPOSITE_SEP

from .ontology_mapping import APPROVED, doctype_terms

PROVISIONS = ("Article", "Paragraph", "Annex")


def doctype_node_id(name: str) -> str:
    return f"Doc:{name}"


def _doctype_nodes(ontology: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [{"id": doctype_node_id(name), "label": "DocumentType",
             "props": {"name": name, "meaning": d["meaning"], "confidence": d["confidence"]}}
            for name, d in ontology["doctypes"].items()]


def _of_doctype(process_graph: Mapping[str, Any], doctypes: Mapping[str, Any]) -> Dict[str, Any]:
    edges, unmapped = [], []
    for n in process_graph["nodes"]:
        if n["label"] != "Activity":
            continue
        prefix = n["props"]["name"].split(COMPOSITE_SEP, 1)[0]
        if prefix in doctypes:
            edges.append({"source": n["id"], "target": doctype_node_id(prefix), "type": "OF_DOCTYPE", "props": {}})
        else:
            unmapped.append(n["props"]["name"])
    return {"edges": edges, "unmapped_activities": sorted(unmapped)}


def _related(ontology: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for r in ontology.get("relations", []):
        props = {"kind": r["type"], "confidence": r["confidence"], "approved_by": ontology["approved_by"]}
        if r.get("years"):
            props["years"] = list(r["years"])
        out.append({"source": doctype_node_id(r["from"]), "target": doctype_node_id(r["to"]),
                    "type": "RELATED_DOCTYPE", "props": props})
    return out


def _maps_to(legal_graph: Mapping[str, Any], ontology: Mapping[str, Any]) -> List[Dict[str, Any]]:
    edges = []
    for n in legal_graph["nodes"]:
        text = n.get("props", {}).get("text")
        if n["label"] not in PROVISIONS or not text:
            continue
        for doctype, terms in doctype_terms(text, ontology).items():
            edges.append({"source": n["id"], "target": doctype_node_id(doctype), "type": "MAPS_TO",
                          "props": {"approved_by": ontology["approved_by"], "terms": terms}})
    return edges


@dataclass(frozen=True)
class Bridge:
    """Tầng Cầu nối đọc từ KG — NGUỒN DUY NHẤT của MAPS_TO lúc sinh luật (gợi ý của Z, kiểm N4 của N)."""
    maps: Mapping[str, FrozenSet[str]]  # khoản → loại giấy tờ (cạnh MAPS_TO)
    meanings: Mapping[str, str]  # loại giấy tờ → nghĩa (node DocumentType)
    approved_at: Optional[str] = None

    def doctypes(self, clause: str) -> FrozenSet[str]:
        return self.maps.get(clause, frozenset())


def load_bridge(graph: Mapping[str, Any]) -> Bridge:
    names = {n["id"]: n["props"]["name"] for n in graph["nodes"] if n["label"] == "DocumentType"}
    maps: Dict[str, set] = {}
    for e in graph["edges"]:
        if e["type"] == "MAPS_TO":
            maps.setdefault(e["source"], set()).add(names[e["target"]])
    return Bridge({k: frozenset(v) for k, v in maps.items()},
                  {n["props"]["name"]: n["props"]["meaning"] for n in graph["nodes"] if n["label"] == "DocumentType"},
                  (graph.get("meta") or {}).get("ontology_approved_at"))


def build_mapping_graph(ontology: Mapping[str, Any], legal_graph: Mapping[str, Any],
                        process_graph: Mapping[str, Any]) -> Dict[str, Any]:
    if ontology.get("status") != APPROVED or not ontology.get("approved_by"):
        raise ValueError("Ontology chưa duyệt (status / approved_by) — không dựng tầng Cầu nối")
    of_doctype = _of_doctype(process_graph, ontology["doctypes"])
    maps_to = _maps_to(legal_graph, ontology)
    texts = sum(1 for n in legal_graph["nodes"] if n["label"] in PROVISIONS and n.get("props", {}).get("text"))
    per_doctype: Dict[str, int] = {}
    for e in maps_to:
        per_doctype[e["target"]] = per_doctype.get(e["target"], 0) + 1
    return {
        "nodes": _doctype_nodes(ontology),
        "edges": of_doctype["edges"] + _related(ontology) + maps_to,
        "meta": {"ontology_approved_by": ontology["approved_by"], "ontology_approved_at": ontology.get("approved_at"),
                 "provisions_with_text": texts, "provisions_mapped": len({e["source"] for e in maps_to}),
                 "maps_to_per_doctype": dict(sorted(per_doctype.items())),
                 "unmapped_activities": of_doctype["unmapped_activities"]},
    }
