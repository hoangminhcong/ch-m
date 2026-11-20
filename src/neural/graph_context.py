"""
Cấu hình Y (Graph-RAG) của TN5–TN8 bộ CAP: ngữ cảnh = khoản luật + nguyên văn các khoản nó dẫn chiếu,
lấy bằng cách duyệt đồ thị luật (data/processed/cap_legal_graph.json), KHÔNG dùng phiếu gán nhãn.

  khoản ──REFERS_TO──▶ Paragraph            → văn bản khoản đó
  khoản ──REFERS_TO──▶ Article ──HAS_PARAGRAPH──▶ các khoản → ghép theo thứ tự (không có khoản → text của Article)
Chỉ đi 1 bước; đích ngoài bộ 4 văn bản (in_scope = False) hoặc không có trong đồ thị bị bỏ, ghi ở `skipped_refs`.
Mỗi văn bản dẫn chiếu cắt ở MAX_REF_CHARS ký tự, tổng ở MAX_TOTAL_REF_CHARS (giới hạn token của API) — phần bị
cắt đánh dấu rõ, và số ký tự bị cắt được ghi lại để báo cáo.
Cấu hình X dùng đúng khoản luật (`clause_only_chunk`) để so sánh công bằng: cùng prompt, chỉ khác ngữ cảnh.
"""

import re
from typing import Any, Dict, List, Mapping

MAX_REF_CHARS = 3000
MAX_TOTAL_REF_CHARS = 12000
REF_HEADER = "\n\nReferenced provisions (retrieved via the legal knowledge graph):"
TRUNCATED = " […truncated]"


def _paragraph_order(node_id: str) -> int:
    m = re.search(r"\((\d+)\)$", node_id)
    return int(m.group(1)) if m else 0


class LegalGraphIndex:
    """Chỉ mục kề của đồ thị luật: REFERS_TO đi ra và HAS_PARAGRAPH của từng Article."""

    def __init__(self, graph: Mapping[str, Any]) -> None:
        self.nodes = {n["id"]: n for n in graph["nodes"]}
        self.refs: Dict[str, List[Mapping[str, Any]]] = {}
        self.paragraphs: Dict[str, List[str]] = {}
        for e in graph["edges"]:
            if e["type"] == "REFERS_TO":
                self.refs.setdefault(e["source"], []).append(e)
            elif e["type"] == "HAS_PARAGRAPH":
                self.paragraphs.setdefault(e["source"], []).append(e["target"])

    def text_of(self, node_id: str) -> str:
        node = self.nodes[node_id]
        if node["label"] == "Article" and self.paragraphs.get(node_id):
            parts = sorted(self.paragraphs[node_id], key=_paragraph_order)
            return "\n".join(self.nodes[p]["props"].get("text", "") for p in parts if p in self.nodes)
        return node["props"].get("text", "")

    def _usable(self, edge: Mapping[str, Any]) -> bool:
        """v1.2 (rà soát M2): đích dùng được khi cạnh VÀ node trong phạm vi, và có văn bản — node giữ chỗ (Điều chưa
        tách được, in_scope=False, không text) từng thành khối '[R1307:Art99] ' rỗng trong ngữ cảnh."""
        target = edge["target"]
        if not edge.get("props", {}).get("in_scope", True) or target not in self.nodes:
            return False
        return bool(self.nodes[target]["props"].get("in_scope", True)) and bool(self.text_of(target).strip())

    def referenced(self, node_id: str) -> List[Dict[str, Any]]:
        """Đích REFERS_TO 1 bước (không trùng, bỏ tự dẫn chiếu), theo thứ tự xuất hiện trong đồ thị. v1.2 (M2): khoản
        của một Điều cũng được dẫn chiếu nguyên Điều → 'covered' (văn bản Điều đã chứa khoản đó, không lặp lại)."""
        out, seen = [], {node_id}
        for e in self.refs.get(node_id, []):
            target = e["target"]
            if target in seen:
                continue
            seen.add(target)
            out.append({"target": target, "kind": e.get("props", {}).get("kind"), "usable": self._usable(e)})
        whole = {r["target"] for r in out if r["usable"] and self.paragraphs.get(r["target"])}
        for r in out:
            parent = re.sub(r"\(\d+\)$", "", r["target"])
            r["covered"] = parent != r["target"] and parent in whole and r["target"] in self.paragraphs[parent]
        return out


def clause_only_chunk(chunk: Mapping[str, Any]) -> Dict[str, Any]:
    """Cấu hình X: chỉ khoản luật. Khoản có `years` (tập Đức) mang theo năm để các kiểm trên log giới hạn hồ sơ."""
    base = {"article_id": chunk["node_id"], "article_title": chunk.get("article_title", ""),
            "text": chunk["text"], "context_refs": [], "skipped_refs": [], "truncated_chars": 0}
    return {**base, "years": list(chunk["years"])} if chunk.get("years") else base


