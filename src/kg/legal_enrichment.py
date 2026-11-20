"""
v2 — tầng Pháp lý giàu hơn (docs/V2_DANG_KY_TRUOC.md mục 4, thành phần 7–8). Tất định, không dùng LLM.

  DefinedTerm   thuật ngữ định nghĩa dạng '(a) "term" means …' / '(1) ‘term’ means …' trong khoản luật.
  DEFINES       khoản định nghĩa → DefinedTerm.
  USES_TERM     khoản → DefinedTerm mà khoản dùng (khớp cụm dài nhất, có dạng số nhiều -s).
                Phạm vi: định nghĩa áp cho văn bản chứa nó; văn bản có khoản định nghĩa DẪN CHIẾU tới khoản định
                nghĩa của văn bản khác thì dùng cả định nghĩa đó (VD R640:Art2(1) dẫn nhập R1307:Art4(1)).
                Định nghĩa "for the purposes of this Article / paragraph" chỉ áp trong cùng Article.
  scope_note    khoản nêu tên quốc gia thành viên mà không có nước của log (Đức) → ghi chú phạm vi.

Lý do v1 thiếu: REFERS_TO chỉ theo dẫn chiếu tường minh; 135/218 khoản trong phiếu dùng thuật ngữ đã định nghĩa
nhưng chỉ 13 khoản dẫn chiếu tới khoản định nghĩa → ngữ cảnh Y không bao giờ có định nghĩa.
"""

import re
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from .legal_graph_builder import find_mentions

LOG_COUNTRY = "Germany"
MIN_TERM_CHARS = 4  # 'act' (R809:Art64) khớp nhầm động từ 'act'
MAX_DEF_CHARS = 600
MAX_TOTAL_DEF_CHARS = 3000
DEF_HEADER = "\n\nDefinitions that apply (retrieved via the legal knowledge graph):"
MEMBER_STATES = ("Belgium", "Bulgaria", "Czech Republic", "Czechia", "Denmark", "Germany", "Estonia", "Ireland",
                 "Greece", "Spain", "France", "Croatia", "Italy", "Cyprus", "Latvia", "Lithuania", "Luxembourg",
                 "Hungary", "Malta", "Netherlands", "Austria", "Poland", "Portugal", "Romania", "Slovenia",
                 "Slovakia", "Finland", "Sweden", "United Kingdom")
_Q_OPEN, _Q_CLOSE = "‘\"“'", "’\"”'"
# '(a) "farmer", means' (dấu phẩy sau nháy, R1306:Art2(1)) cũng là định nghĩa — rà soát 2026-11-18 M1
_MARKER = re.compile(rf"\((\w{{1,3}})\)\s*[{_Q_OPEN}]([^{_Q_CLOSE}]{{2,80}})[{_Q_CLOSE}],?\s*"
                     r"(?:\([^)]*\)\s*)?(?:means|shall mean)\b:?\s*")
# Phạm vi văn bản chỉ khi nói rõ 'this Regulation' (hoặc không nói gì); 'for the purposes of this Article / Chapter
# / Title / Section …' hay 'for the purposes of establishing …' → chỉ trong cùng Article (an toàn: không có cấu
# trúc Chương trong dữ liệu để xác định phạm vi rộng hơn) — rà soát M1.
_ARTICLE_SCOPE = re.compile(r"for the purposes? of (?!this Regulation)", re.IGNORECASE)
_SENTENCE_END = re.compile(r"\.\s+(?=[A-Z])")


