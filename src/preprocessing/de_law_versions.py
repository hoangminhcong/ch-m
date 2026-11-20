"""
Tập positive mới (docs/V2_DANG_KY_TRUOC.md mục 5.1): văn bản InVeKoSV / DirektZahlDurchfV có hiệu lực tại một ngày.

Nguồn: trang so sánh phiên bản của buzer.de (một trang mỗi lần sửa đổi, ngày = ngày có hiệu lực của bản mới):
  dòng điều hướng 'nächste Fassung von § X'  → bắt đầu khối của § X
  ô colspan=2 / 'hunc'                        → đoạn không đổi (thuộc cả bản cũ lẫn bản mới)
  ô 'halt' / 'hneu'                           → đoạn của bản cũ / bản mới
  span 'hdiff' (nhãn), 'satz' (số câu), a 'noprint' (điều hướng) → bỏ
Văn bản của § X tại ngày d: bản MỚI của lần sửa gần nhất có hiệu lực ≤ d; chưa có lần sửa nào ≤ d → bản CŨ của lần
sửa đầu tiên sau d; § chưa từng sửa → bản hiện hành. Văn bản rỗng = § chưa tồn tại (None).
Không gọi mạng (tải trang: scripts/fetch_de_laws.py).
"""

import html
import re
from datetime import date
from html.parser import HTMLParser
from typing import Any, Dict, List, Mapping, Optional, Sequence

_SKIP_CLASSES = {"hdiff", "satz", "noprint"}
_SECTION = re.compile(r"Fassung (?:von )?§\s*([0-9]+[a-z]?)")
_EFFECTIVE = re.compile(r"in der am (\d{2})\.(\d{2})\.(\d{4}) geltenden Fassung")
_ABSATZ = re.compile(r"(?m)^\((\d+[a-z]?)\)\s")


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: List[Dict[str, Any]] = []
        self.headers: List[str] = []
        self._stack: List[bool] = []
        self._cell: Optional[Dict[str, Any]] = None

    def _skipping(self) -> bool:
        return any(self._stack)

    def handle_starttag(self, tag: str, attrs: List) -> None:
        a = dict(attrs)
        classes = set((a.get("class") or "").split())
        if tag == "br":
            if self._cell is not None and not self._skipping():
                self._cell["text"].append("\n")
            return
        if tag == "img":
            return
        self._stack.append(bool(classes & _SKIP_CLASSES) and tag in ("span", "a"))
        if tag == "tr":
            self.rows.append({"class": a.get("class") or "", "cells": []})
        elif tag in ("td", "th"):
            self._cell = {"class": a.get("class") or "", "text": [], "th": tag == "th"}
            if tag == "td" and self.rows:
                self.rows[-1]["cells"].append(self._cell)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("br", "img"):
            return
        if self._stack:
            self._stack.pop()
        if tag == "th" and self._cell is not None:
            self.headers.append("".join(self._cell["text"]))
            self._cell = None
        elif tag == "td":
            self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None and not self._skipping():
            self._cell["text"].append(data)


def _clean(parts: Sequence[str]) -> str:
    text = html.unescape(" ".join(parts))
    text = re.sub(r"[ \t\r\f\v ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{2,}", "\n", text).strip()


def parse_version_page(page: str) -> Dict[str, Any]:
    """→ {'effective': date, 'sections': {'7': {'old': str, 'new': str}, …}} theo thứ tự xuất hiện."""
    p = _TableParser()
    p.feed(page)
    m = next((_EFFECTIVE.search(h) for h in p.headers if _EFFECTIVE.search(h)), None)
    if m is None:
        raise ValueError("Không thấy ngày hiệu lực ('in der am TT.MM.JJJJ geltenden Fassung') trong trang.")
    sections: Dict[str, Dict[str, List[str]]] = {}
    # Trang sửa một § (al…-n.htm): nhãn ở tiêu đề cột ('§ 12a X a.F. …'); trang nhiều §: tiêu đề là tên văn bản.
    head = re.match(r"\s*§§?\s*([0-9]+[a-z]?)", html.unescape(p.headers[0])) if p.headers else None
    current: Optional[str] = head.group(1) if head else None
    if current:
        sections[current] = {"old": [], "new": []}
    for row in p.rows:
        texts = ["".join(c["text"]) for c in row["cells"]]
        if "noprint" in row["class"]:
            label = next((s.group(1) for t in texts if (s := _SECTION.search(html.unescape(t)))), None)
            if label and label != current:
                current = label
                sections.setdefault(current, {"old": [], "new": []})
            continue
        if current is None or not row["cells"]:
            continue
        classes = [c["class"] for c in row["cells"]]
        if len(row["cells"]) == 2 and "halt" in classes[0] and "hneu" in classes[1]:
            sections[current]["old"].append(texts[0])
            sections[current]["new"].append(texts[1])
        else:
            joined = " ".join(texts)
            sections[current]["old"].append(joined)
            sections[current]["new"].append(joined)
    return {"effective": date(int(m.group(3)), int(m.group(2)), int(m.group(1))),
            "sections": {k: {"old": _clean(v["old"]), "new": _clean(v["new"])} for k, v in sections.items()}}


def text_at(section: str, day: date, versions: Sequence[Mapping[str, Any]],
            current: Mapping[str, str]) -> Optional[str]:
    changes = sorted((v for v in versions if section in v["sections"]), key=lambda v: v["effective"])
    before = [v for v in changes if v["effective"] <= day]
    if before:
        return before[-1]["sections"][section]["new"] or None
    if changes:
        return changes[0]["sections"][section]["old"] or None
    return current.get(section)


_ANNEX = re.compile(r"\n(?:Anlage|Anhang)\s+\d")


def section_text_or_none(section: str, text: Optional[str]) -> Optional[str]:
    """Văn bản của ĐÚNG § này hoặc None. Rà soát 2026-11-18 H5: khi văn bản được đánh số lại (§ 35 cũ → § 36),
    cột cũ của trang so sánh là § KHÁC — dòng tiêu đề '§ N' phải khớp mã §. Khối Anlage gắn sau § cuối bị cắt."""
    if not text:
        return None
    m = re.match(r"§§?\s*([0-9]+[a-z]?)\b", text)
    if not m or m.group(1) != section:
        return None
    cut = _ANNEX.search(text)
    return text[:cut.start()].rstrip() if cut else text


def split_absaetze(section_text: str) -> List[Dict[str, Optional[str]]]:
    """'§ N Titel\\n(1) …\\n(2) …' → các khoản (Absatz). Không có '(n)' → một mục, absatz = None."""
    head, _, body = section_text.partition("\n")
    title = re.sub(r"^§\s*[0-9]+[a-z]?\s*", "", head).strip()
    starts = [m.start() for m in _ABSATZ.finditer(body)]
    if not starts:
        return [{"absatz": None, "title": title, "text": body.strip()}]
    bounds = [*starts, len(body)]
    return [{"absatz": _ABSATZ.match(body, s).group(1), "title": title, "text": body[s:e].strip()}
            for s, e in zip(bounds, bounds[1:], strict=False)]  # cặp liền kề: dài hơn kém 1 là đúng
