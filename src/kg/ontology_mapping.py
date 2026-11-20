"""
v2 — nối tầng Pháp lý với tầng Tiến trình qua ontology loại giấy tờ (docs/V2_DANG_KY_TRUOC.md thành phần 6, 9, 10).

  ontology   data/review/bpic2018_ontology.json — Claude soạn, NGƯỜI DUYỆT; chỉ dùng khi status = "approved".
  MAPS_TO    khoản luật → loại giấy tờ khi khoản nhắc tới một thuật ngữ pháp lý của loại đó (khớp cụm dài nhất).
  gợi ý      một dòng thêm vào câu hỏi sinh nêu các loại giấy tờ liên quan; KHÔNG xoá activity nào khỏi Γ.
"""

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Union

from .legal_graph_builder import find_mentions

APPROVED = "approved"


def load_ontology(path: Union[str, Path]) -> Optional[dict]:
    """Ontology đã duyệt, hoặc None (không có file / chưa duyệt) — hệ thống khi đó chạy như không có ontology."""
    p = Path(path)
    if not p.exists():
        return None
    onto = json.loads(p.read_text(encoding="utf-8"))
    return onto if onto.get("status") == APPROVED else None


def doctype_terms(text: str, ontology: Optional[Mapping[str, Any]]) -> Dict[str, List[str]]:
    """Loại giấy tờ → thuật ngữ pháp lý của nó được nhắc trong text (khớp cụm dài nhất). Căn cứ của cạnh MAPS_TO."""
    if not ontology:
        return {}
    term_to_doctypes: Dict[str, Set[str]] = {}
    for doctype, d in ontology.get("doctypes", {}).items():
        for term in [*d.get("legal_terms", []), *d.get("legal_terms_de", [])]:  # tiếng Đức: tập Đức (v2)
            term_to_doctypes.setdefault(term, set()).add(doctype)
    out: Dict[str, Set[str]] = {}
    for term in find_mentions(text, term_to_doctypes):
        for dt in term_to_doctypes[term]:
            out.setdefault(dt, set()).add(term)
    return {dt: sorted(terms) for dt, terms in sorted(out.items())}


def doctype_mentions(text: str, ontology: Optional[Mapping[str, Any]]) -> List[str]:
    return list(doctype_terms(text, ontology))


def hint_from_doctypes(doctypes: Iterable[str], meanings: Mapping[str, str]) -> str:
    """Dòng gợi ý cho câu hỏi sinh từ các loại giấy tờ mà khoản được nối tới (MAPS_TO) và nghĩa của chúng."""
    ordered = sorted(doctypes)
    if not ordered:
        return ""
    described = "; ".join(f"'{d}' ({meanings[d]})" for d in ordered)
    return ("Knowledge-graph note: the clause uses legal terms linked to these document types of the process: "
            f"{described}. Their activities are a starting point; all activities of Γ remain allowed.")


def generation_hint(text: str, ontology: Optional[Mapping[str, Any]]) -> str:
    """Như hint_from_doctypes nhưng tính MAPS_TO tại chỗ từ ontology (khi dựng tầng Cầu nối và để kiểm đối chiếu).
    Lúc sinh luật, hệ thống đọc MAPS_TO từ KG (mapping_graph_builder.load_bridge) — một nguồn duy nhất."""
    doctypes = doctype_mentions(text, ontology)
    return hint_from_doctypes(doctypes, {d: ontology["doctypes"][d]["meaning"] for d in doctypes}) if doctypes else ""
