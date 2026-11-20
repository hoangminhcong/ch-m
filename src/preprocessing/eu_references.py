"""
Nhận diện dẫn chiếu trong một khoản luật EU (bộ CAP) — viết lại sau kiểm toán đợt 2 (2026-11-09).

  F-REFLIST  danh sách / khoảng: 'Articles 53, 55 and 56', 'Articles 43 to 46', 'Article 5(1), (2) and (4)',
             'Article 30(1) to (4)' → MỌI phần tử (trước đây chỉ phần tử đầu: mất 385 đích)
  F-REFMIS   cụm chen trong danh sách ('…, except paragraph 7(e), and Article 39 of Regulation …') → cả danh
             sách thuộc văn bản ghi ở CUỐI danh sách
  F-PARA     'paragraph 2', 'paragraphs 1 and 3 of this Article' → khoản cùng Điều; '… of that Article' → Điều
             vừa nhắc trước đó (trước đây không thành cạnh: 390 chỗ)
  F-ANNEX    'Annex I', 'Annexes II and III to Regulation …', 'the Annex' → node Phụ lục
Văn bản đích của danh sách 'Article…': 'of Regulation (EU) No N' (trong bộ 4 → R…, ngoài bộ → 'N:'),
'of that Regulation' (văn bản nhắc gần nhất trước đó), Directive / TFEU / TEU (ngoài bộ), còn lại = cùng văn bản.
Điểm '(a)', '(iii)' sau số điều/khoản được bỏ qua (đích là khoản, không phải điểm).
"""

import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

_ITEM = re.compile(r"(\d+[a-z]?)((?:\(\d+\))?)((?:\([a-z]{1,4}\))*)")
_BARE_PARA = re.compile(r"\((\d+)\)((?:\([a-z]{1,4}\))*)")
_BARE_POINT = re.compile(r"(?:\([a-z]{1,4}\))+")  # '(v)', '(b)(i)'
_ARTWORD = re.compile(r"Articles?\s+")
# v1.2 (rà soát dữ liệu H4): 'in conjunction with', 'as well as', 'with the exception of' nối tiếp danh sách —
# 'Article 132(2) in conjunction with Articles 7 and 10 of that Regulation' (R1307:Art37(3)) từng cho Art132 nội bộ
_SEP = re.compile(r"\s*(?:,\s*(?:and\s+|or\s+)?|\s+and/or\s+|\s+and\s+|\s+or\s+|\s+to\s+)"
                  r"|\s*,?\s+(?:in\s+conjunction\s+with|as\s+well\s+as|with\s+the\s+exception\s+of)\s+")
_QUAL = re.compile(r"\s*,?\s*except\s+[^,;]{1,40}?,\s*(?:and\s+|or\s+)?")
_START = re.compile(r"\bArticles?\s+(?=\d)")
_UNIT_AFTER = re.compile(r"\s*(?:calendar\s+|working\s+)?(?:days?|weeks?|months?|years?|hectares?|ha\b|%|per\s*cent|EUR|/)")
# v1.2 (rà soát dữ liệu H4): 'Regulation (EU) 1307/2013' (không 'No' — R1306:Art2 định nghĩa), '(Euratom, EC)',
# 'Regulation 1305/2013' (không ngoặc) — trước đây đều rơi về 'cùng văn bản'
_REG_ID = r"Regulation\s+(?:\((?:EU|EC|EEC|Euratom)(?:,\s*(?:Euratom|EC|EU))?\)\s+)?(?:No\s+)?(\d+/\d{2,4})\b"
_REG = rf"(?:the\s+)?(?:Commission\s+|Council\s+)?(?:Delegated\s+|Implementing\s+)?{_REG_ID}"
_ACT_REG = re.compile(rf"^\s*,?\s+(?:of|to|under)\s+{_REG}")
_ACT_THAT = re.compile(r"^\s*,?\s+(?:of\s+that\s+Regulation|thereof)\b")
_ACT_DIRECTIVE = re.compile(r"^\s*,?\s+(?:of|to)\s+(?:the\s+)?(?:Council\s+)?Directive\s+(\d+/\d+/E[CU]{1,2})")
_ACT_TREATY = re.compile(r"^\s*,?\s+(?:(?:of|to)\s+(?:the\s+)?(?:Treaty|TFEU|TEU)|TFEU|TEU)\b")
_ANY_REG = re.compile(_REG_ID)
_ANY_DIRECTIVE = re.compile(r"Directive\s+(\d+/\d+/E[CU]{1,2})")
_PARA_REF = re.compile(r"\bparagraphs?\s+(\d+)((?:\s*(?:,|and|or|to)\s*\d+)*)(?:\s*\([a-z]{1,4}\))*")
_ANNEX = re.compile(r"\bAnnex(?:es)?\s+([IVXLC]+)\b((?:\s*(?:,|and|to)\s*[IVXLC]+\b)*)")
_THE_ANNEX = re.compile(r"\b(?:the|this)\s+Annex\b(?!\s+[IVXLC]+\b)")
_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman_to_int(s: str) -> int:
    total = 0
    for i, ch in enumerate(s):
        v = _ROMAN[ch]
        total += -v if i + 1 < len(s) and _ROMAN[s[i + 1]] > v else v
    return total


