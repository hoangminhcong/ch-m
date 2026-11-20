"""
M1 cho bộ dữ liệu thứ hai: tầng Pháp lý của KG từ 4 Quy định CAP (data/processed/cap_chunks.json).

Khác legal_graph_builder.py (riêng Directive 2008/48/EC, mã điều là số nguyên): ở đây mã node có tiền tố
văn bản ('R1306:Art75', 'R1306:Art75(1)') và dẫn chiếu có thể đi SANG văn bản khác.

Node:  Article (mọi điều; điều không có khoản đánh số mang luôn văn bản)   Paragraph (khoản đánh số)
Cạnh:  HAS_PARAGRAPH  Article -> Paragraph
       REFERS_TO      Paragraph|Article -> Paragraph|Article   props: kind (internal|external), cited_as
Đích dẫn chiếu không có trong dữ liệu đã tách: lùi về điều; nếu điều cũng không có -> node Article
in_scope=False (VD điều chưa tách được, hoặc văn bản ngoài bộ như 1305/2013).
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Union

from .schema import EdgeType, KGEdge, KGNode, KnowledgeGraph, NodeLabel

_PARAGRAPH = re.compile(r"^(?P<article>.+:Art\d+)\((?P<para>\d+)\)$")


def article_of(node_id: str) -> str:
    """'R1306:Art75(1)' -> 'R1306:Art75'; 'R1306:Art74' -> 'R1306:Art74'."""
    m = _PARAGRAPH.match(node_id)
    return m.group("article") if m else node_id


def _structure(chunks: Sequence[Mapping[str, Any]]) -> Dict[str, KGNode]:
    nodes: Dict[str, KGNode] = {}
    for chunk in chunks:
        node_id, doc_id = chunk["node_id"], chunk["doc_id"]
        common = {"doc_id": doc_id, "text": chunk["text"], "has_numeric_bound": bool(chunk["has_numeric_bound"]),
                  "in_scope": True, "title": chunk["article_title"]}
        art_id = article_of(node_id)
        if art_id == node_id:  # điều không có khoản đánh số
            nodes[node_id] = KGNode(node_id, NodeLabel.ARTICLE, common)
            continue
        nodes[node_id] = KGNode(node_id, NodeLabel.PARAGRAPH, common)
        nodes.setdefault(art_id, KGNode(art_id, NodeLabel.ARTICLE, {
            "doc_id": doc_id, "title": chunk["article_title"], "in_scope": True}))
    return nodes


def _annex_nodes(annexes: Sequence[Mapping[str, Any]]) -> Dict[str, KGNode]:
    return {a["node_id"]: KGNode(a["node_id"], NodeLabel.ANNEX, {
        "doc_id": a["doc_id"], "text": a["text"], "title": a["article_title"],
        "has_numeric_bound": bool(a["has_numeric_bound"]), "in_scope": True}) for a in annexes}


def build_regulation_graph(chunks: Sequence[Mapping[str, Any]],
                           annexes: Sequence[Mapping[str, Any]] = ()) -> KnowledgeGraph:
    """Khoản + (tuỳ chọn) Phụ lục; dẫn chiếu từ cả khoản lẫn Phụ lục."""
    nodes = {**_structure(chunks), **_annex_nodes(annexes)}
    edges: List[KGEdge] = [
        KGEdge(article_of(nid), nid, EdgeType.HAS_PARAGRAPH)
        for nid, node in nodes.items() if node.label == NodeLabel.PARAGRAPH
    ]
    placeholders: Dict[str, KGNode] = {}
    for chunk in [*chunks, *annexes]:
        source = chunk["node_id"]
        for ref in chunk.get("refs", []):
            target = ref["target"] if ref["target"] in nodes else article_of(ref["target"])
            if target == source:
                continue
            if target not in nodes and target not in placeholders:
                label = NodeLabel.ANNEX if ":Annex" in target else NodeLabel.ARTICLE
                placeholders[target] = KGNode(target, label, {
                    "doc_id": target.split(":")[0], "in_scope": False})
            edges.append(KGEdge(source, target, EdgeType.REFERS_TO, {
                "kind": ref["kind"], "in_scope": bool(ref["in_scope"]), "cited_as": ref["target"]}))
    return KnowledgeGraph().merge(nodes=[*nodes.values(), *placeholders.values()], edges=edges)


def build_regulation_graph_file(chunks_path: Union[str, Path], output_path: Union[str, Path],
                                annexes_path: Union[str, Path, None] = None) -> KnowledgeGraph:
    chunks = json.loads(Path(chunks_path).read_text(encoding="utf-8"))
    has_annexes = annexes_path is not None and Path(annexes_path).exists()
    annexes = json.loads(Path(annexes_path).read_text(encoding="utf-8")) if has_annexes else []
    graph = build_regulation_graph(chunks, annexes)
    Path(output_path).write_text(json.dumps(graph.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return graph
