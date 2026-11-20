"""
Tách văn bản Quy định EU (Regulation) thành từng khoản, có tiền tố văn bản, và nhận diện dẫn chiếu.

Dùng cho bộ dữ liệu thứ hai (BPIC2018 – Chính sách Nông nghiệp Chung, CAP):
  R1306 = Regulation (EU) No 1306/2013   (tài chính, quản lý, kiểm soát, IACS)
  R1307 = Regulation (EU) No 1307/2013   (các chương trình trả tiền trực tiếp)
  R640  = Delegated Regulation (EU) No 640/2014    (IACS, phạt hành chính)
  R809  = Implementing Regulation (EU) No 809/2014 (đơn, kiểm tra, mẫu kiểm tra)

Khác parse_directive.py (riêng Directive 2008/48/EC): mã khoản có tiền tố văn bản ('R1306:Art75(1)'),
bắt đầu sau 'ADOPTED THIS REGULATION', bỏ tiêu đề TITLE/CHAPTER/Section và header trang Official Journal,
và phân biệt dẫn chiếu TRONG văn bản với dẫn chiếu SANG văn bản khác ('of Regulation (EU) No 1306/2013').
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

from .eu_references import find_references as _find_references

CAP_REGULATIONS: Dict[str, str] = {
    "1306/2013": "R1306",
    "1307/2013": "R1307",
    "640/2014": "R640",
    "809/2014": "R809",
}

_START = re.compile(r"HAV?E?S? ADOPTED THIS REGULATION:?")
_END = re.compile(r"\nANNEX\b|This Regulation shall be binding in its entirety")
_ARTICLE = re.compile(r"^Article\s+(\d+)$")
# v1.2 (rà soát dữ liệu H3): cả 'CHAPTER 2', 'SECTION 3' (số Ả Rập) — trước đây chỉ số La Mã → tiêu đề lẫn vào khoản
_STRUCTURE = re.compile(r"^(?:TITLE|CHAPTER|SECTION)\s+(?:[IVXLC]+|\d+)$", re.IGNORECASE)
_SPACED = re.compile(r"^(?:\S ){2,}\S(?: (?:\S ){1,}\S)*$")  # 'S e c t i o n 1', 'G e n e r a l ...'
_HEADER_LINE = re.compile(
    r"^(?:\d{1,2}\.\d{1,2}\.\d{4}|EN|L\s*\d+/\d+|Official Journal of the European Union"
    r"|.*\bOfficial Journal of the European Union\s+(?:L\s*\d+/\d+|\d{1,2}\.\d{1,2}\.\d{4}).*)$"
)
# v1.2 (rà soát dữ liệu H3): '( 1 ) Council Regulation …' (khoảng trắng trước ')') cũng là chú thích
# 'p 48).' (thiếu dấu chấm sau p — R809:Art5, phát hiện khi đối chiếu bản hợp nhất 2026-11-19) cũng là kết thúc chú thích
_FOOTNOTE = re.compile(r"\n\(\s*\n?\s*\d+\s*\)\s[\s\S]{0,700}?(?:p\.?\s*\d+\)\.|Official Journal\)\.)")
_KEEP_HYPHEN = r"(?:open|out|pre|non|cross|self|co|sub|inter|over|under|multi|on|ex|de|agro|agri|re)"
_MONTHS = r"January|February|March|April|May|June|July|August|September|October|November|December"
_NUMERIC = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:calendar\s+|working\s+)?(?:days?|months?|years?|weeks?|hectares?|ha\b|EUR|%|percent)"
    r"|\bEUR\s*\d+(?:[\s.,]\d+)*"
    rf"|\b\d{{1,2}}\s+(?:{_MONTHS})\b",
    re.IGNORECASE,
)


# ------------------------------------------------------------------------------ cleaning


def _drop_structure_headings(lines: List[str]) -> List[str]:
    """Bỏ TITLE/CHAPTER/Section và (các) dòng tiêu đề đi kèm cho tới 'Article N' kế tiếp."""
    out: List[str] = []
    skipping = False
    for line in lines:
        if _STRUCTURE.match(line) or _SPACED.match(line):
            skipping = True
            continue
        if skipping and not _ARTICLE.match(line):
            continue
        skipping = False
        out.append(line)
    return out


def _clean(text: str) -> List[str]:
    text = _FOOTNOTE.sub("\n", text)
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not _HEADER_LINE.match(ln)]
    return _drop_structure_headings(lines)


def _join(lines: List[str]) -> str:
    text = "\n".join(lines)
    text = text.replace("­\n", "").replace("­", "")  # gạch nối mềm: luôn nối từ
    text = re.sub(rf"\b({_KEEP_HYPHEN})[-�]\n([a-zA-Z])", r"\1-\2", text, flags=re.IGNORECASE)
    text = re.sub(r"([a-zA-Z])[-�]\n([a-zA-Z])", r"\1\2", text)
    return text


# ------------------------------------------------------------------------------ splitting


def _article_blocks(lines: List[str]) -> List[tuple]:
    """(số điều, các dòng) theo thứ tự Article 1, 2, 3 ... (bỏ 'Article N' xuất hiện lạc thứ tự)."""
    blocks, current, expected = [], None, 1
    for line in lines:
        m = _ARTICLE.match(line)
        if m and int(m.group(1)) == expected:
            current = (expected, [])
            blocks.append(current)
            expected += 1
        elif current is not None:
            current[1].append(line)
    return blocks


def _title_and_body(lines: List[str]) -> tuple:
    if not lines:
        return "", []
    title = [lines[0]]
    i = 1
    while i < len(lines) and lines[i][:1].islower():
        title.append(lines[i])
        i += 1
    return " ".join(title), lines[i:]


def _paragraphs(body: str) -> List[str]:
    """Tách khoản chỉ tại số KẾ TIẾP đúng thứ tự (1., 2., …). v1.2 (rà soát dữ liệu H2): dòng xuống hàng bắt đầu bằng
    năm ('2014.', '2015. In order …') từng thành khoản giả R1307:Art21 / R1307:Art25(2015) và cắt cụt khoản trước."""
    parts = re.split(r"\n(?=\d+\.\s)", body)
    out: List[str] = []
    expected = 1
    for part in parts:
        m = re.match(r"^(\d+)\.\s", part)
        if m and int(m.group(1)) == expected:
            out.append(part)
            expected += 1
        elif out:
            # số không đúng thứ tự (kể cả '2014.' ở cuối khối) → phần tiếp của khoản trước
            out[-1] = out[-1] + "\n" + part
        else:
            out.append(part)
    return out


_BROKEN = re.compile(r"\b([a-z]{2,})\n([a-z]{2,})\b")


def rejoin_broken_words(text: str) -> str:
    """
    PDF R640 bỏ mất gạch nối ở chỗ ngắt từ cuối dòng ('legisla\\ntion', 'condi\\ntions' — phát hiện khi đối chiếu
    bản hợp nhất 2026-11-19). Nối hai mảnh CHỈ khi từ ghép xuất hiện ở chỗ khác trong CÙNG văn bản và mảnh đầu không
    đứng riêng ở đâu khác (dữ liệu tự chứng, không dùng từ điển ngoài); còn lại giữ là hai từ ('of\\nthe').
    """
    words: Dict[str, int] = {}
    for w in re.findall(r"[a-z]+", text.replace("-\n", "").lower()):
        words[w] = words.get(w, 0) + 1

    def fix(m: "re.Match[str]") -> str:
        a, b = m.group(1), m.group(2)
        return a + b if words.get(a + b, 0) > 0 and words.get(a, 0) <= 1 else m.group(0)

    return _BROKEN.sub(fix, text)


def split_articles(text: str, doc_id: str) -> List[Dict[str, Any]]:
    """Tách phần điều khoản (sau 'ADOPTED THIS REGULATION', trước phụ lục) thành từng khoản."""
    text = rejoin_broken_words(text)
    start = _START.search(text)
    body = text[start.end():] if start else text
    end = _END.search(body)
    body = body[: end.start()] if end else body

    chunks: List[Dict[str, Any]] = []
    for art_num, lines in _article_blocks(_clean(body)):
        title, body_lines = _title_and_body(lines)
        for para in _paragraphs(_join(body_lines)):
            para = re.sub(r"\s+", " ", para).strip()
            if not para:
                continue
            m = re.match(r"^(\d+)\.\s", para)
            node_id = f"{doc_id}:Art{art_num}({m.group(1)})" if m else f"{doc_id}:Art{art_num}"
            chunks.append({
                "node_id": node_id,
                "doc_id": doc_id,
                "article_title": title,
                "text": para,
                "has_numeric_bound": bool(_NUMERIC.search(para)),
            })
    return chunks


# ---------------------------------------------------------------------------- references


def find_references(text: str, doc_id: str, known: Mapping[str, str] = CAP_REGULATIONS,
                    article: Optional[str] = None) -> List[Dict[str, Any]]:
    """Dẫn chiếu trong khoản — xem src/preprocessing/eu_references.py (danh sách/khoảng, 'paragraph N', Phụ lục)."""
    return _find_references(text, doc_id, known, article)


# ------------------------------------------------------------------------------ annexes

_ANNEX_HEAD = re.compile(r"\nANNEX(?:\s+([IVXLC]+))?\s*\n")


def split_annexes(text: str, doc_id: str) -> List[Dict[str, Any]]:
    """
    F-ANNEX (kiểm toán đợt 2): Phụ lục sau phần điều khoản → mỗi Phụ lục một mục 'R…:AnnexX' ('R809:Annex' nếu
    không đánh số). Phụ lục thường là bảng: chữ trích từ PDF rời rạc nhưng vẫn đọc được làm ngữ cảnh.
    """
    start = _START.search(text)
    body = text[start.end():] if start else text
    heads = list(_ANNEX_HEAD.finditer(body))
    out: List[Dict[str, Any]] = []
    for i, h in enumerate(heads):
        block = body[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(body)]
        lines = _clean(block)
        if not lines:
            continue
        content = re.sub(r"\s+", " ", _join(lines)).strip()
        roman = h.group(1) or "I"  # phụ lục duy nhất không đánh số ('ANNEX') = Phụ lục I — R809 dẫn chiếu 'Annex I'
        out.append({"node_id": f"{doc_id}:Annex{roman}", "doc_id": doc_id, "article_title": lines[0].strip(),
                    "text": content, "has_numeric_bound": bool(_NUMERIC.search(content)), "kind": "annex"})
    return out


# ---------------------------------------------------------------------------------- PDF


def parse_regulation_pdf(pdf_path: Union[str, Path], doc_id: str) -> List[Dict[str, Any]]:
    """Đọc PDF (EUR-Lex) và trả về các khoản kèm dẫn chiếu."""
    import pymupdf

    with pymupdf.open(str(pdf_path)) as doc:
        text = "\n".join(page.get_text("text") for page in doc)
    chunks = split_articles(text, doc_id)
    for chunk in chunks:
        article = re.sub(r"\(\d+\)$", "", chunk["node_id"].split(":", 1)[1])
        chunk["refs"] = find_references(chunk["text"], doc_id, article=article)
    return chunks


def parse_regulation_annexes(pdf_path: Union[str, Path], doc_id: str) -> List[Dict[str, Any]]:
    """Phụ lục của PDF (EUR-Lex), kèm dẫn chiếu."""
    import pymupdf

    with pymupdf.open(str(pdf_path)) as doc:
        text = "\n".join(page.get_text("text") for page in doc)
    annexes = split_annexes(text, doc_id)
    for annex in annexes:
        annex["refs"] = find_references(annex["text"], doc_id)
    return annexes
