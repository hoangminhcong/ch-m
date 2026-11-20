"""
Dẫn chiếu trong văn bản Đức (tập positive mới, docs/V2_DANG_KY_TRUOC.md mục 5.1) → id node đồ thị.

  'Artikel 11 der Delegierten Verordnung (EU) Nr. 640/2014'          → R640:Art11          (trong phạm vi)
  'Artikels 32 Absatz 2 Buchstabe b der Verordnung (EU) Nr. 1307/2013' → R1307:Art32(2)
  'Artikel 2 Absatz 10 der Verordnung (EU) Nr. 1303/2013'             → EU-1303/2013:Art2(10) (ngoài phạm vi)
  '§ 27 Absatz 2'                                                     → DE-<văn bản hiện tại>:§27(2)
  '§ 32 Absatz 2 der Direktzahlungen-Durchführungsverordnung'         → DE-DirektZahlDurchfV:§32(2)
  '§ 12 Absatz 1 des Direktzahlungen-Durchführungsgesetzes'           → DE-DirektZahlDurchfG:§12(1) (ngoài phạm vi)
Danh sách ('11 und 12', '§§ 15 und 16') và khoảng ('20 bis 22') được tách. 'Absatz 3' không kèm § (trong cùng §) bỏ qua.
"""

import re
from typing import Any, Dict, List, Optional

CAP_REGULATIONS = {"1306/2013": "R1306", "1307/2013": "R1307", "640/2014": "R640", "809/2014": "R809"}
GERMAN_LAWS = {"Direktzahlungen-Durchführungsverordnung": ("DirektZahlDurchfV", True),
               "InVeKoS-Verordnung": ("InVeKoSV", True),
               "Direktzahlungen-Durchführungsgesetzes": ("DirektZahlDurchfG", False),
               "Direktzahlungen-Durchführungsgesetz": ("DirektZahlDurchfG", False)}
_EU = re.compile(r"Artikel(?:s|n)?\s+(?P<spec>\d[0-9A-Za-zäöüÄÖÜß ,]{0,90}?)\s+(?:der|des)\s+"
                 r"(?:Delegierten\s+|Durchführungs)?[Vv]erordnung\s+\(EU\)\s+Nr\.\s*(?P<reg>\d+/\d{4})")
# Chuỗi đặc tả sau '§': số, 'Absatz', các bổ ngữ (Satz / Nummer / Buchstabe / Unterabsatz), liên từ danh sách.
# 'in Verbindung mit' nối tiếp đặc tả (kiểm metamodel 2026-11-19): '§ 6 Absatz 1 Nummer 2 in Verbindung mit Absatz 5
# Satz 1 des Marktorganisationsgesetzes' từng thành InVeKoSV §6(1) (4 khoản) vì đặc tả dừng trước 'in Verbindung mit'
_TOKEN = (r"(?:Absatz|Sätze|Satz|Nummern|Nummer|Buchstaben|Buchstabe|Unterabsätze|Unterabsatz|und|bis|oder|sowie|,"
          r"|in\s+Verbindung\s+mit|\d+[a-z]?|[a-z]\b)")
_NAT = re.compile(rf"§§?\s*(?P<spec>\d+[a-z]?(?:\s*{_TOKEN})*)"
                  r"(?:\s+(?:der|des)\s+(?P<law>Gesetz(?:es)?\s+über\s+[A-ZÄÖÜ][\w-]*"
                  r"|[A-ZÄÖÜ][\w-]*(?:[Vv]erordnung|[Gg]esetzes|[Gg]esetz)))?")
_CHAIN_GAP = re.compile(r"[\s,]*(?:(?:oder|und|sowie|in\s+Verbindung\s+mit)\s+)?(?:(?:des|der|dem|den)\s*)?")
_QUALIFIERS = {"Satz", "Sätze", "Nummer", "Nummern", "Buchstabe", "Buchstaben", "Unterabsatz", "Unterabsätze"}
_RESTART = {"Artikel", "Artikels", "Artikeln", "§", "§§"}


