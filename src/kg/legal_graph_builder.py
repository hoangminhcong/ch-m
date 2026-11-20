"""
M1 – Legal Graph Builder (T1.2): dựng tầng Pháp lý của KG từ directive_chunks.json.

Tạo các node Article / Paragraph / LegalConcept và các cạnh:
- HAS_PARAGRAPH : Article -> Paragraph
- REFERS_TO     : Paragraph -> Paragraph | Article  (tham chiếu chéo trong cùng Directive)
- DEFINES       : Article 3 -> LegalConcept         (định nghĩa '(a) ‘term’ means ...')
- MENTIONS      : Paragraph -> LegalConcept         (khoản có nhắc tới khái niệm)

Bước này hoàn toàn tất định (regex), không dùng LLM.
Article không có khoản đánh số (VD: Article 3, Article 7) chỉ có một node Article mang luôn văn bản.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple, Union

from .schema import EdgeType, KGEdge, KGNode, KnowledgeGraph, NodeLabel

Ref = Tuple[int, Optional[int]]  # (số Article, số khoản | None nếu tham chiếu cả Article)

_PARAGRAPH_ID = re.compile(r"^Article\s+(\d+)(?:\((\d+)\))?$")
_NUM = r"\d+(?:\(\d+\))?"
_ARTICLE_REF = re.compile(rf"\bArticles?\s+({_NUM}(?:\s*(?:,|and|or|to)\s*{_NUM})*)")
_PARAGRAPH_REF = re.compile(r"\bparagraphs?\s+(\d+(?:\s*(?:,|and|or|to)\s*\d+)*)")
# "paragraph 2 of Article 10" -> khoản thuộc Article 10 (không phải Article hiện tại)
_OF_ARTICLE = re.compile(r"\s+of\s+(Article\s+(\d+))\b")
# Phần đuôi cho biết tham chiếu trỏ sang văn bản luật khác (VD: "... of Directive 2002/65/EC")
_EXTERNAL_TAIL = re.compile(
    r"^(?:\s*,?\s*(?:paragraphs?|and|or|\(\d+\)|\d+))*\s*of\s+(?:Council\s+)?"
    r"(?:Directive|Regulation|Decision|the\s+Treaty)",
    re.IGNORECASE,
)
_QUOTES = "‘’'\"“”"
_DEFINITION = re.compile(
    rf"\(([a-z]{{1,2}})\)\s*[{_QUOTES}]([^{_QUOTES}]+)[{_QUOTES}]\s+means\s+(.*?)"
    rf"(?=;\s*(?:and\s+)?\([a-z]{{1,2}}\)\s*[{_QUOTES}]|$)",
    re.DOTALL,
)
DEFINITIONS_ARTICLE = 3


# ----------------------------------------------------------------------------- ids


def parse_paragraph_id(article_id: str) -> Ref:
    """'Article 14(1)' -> (14, 1); 'Article 7' -> (7, None)."""
    match = _PARAGRAPH_ID.match(article_id.strip())
    if not match:
        raise ValueError(f"article_id không hợp lệ: {article_id!r}")
    para = match.group(2)
    return int(match.group(1)), int(para) if para else None


def paragraph_node_id(article: int, paragraph: Optional[int]) -> str:
    return f"Art{article}" if paragraph is None else f"Art{article}({paragraph})"


def concept_node_id(term: str) -> str:
    return f"Concept:{term.lower()}"


# ------------------------------------------------------------------------ references


def _expand_numbers(spec: str) -> List[Ref]:
    """'1 to 3, 18 and 10(2)' -> [(1,None),(2,None),(3,None),(18,None),(10,2)]."""
    refs: List[Ref] = []
    tokens = re.findall(r"\d+(?:\(\d+\))?|\bto\b", spec)
    pending_range = False
    for token in tokens:
        if token == "to":
            pending_range = True
            continue
        art, para = parse_paragraph_id(f"Article {token}")
        if pending_range and refs and refs[-1][1] is None and para is None:
            refs.extend((n, None) for n in range(refs[-1][0] + 1, art + 1))
        else:
            refs.append((art, para))
        pending_range = False
    return refs


def _is_external(text: str, match_end: int) -> bool:
    return bool(_EXTERNAL_TAIL.match(text[match_end:match_end + 80]))


def extract_references(
    text: str, current_article: int, current_paragraph: Optional[int] = None
) -> List[Ref]:
    """Trả về tham chiếu tới các Article/khoản khác trong cùng Directive, theo thứ tự xuất hiện."""
    found: List[Tuple[int, Ref]] = []
    consumed_article_starts: Set[int] = set()
    for match in _PARAGRAPH_REF.finditer(text):
        owner = _OF_ARTICLE.match(text, match.end())
        if owner and _is_external(text, owner.end()):
            continue
        target_article = int(owner.group(2)) if owner else current_article
        if owner:
            consumed_article_starts.add(owner.start(1))
        found.extend(
            (match.start(), (target_article, para))
            for para, _ in _expand_numbers(match.group(1))
        )
    for match in _ARTICLE_REF.finditer(text):
        if match.start() in consumed_article_starts or _is_external(text, match.end()):
            continue
        found.extend((match.start(), ref) for ref in _expand_numbers(match.group(1)))

    own = {(current_article, None), (current_article, current_paragraph)}
    result: List[Ref] = []
    for _, ref in sorted(found, key=lambda item: item[0]):
        if ref not in own and ref not in result:
            result.append(ref)
    return result


# ------------------------------------------------------------- definitions / mentions


def extract_definitions(text: str) -> List[Tuple[str, str]]:
    """Trích '(a) ‘term’ means definition' -> [(term, definition), ...]."""
    return [
        (m.group(2).strip(), re.sub(r"\s+", " ", m.group(3)).strip().rstrip(".;"))
        for m in _DEFINITION.finditer(text)
    ]


def find_mentions(text: str, terms: Iterable[str]) -> Set[str]:
    """Khái niệm được nhắc trong text; ưu tiên cụm dài nhất ('credit agreement' thắng 'credit')."""
    occupied: List[Tuple[int, int]] = []
    found: Set[str] = set()
    for term in sorted(set(terms), key=len, reverse=True):
        pattern = re.compile(rf"\b{re.escape(term)}s?\b", re.IGNORECASE)
        for m in pattern.finditer(text):
            if any(m.start() < end and start < m.end() for start, end in occupied):
                continue
            occupied.append((m.start(), m.end()))
            found.add(term)
    return found


# ------------------------------------------------------------------------- building


def _structure_nodes(chunks: Sequence[Mapping[str, Any]]) -> Tuple[List[KGNode], List[KGEdge]]:
    """Node Article/Paragraph và cạnh HAS_PARAGRAPH."""
    nodes: Dict[str, KGNode] = {}
    edges: List[KGEdge] = []
    for chunk in chunks:
        art, para = parse_paragraph_id(chunk["article_id"])
        art_id = paragraph_node_id(art, None)
        text_props = {
            "article_ref": chunk["article_id"],
            "text": chunk["text"],
            "has_numeric_bound": bool(chunk.get("has_numeric_bound", False)),
            "in_scope": True,  # mọi khoản có văn bản đều thuộc phạm vi đã parse (Article 1–24)
        }
        article_props: Dict[str, Any] = {
            "number": art, "title": chunk.get("article_title", ""), "in_scope": True,
        }
        if para is None:
            nodes[art_id] = KGNode(art_id, NodeLabel.ARTICLE, {**article_props, **text_props})
            continue
        if art_id not in nodes:
            nodes[art_id] = KGNode(art_id, NodeLabel.ARTICLE, article_props)
        para_id = paragraph_node_id(art, para)
        nodes[para_id] = KGNode(para_id, NodeLabel.PARAGRAPH, {**text_props, "number": para})
        edges.append(KGEdge(art_id, para_id, EdgeType.HAS_PARAGRAPH))
    return list(nodes.values()), edges


def _resolve_target(ref: Ref, known_ids: Set[str]) -> str:
    """Ưu tiên node khoản; nếu không có thì trỏ tới node Article."""
    para_id = paragraph_node_id(*ref)
    return para_id if para_id in known_ids else paragraph_node_id(ref[0], None)


def _reference_edges(
    chunks: Sequence[Mapping[str, Any]], known_ids: Set[str]
) -> Tuple[List[KGNode], List[KGEdge]]:
    """Cạnh REFERS_TO; Article ngoài phạm vi đã parse (VD 25–32) được tạo node in_scope=False."""
    extra_nodes: Dict[str, KGNode] = {}
    edges: List[KGEdge] = []
    for chunk in chunks:
        art, para = parse_paragraph_id(chunk["article_id"])
        source = paragraph_node_id(art, para)
        for ref in extract_references(chunk["text"], art, para):
            target = _resolve_target(ref, known_ids)
            if target not in known_ids and target not in extra_nodes:
                extra_nodes[target] = KGNode(
                    target, NodeLabel.ARTICLE, {"number": ref[0], "in_scope": False}
                )
            edges.append(KGEdge(source, target, EdgeType.REFERS_TO, {
                "cited_as": f"Article {ref[0]}" + (f"({ref[1]})" if ref[1] else ""),
            }))
    return list(extra_nodes.values()), edges


def _concept_layer(
    chunks: Sequence[Mapping[str, Any]],
) -> Tuple[List[KGNode], List[KGEdge]]:
    """Node LegalConcept từ Article 3 + cạnh DEFINES và MENTIONS."""
    def_chunks = [c for c in chunks if parse_paragraph_id(c["article_id"])[0] == DEFINITIONS_ARTICLE]
    nodes: List[KGNode] = []
    edges: List[KGEdge] = []
    for chunk in def_chunks:
        source = paragraph_node_id(*parse_paragraph_id(chunk["article_id"]))
        for term, definition in extract_definitions(chunk["text"]):
            cid = concept_node_id(term)
            nodes.append(KGNode(cid, NodeLabel.LEGAL_CONCEPT, {"term": term, "definition": definition}))
            edges.append(KGEdge(source, cid, EdgeType.DEFINES))

    terms = [n.props["term"] for n in nodes]
    for chunk in chunks:
        art, para = parse_paragraph_id(chunk["article_id"])
        if art == DEFINITIONS_ARTICLE:
            continue
        source = paragraph_node_id(art, para)
        edges.extend(
            KGEdge(source, concept_node_id(t), EdgeType.MENTIONS)
            for t in sorted(find_mentions(chunk["text"], terms))
        )
    return nodes, edges


def build_legal_graph(chunks: Sequence[Mapping[str, Any]]) -> KnowledgeGraph:
    """Dựng tầng Pháp lý của KG từ danh sách chunk (định dạng directive_chunks.json)."""
    struct_nodes, struct_edges = _structure_nodes(chunks)
    known_ids = {n.id for n in struct_nodes}
    ref_nodes, ref_edges = _reference_edges(chunks, known_ids)
    concept_nodes, concept_edges = _concept_layer(chunks)
    return KnowledgeGraph().merge(
        nodes=[*struct_nodes, *ref_nodes, *concept_nodes],
        edges=[*struct_edges, *ref_edges, *concept_edges],
    )


def build_legal_graph_file(
    chunks_path: Union[str, Path], output_path: Union[str, Path]
) -> KnowledgeGraph:
    """Đọc directive_chunks.json, dựng đồ thị, ghi ra JSON."""
    with open(chunks_path, encoding="utf-8") as f:
        chunks = json.load(f)
    graph = build_legal_graph(chunks)
    problems = graph.validate()
    if problems:
        raise ValueError(f"Đồ thị pháp lý có cạnh treo: {problems[:5]}")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(graph.to_dict(), f, ensure_ascii=False, indent=2)
    return graph
