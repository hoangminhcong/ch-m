"""
Đồ thị Pháp lý cho tập Đức (docs/V2_DANG_KY_TRUOC.md mục 5.1) — cho ngữ cảnh Graph-RAG (Y, Z) trên khoản Đức.

  node   = đồ thị CAP v1 (cap_legal_graph.json, giữ nguyên) + một node Paragraph cho mỗi khoản Đức (theo năm)
  cạnh   REFERS_TO khoản Đức →
           điều khoản EU: khoản nếu đồ thị có, không thì Article (Article ghép các khoản qua HAS_PARAGRAPH);
           § Đức: phiên bản trùng năm với khoản nguồn nhiều nhất; dẫn chiếu cả § → mọi khoản của phiên bản đó;
           ngoài phạm vi / không tìm thấy: cạnh vẫn ghi (in_scope / không có node) → graph_context bỏ, ghi skipped_refs.
"""

from typing import Any, Dict, List, Mapping, Sequence


def _base(node_id: str) -> str:
    return node_id.split("@", 1)[0]


def _section(node_id: str) -> str:
    return _base(node_id).split("(", 1)[0]


def _german_targets(target: str, years: Sequence[int], de: Sequence[Mapping[str, Any]]) -> List[str]:
    level = _base if "(" in target else _section
    cands = [c for c in de if level(c["node_id"]) == target]
    if not cands and "(" in target:  # khoản không có riêng (VD § không chia khoản) → cả § (rà soát MEDIUM-4)
        return _german_targets(target.split("(", 1)[0], years, de)
    if not cands:
        return []
    # mọi phiên bản trùng ít nhất một năm với khoản nguồn (rà soát M3: trước chỉ phiên bản trùng NHIỀU năm nhất →
    # có năm của khoản nguồn không có đích); không trùng năm nào → mọi phiên bản
    overlapping = [c for c in cands if set(c["years"]) & set(years)]
    return sorted(c["node_id"] for c in (overlapping or cands))


def _eu_target(target: str, cap_ids: set) -> str:
    if target in cap_ids:
        return target
    article = target.split("(", 1)[0]
    return article if article in cap_ids else target


def build_de_legal_graph(de: Sequence[Mapping[str, Any]], cap_graph: Mapping[str, Any]) -> Dict[str, Any]:
    cap_ids = {n["id"] for n in cap_graph["nodes"]}
    nodes = list(cap_graph["nodes"]) + [
        {"id": c["node_id"], "label": "Paragraph",
         "props": {"text": c["text"], "doc_id": c.get("doc_id"), "years": c["years"], "language": "de"}}
        for c in de]
    edges: List[Dict[str, Any]] = list(cap_graph["edges"])
    for c in de:
        for ref in c.get("refs", []):
            props = {"kind": ref["kind"], "in_scope": bool(ref["in_scope"]), "cited_as": ref["target"]}
            if not ref["in_scope"]:
                targets = [ref["target"]]
            elif ref["target"].startswith("DE-"):
                targets = _german_targets(ref["target"], c["years"], de) or [ref["target"]]
            else:
                targets = [_eu_target(ref["target"], cap_ids)]
            edges += [{"source": c["node_id"], "target": t, "type": "REFERS_TO", "props": props}
                      for t in targets if t != c["node_id"]]
    seen, unique = set(), []
    for e in edges:  # cạnh trùng (cùng nguồn, đích, loại) — rà soát M3
        key = (e["source"], e["target"], e["type"])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return {"nodes": nodes, "edges": unique}