def _items(spec: str) -> List[tuple]:
    """Đặc tả → [(số Điều/§, Absatz|None), …]. Quy ước tiếng Đức (rà soát HIGH-2): số sau 'Absatz' (kể cả danh sách
    'Absatz 1 und 2', khoảng 'Absatz 1 bis 3') là khoản của CÙNG Điều; số sau Satz/Nummer/Buchstabe/Unterabsatz bị
    bỏ qua; 'Artikel'/'§' bắt đầu đích mới; ngoài ra số sau liên từ là Điều / § mới ('11 und 12', '20 bis 22')."""
    tokens = re.findall(r"§§?|\d+[a-z]?|[A-Za-zÄÖÜäöüß]+|,", spec)
    items: List[List[Any]] = []  # [số, [absatz…]]
    mode, pending_range = "art", False
    for tok in tokens:
        if tok in _RESTART:
            mode = "art"
        elif tok == "Absatz":
            mode = "abs"
        elif tok in _QUALIFIERS:
            mode = "qual"
        elif tok == "bis":
            pending_range = True
        elif re.fullmatch(r"\d+[a-z]?", tok):
            if mode == "qual":
                pending_range = False
                continue
            absaetze = items[-1][1] if mode == "abs" and items else None
            # khoảng có chữ cái cùng số: '§§ 24a bis 24d' → 24a, 24b, 24c, 24d (rà soát M4)
            if pending_range and absaetze is None and items and re.fullmatch(r"\d+[a-z]", tok):
                start = re.fullmatch(r"(\d+)([a-z])", items[-1][0])
                if start and start.group(1) == tok[:-1]:
                    items += [[f"{start.group(1)}{chr(c)}", []]
                              for c in range(ord(start.group(2)) + 1, ord(tok[-1]) + 1)]
                    pending_range = False
                    continue
            if pending_range and tok.isdigit() and items:
                last = absaetze[-1] if absaetze else items[-1][0]
                if last.isdigit():
                    for n in range(int(last) + 1, int(tok) + 1):
                        if absaetze is not None:
                            absaetze.append(str(n))
                        else:
                            items.append([str(n), []])
                    pending_range = False
                    continue
            pending_range = False
            if absaetze is not None:
                absaetze.append(tok)
            else:
                items.append([tok, []])
        elif tok not in ("und", "oder", "sowie", ","):
            pending_range = False
    return [(num, a) for num, abs_ in items for a in (abs_ or [None])]


def extract_de_references(text: str, law: str) -> List[Dict[str, Any]]:
    found = []
    for m in _EU.finditer(text):
        reg = m.group("reg")
        prefix, in_scope = (CAP_REGULATIONS[reg], True) if reg in CAP_REGULATIONS else (f"EU-{reg}", False)
        for art, absatz in _items(m.group("spec")):
            found.append((m.start(), {"target": f"{prefix}:Art{art}" + (f"({absatz})" if absatz else ""),
                                      "in_scope": in_scope, "kind": "eu"}))
    nat = list(_NAT.finditer(text))
    laws: List[Optional[str]] = [m.group("law") for m in nat]
    # Chuỗi '§ 27 Absatz 2, des § 28 oder des § 29 der X': § không ghi tên luật mà nối trực tiếp với § sau (chỉ cách
    # bởi ',', 'oder/und/sowie', 'des/der/dem/den') mang tên luật của § sau (duyệt từ cuối lên).
    for i in range(len(nat) - 2, -1, -1):
        gap = text[nat[i].end():nat[i + 1].start()]
        if laws[i] is None and laws[i + 1] and _CHAIN_GAP.fullmatch(gap):
            laws[i] = laws[i + 1]
    laws = [re.sub(r"^Gesetzes\b", "Gesetz", n) if n else n for n in laws]  # 'des Gesetzes über X' → 'Gesetz über X'
    for m, name in zip(nat, laws, strict=True):
        target_law, in_scope = GERMAN_LAWS.get(name, (name, False)) if name else (law, True)
        for sec, absatz in _items(m.group("spec")):
            found.append((m.start(), {"target": f"DE-{target_law}:§{sec}" + (f"({absatz})" if absatz else ""),
                                      "in_scope": in_scope, "kind": "internal" if not name else "national"}))
    seen, out = set(), []
    for _, ref in sorted(found, key=lambda x: x[0]):
        if ref["target"] not in seen:
            seen.add(ref["target"])
            out.append(ref)
    return out