def extract_cap_definitions(text: str) -> List[Tuple[str, str]]:
    """[(thuật ngữ, định nghĩa)] theo thứ tự; định nghĩa kéo tới thuật ngữ kế tiếp (giữ các mục (i), (ii) bên trong)."""
    marks = list(_MARKER.finditer(text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        if i + 1 == len(marks):  # định nghĩa cuối: dừng ở hết câu, không nuốt câu sau (rà soát M1)
            stop = _SENTENCE_END.search(text, m.end(), end)
            end = stop.start() if stop else end
        body = re.sub(r"\s+", " ", text[m.end():end]).strip()
        body = re.sub(r"(?:;\s*(?:and|or)?|[.;,])\s*$", "", body).strip()
        out.append((m.group(2).strip(), body))
    return out


def _article(node_id: str) -> str:
    return node_id.split("(")[0]


def _definition_sources(chunks: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    sources = {}
    for c in chunks:
        defs = extract_cap_definitions(c["text"])
        if defs:
            head = c["text"][:_MARKER.search(c["text"]).start()]
            scope = "article" if _ARTICLE_SCOPE.search(head) else "document"
            sources[c["node_id"]] = {"doc": c.get("doc_id") or c["node_id"].split(":")[0], "scope": scope,
                                     "defs": defs, "refs": [r["target"] for r in c.get("refs", [])]}
    return sources


def _terms_for(chunk: Mapping[str, Any], sources: Mapping[str, Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    """(term, definition, source) áp cho khoản: định nghĩa cùng văn bản trước, rồi định nghĩa được dẫn nhập."""
    doc = chunk.get("doc_id") or chunk["node_id"].split(":")[0]
    own = [s for s, v in sources.items() if v["doc"] == doc
           and (v["scope"] == "document" or _article(s) == _article(chunk["node_id"]))]
    # dẫn chiếu 'Article 4' khớp khoản định nghĩa 'Art4(1)': so theo Article (rà soát M1 — trước khớp đúng id)
    cited = {_article(t) for s in own if sources[s]["scope"] == "document" for t in sources[s]["refs"]}
    imported = sorted(t for t, v in sources.items()
                      if _article(t) in cited and v["doc"] != doc and v["scope"] == "document")
    out, seen = [], set()
    for s in [*own, *imported]:
        for term, definition in sources[s]["defs"]:
            if term.lower() not in seen and len(term) >= MIN_TERM_CHARS:
                seen.add(term.lower())
                out.append((term, definition, s))
    return out


def build_legal_enrichment(chunks: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    sources = _definition_sources(chunks)
    nodes = [{"id": f"Term:{s}:{t}", "label": "DefinedTerm", "props": {"term": t, "definition": d, "source": s,
                                                                         "scope": v["scope"]}}
             for s, v in sources.items() for t, d in v["defs"] if len(t) >= MIN_TERM_CHARS]
    edges = [{"source": n["props"]["source"], "target": n["id"], "type": "DEFINES", "props": {}} for n in nodes]
    uses: Dict[str, List[str]] = {}
    definitions: Dict[str, List[Dict[str, str]]] = {}
    for c in chunks:
        if c["node_id"] in sources:
            continue
        terms = _terms_for(c, sources)
        found = find_mentions(c["text"], [t for t, _, _ in terms])
        if not found:
            continue
        used = [(t, d, s) for t, d, s in terms if t in found]
        uses[c["node_id"]] = sorted(t for t, _, _ in used)
        definitions[c["node_id"]] = [{"term": t, "definition": d, "source": s}
                                     for t, d, s in sorted(used, key=lambda x: (-len(x[0]), x[0]))]
        edges += [{"source": c["node_id"], "target": f"Term:{s}:{t}", "type": "USES_TERM", "props": {}}
                  for t, _, s in used]
    return {"graph": {"nodes": nodes, "edges": edges}, "uses": uses, "definitions": definitions}


def definitions_context(node_id: str, enrichment: Mapping[str, Any]) -> str:
    """Khối định nghĩa cho ngữ cảnh v2: thuật ngữ dài trước, mỗi định nghĩa ≤ MAX_DEF_CHARS, tổng ≤ MAX_TOTAL."""
    blocks, budget = [], MAX_TOTAL_DEF_CHARS
    for d in enrichment.get("definitions", {}).get(node_id, []):
        text = d["definition"] if len(d["definition"]) <= MAX_DEF_CHARS else d["definition"][:MAX_DEF_CHARS] + " […]"
        line = f"[{d['source']}] ‘{d['term']}’ means {text}"
        if len(line) > budget:
            break
        budget -= len(line)
        blocks.append(line)
    return DEF_HEADER + "\n" + "\n".join(blocks) if blocks else ""


def scope_note(text: str) -> str:
    """Khoản cho NGOẠI LỆ riêng một số quốc gia ('by way of derogation …', '… may …') mà không có nước của log → ghi
    chú phạm vi. Chỉ xét câu có dấu hiệu ngoại lệ: 'in the case of Croatia, …' (quy định thêm cho Croatia, không
    loại trừ Đức) không sinh ghi chú — rà soát 2026-11-18 M1."""
    sentences = [s for s in re.split(r"(?<=[.;])\s+", text) if re.search(r"derogat|\bmay\b", s, re.IGNORECASE)]
    named = sorted({s for s in MEMBER_STATES for sent in sentences if re.search(rf"\b{re.escape(s)}\b", sent)},
                   key=text.find)
    if not named or LOG_COUNTRY in named:
        return ""
    return (f"\n\nJurisdiction note (from the knowledge graph): the event log was recorded in {LOG_COUNTRY}. "
            f"Provisions of this clause that apply only to {', '.join(named)} do not apply to it.")