def graph_context_chunk(chunk: Mapping[str, Any], index: LegalGraphIndex) -> Dict[str, Any]:
    """Cấu hình Y: khoản luật + văn bản các khoản dẫn chiếu (1 bước trên đồ thị)."""
    base = clause_only_chunk(chunk)
    blocks, used, skipped, cut, budget = [], [], [], 0, MAX_TOTAL_REF_CHARS
    for ref in index.referenced(chunk["node_id"]):
        if ref.get("covered"):
            continue  # đã nằm trong văn bản Điều cha (vẫn được dẫn chiếu) — không phải bị bỏ
        if not ref["usable"]:
            skipped.append(ref["target"])
            continue
        text = index.text_of(ref["target"])
        limit = min(MAX_REF_CHARS, budget)
        if limit <= 0:
            skipped.append(ref["target"])
            cut += len(text)
            continue
        shown = text if len(text) <= limit else text[:limit] + TRUNCATED
        cut += max(0, len(text) - limit)
        budget -= min(len(text), limit)
        blocks.append(f"[{ref['target']}] {shown}")
        used.append(ref["target"])
    if blocks:
        base["text"] = chunk["text"] + REF_HEADER + "\n" + "\n".join(blocks)
    return {**base, "context_refs": used, "skipped_refs": skipped, "truncated_chars": cut}


def _tokens(text: str) -> List[str]:
    return re.findall(r"\w+", text.lower())


def _base_id(node_id: str) -> str:
    return node_id.split("@", 1)[0]


class BM25ClauseIndex:
    """
    Đường cơ sở RAG truyền thống — cấu hình R (đăng ký bổ sung B4, docs/V2_DANG_KY_TRUOC.md): BM25Okapi trên MỌI
    node có văn bản của đồ thị luật (khoản, Điều không tách khoản, Phụ lục), KHÔNG dùng cạnh. Truy vấn = nguyên văn
    khoản. Bỏ chính khoản đó (và các phiên bản năm khác của nó); khoản có `years` chỉ lấy node có năm giao nhau.
    """

    def __init__(self, index: LegalGraphIndex) -> None:
        from rank_bm25 import BM25Okapi

        self.index = index
        self.ids = [nid for nid, n in index.nodes.items()
                    if (n["label"] in ("Paragraph", "Annex") or (n["label"] == "Article" and not index.paragraphs.get(nid)))
                    and index.text_of(nid).strip()]
        self.bm25 = BM25Okapi([_tokens(index.text_of(i)) for i in self.ids])

    def ranked(self, chunk: Mapping[str, Any]) -> List[str]:
        """Node theo điểm BM25 giảm dần (hoà điểm: theo id, tất định)."""
        scores = self.bm25.get_scores(_tokens(chunk["text"]))
        own, years = _base_id(chunk["node_id"]), set(chunk.get("years") or [])

        def allowed(nid: str) -> bool:
            node_years = set((self.index.nodes[nid].get("props") or {}).get("years") or [])
            return _base_id(nid) != own and (not years or not node_years or bool(years & node_years))

        order = sorted(range(len(self.ids)), key=lambda i: (-scores[i], self.ids[i]))
        return [self.ids[i] for i in order if scores[i] > 0 and allowed(self.ids[i])]


def rag_context_chunk(chunk: Mapping[str, Any], index: LegalGraphIndex, bm25: BM25ClauseIndex) -> Dict[str, Any]:
    """Cấu hình R: khoản luật + các khoản BM25 xếp đầu, NGÂN SÁCH KÝ TỰ KHỚP TỪNG KHOẢN với Y (= số ký tự ngữ cảnh mà
    graph_context_chunk thêm cho chính khoản đó; Y không có ngữ cảnh → R cũng không). Cùng giới hạn MAX_REF_CHARS mỗi
    khoản; khoản cuối cắt cho vừa ngân sách. So R với Y chỉ khác NGUỒN ngữ cảnh (truy xuất văn bản vs cạnh đồ thị)."""
    base = clause_only_chunk(chunk)
    budget = len(graph_context_chunk(chunk, index)["text"]) - len(chunk["text"])
    if budget <= 0:
        return {**base, "retrieval": "bm25", "budget_chars": 0}
    blocks: List[str] = []
    used: List[str] = []
    remaining = budget - len(REF_HEADER)
    for nid in bm25.ranked(chunk):
        prefix = f"\n[{nid}] "
        room = min(MAX_REF_CHARS, remaining - len(prefix))
        if room <= len(TRUNCATED):
            break
        text = index.text_of(nid)
        shown = text if len(text) <= room else text[:room - len(TRUNCATED)] + TRUNCATED
        blocks.append(prefix + shown)
        used.append(nid)
        remaining -= len(prefix) + len(shown)
    text = chunk["text"] + REF_HEADER + "".join(blocks) if blocks else chunk["text"]
    return {**base, "text": text, "context_refs": used, "retrieval": "bm25", "budget_chars": budget}


def graph_context_chunk_v2(chunk: Mapping[str, Any], index: LegalGraphIndex,
                           legal_v2: Mapping[str, Any]) -> Dict[str, Any]:
    """v2 (docs/V2_DANG_KY_TRUOC.md thành phần 7–8): ngữ cảnh Y + định nghĩa thuật ngữ khoản dùng (USES_TERM)
    + ghi chú phạm vi quốc gia. Phần đầu giống hệt Y; định nghĩa có ngân sách riêng (legal_enrichment)."""
    from ..kg.legal_enrichment import definitions_context

    base = graph_context_chunk(chunk, index)
    nid = chunk["node_id"]
    note = legal_v2.get("scope_notes", {}).get(nid, "")
    return {**base, "text": base["text"] + definitions_context(nid, legal_v2) + note,
            "definitions": [d["term"] for d in legal_v2.get("definitions", {}).get(nid, [])],
            "scope_note": bool(note)}