def int_to_roman(n: int) -> str:
    out = ""
    for v, r in ((100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out, n = out + r, n - v
    return out


def _extend(items: List[str], last_art: str, art: str, para: str, pending_range: bool) -> None:
    """Thêm một điều; 'X to Y' (hai số điều trơn) → mở rộng X+1..Y."""
    if pending_range and not para and items and items[-1] == f"Art{last_art}" \
            and last_art.isdigit() and art.isdigit() and int(art) > int(last_art):
        items.extend(f"Art{n}" for n in range(int(last_art) + 1, int(art) + 1))
    else:
        items.append(f"Art{art}{para}")


def _extend_para(items: List[str], last_art: str, para: int, pending_range: bool) -> None:
    """Thêm khoản '(n)' của điều vừa nhắc; '(1) to (4)' → mở rộng."""
    prev = re.match(rf"Art{re.escape(last_art)}\((\d+)\)$", items[-1]) if items else None
    if pending_range and prev and para > int(prev.group(1)):
        items.extend(f"Art{last_art}({n})" for n in range(int(prev.group(1)) + 1, para + 1))
    else:
        items.append(f"Art{last_art}({para})")


def _read_chain(text: str, pos: int) -> Tuple[List[str], int]:
    """Đọc danh sách sau 'Article(s) ' tại pos → (các 'Art…' đã mở rộng khoảng, vị trí kết thúc)."""
    items: List[str] = []
    last_art: Optional[str] = None
    pending_range = False
    while True:
        m = _ITEM.match(text, pos)
        bare = None if m else _BARE_PARA.match(text, pos)
        if m:
            _extend(items, last_art or "", m.group(1), m.group(2), pending_range)
            last_art, pos = m.group(1), m.end()
        elif bare and last_art:
            _extend_para(items, last_art, int(bare.group(1)), pending_range)
            pos = bare.end()
        elif items and _BARE_POINT.match(text, pos):
            pos = _BARE_POINT.match(text, pos).end()
        else:
            break
        sep = _QUAL.match(text, pos) or _SEP.match(text, pos)
        if not sep:
            break
        nxt = sep.end()
        word = _ARTWORD.match(text, nxt)
        nxt = word.end() if word else nxt
        nxt_item = _ITEM.match(text, nxt)
        if nxt_item and _UNIT_AFTER.match(text, nxt_item.end()):
            break  # 'Article 7 and 30 days': 30 là thời hạn, không phải số điều
        if not (nxt_item or _BARE_PARA.match(text, nxt) or _BARE_POINT.match(text, nxt)):
            break
        pending_range = sep.group(0).strip() == "to"
        pos = nxt
    return items, pos


def _external(number: str, local: str, known: Mapping[str, str]) -> Dict[str, Any]:
    if number in known:
        return {"target": f"{known[number]}:{local}", "kind": "external", "in_scope": True}
    return {"target": f"{number}:{local}", "kind": "external", "in_scope": False}


def _resolve(after: str, before: str, doc_id: str, local: str, known: Mapping[str, str]) -> Dict[str, Any]:
    """Văn bản đích của một danh sách, đọc ngay sau danh sách."""
    reg = _ACT_REG.match(after)
    if reg:
        return _external(reg.group(1), local, known)
    that = _ACT_THAT.match(after)
    if that:
        # 'thereof' = văn bản nhắc GẦN NHẤT (Regulation hoặc Directive — R809:Art17(7) 'Directive 2002/57/EC …
        # Article 12 thereof'); 'of that Regulation' = Regulation gần nhất
        acts = [(m.start(), "reg", m.group(1)) for m in _ANY_REG.finditer(before)]
        if that.group(0).strip(" ,") == "thereof":
            acts += [(m.start(), "dir", m.group(1)) for m in _ANY_DIRECTIVE.finditer(before)]
        if acts:
            _, kind, number = max(acts)
            if kind == "dir":
                return {"target": f"{number}:{local}", "kind": "external", "in_scope": False}
            return _external(number, local, known)
        # v1.2 (H4): 'of that Regulation' không có tiền ngữ trong khoản → KHÔNG mặc định về cùng văn bản
        return {"target": f"unresolved:{local}", "kind": "external", "in_scope": False}
    directive = _ACT_DIRECTIVE.match(after)
    if directive:
        return {"target": f"{directive.group(1)}:{local}", "kind": "external", "in_scope": False}
    if _ACT_TREATY.match(after):
        return {"target": f"TFEU:{local}", "kind": "external", "in_scope": False}
    return {"target": f"{doc_id}:{local}", "kind": "internal", "in_scope": True}


def _article_refs(text: str, doc_id: str, known: Mapping[str, str]) -> List[Tuple[int, Dict[str, Any]]]:
    out = []
    for m in _START.finditer(text):
        items, end = _read_chain(text, m.end())
        out += [(m.start(), _resolve(text[end:end + 160], text[:m.start()], doc_id, local, known))
                for local in items]
    return out


def _paragraph_refs(text: str, doc_id: str, article: Optional[str],
                    art_refs: List[Tuple[int, Dict[str, Any]]]) -> List[Tuple[int, Dict[str, Any]]]:
    out = []
    for m in _PARA_REF.finditer(text):
        after = text[m.end():m.end() + 40]
        if re.match(r"\s*,?\s*of\s+(?:Articles?\b|Regulation|Directive|Annex)", after):
            continue  # 'paragraph 2 of Article 10': đích đã do dẫn chiếu Article xử lý
        nums = [int(m.group(1))] + [int(n) for n in re.findall(r"\d+", m.group(2))]
        if " to " in m.group(2) and len(nums) == 2 and nums[1] > nums[0]:
            nums = list(range(nums[0], nums[1] + 1))
        if re.match(r"\s*,?\s*of\s+that\s+Article", after):
            earlier = [r for pos, r in art_refs if pos < m.start()]
            if not earlier:
                continue
            base = re.sub(r"\(\d+\)$", "", earlier[-1]["target"])
            kind, scope = earlier[-1]["kind"], earlier[-1]["in_scope"]
        elif article:
            base, kind, scope = f"{doc_id}:{article}", "internal", True
        else:
            continue
        out += [(m.start(), {"target": f"{base}({n})", "kind": kind, "in_scope": scope}) for n in nums]
    return out


def _annex_refs(text: str, doc_id: str, known: Mapping[str, str]) -> List[Tuple[int, Dict[str, Any]]]:
    out = []
    for m in _ANNEX.finditer(text):
        romans = [m.group(1)] + re.findall(r"[IVXLC]+", m.group(2))
        if " to " in m.group(2) and len(romans) == 2:
            romans = [int_to_roman(n) for n in range(roman_to_int(romans[0]), roman_to_int(romans[1]) + 1)]
        after = text[m.end():m.end() + 160]
        out += [(m.start(), _resolve(after, text[:m.start()], doc_id, f"Annex{r}", known)) for r in romans]
    # 'the Annex (to Regulation …)': phụ lục duy nhất của văn bản = Phụ lục I (R809 gọi 'Annex I'); văn bản đích
    # đọc như danh sách điều ('to Regulation (EC) No 21/2004' → ngoài bộ)
    out += [(m.start(), _resolve(text[m.end():m.end() + 160], text[:m.start()], doc_id, "AnnexI", known))
            for m in _THE_ANNEX.finditer(text)]
    return out


def find_references(text: str, doc_id: str, known: Mapping[str, str], article: Optional[str] = None
                    ) -> List[Dict[str, Any]]:
    """
    Dẫn chiếu trong khoản (thứ tự xuất hiện, không trùng): điều / khoản (internal | external), khoản cùng Điều
    ('paragraph N' — cần `article`, VD 'Art13'), Phụ lục. Khoản tự dẫn chiếu chính nó bị bỏ ở bước dựng đồ thị.
    """
    art = _article_refs(text, doc_id, known)
    found = sorted(art + _paragraph_refs(text, doc_id, article, art) + _annex_refs(text, doc_id, known),
                   key=lambda x: x[0])
    refs, seen = [], set()
    for _, ref in found:
        if ref["target"] not in seen:
            seen.add(ref["target"])
            refs.append(ref)
    return refs
