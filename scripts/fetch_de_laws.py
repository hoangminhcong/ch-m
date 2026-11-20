"""
Tập positive mới (docs/V2_DANG_KY_TRUOC.md mục 5.1): tải và dựng các khoản InVeKoSV + DirektZahlDurchfV theo từng
năm nộp đơn của log (văn bản có hiệu lực ngày 15/5 của năm đó — hạn nộp Sammelantrag).

Chạy:  python scripts/fetch_de_laws.py            (tải những trang còn thiếu trong cache, rồi dựng)
       python scripts/fetch_de_laws.py --offline  (chỉ dựng từ cache)
Nguồn: buzer.de (trang so sánh từng lần sửa đổi; robots.txt cho phép /gesetz/), gesetze-im-internet.de (XML bản hiện
hành — chỉ dùng cho § chưa từng sửa). Cache: data/raw/de_laws/. Ghi: data/processed/de_chunks.json.
Mỗi khoản: văn bản giống nhau qua các năm → một mục kèm danh sách năm; khác nhau → mỗi văn bản một mục.
Không gọi API LLM.
"""

import argparse
import io
import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.preprocessing.de_law_versions import (  # noqa: E402
    parse_version_page,
    section_text_or_none,
    split_absaetze,
    text_at,
)
from src.preprocessing.de_references import extract_de_references  # noqa: E402

CACHE = PROJECT_ROOT / "data" / "raw" / "de_laws"
OUT = PROJECT_ROOT / "data" / "processed" / "de_chunks.json"
YEARS = (2015, 2016, 2017)
REFERENCE_DAY = (5, 15)  # 15/5 của năm nộp đơn
LAWS = {
    "InVeKoSV": {"buzer": 11495, "gii": "invekosv_2015"},
    "DirektZahlDurchfV": {"buzer": 11333, "gii": "direktzahldurchfv"},
}
USER_AGENT = "Mozilla/5.0 (research; legal-text corpus for compliance checking)"
PAUSE_S = 1.5
_REPEALED = re.compile(r"(?:\(\w+\)\s*)?\((?:aufgehoben|weggefallen)\)\s*")
# Trang so sánh: 'v…-JJJJ-MM-TT' (lần sửa nhiều §) và 'al…-n' (lần sửa một §, liên kết thẳng từ bảng lịch sử).
_VLINK = re.compile(r'href="(?:https://www\.buzer\.de)?(/gesetz/(\d+)/(v\d+-\d{4}-\d{2}-\d{2}|al\d+-\d+)\.htm)"')


def _get(url: str, path: Path, offline: bool) -> bytes:
    if path.exists():
        return path.read_bytes()
    if offline:
        raise SystemExit(f"Thiếu trong cache (chạy không --offline): {path}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (URL cố định của nguồn công khai)
        data = resp.read()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    time.sleep(PAUSE_S)
    return data


def _current_sections(law: str, gii: str, offline: bool) -> Dict[str, str]:
    raw = _get(f"https://www.gesetze-im-internet.de/{gii}/xml.zip", CACHE / law / "current_xml.zip", offline)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        root = ET.fromstring(z.read(next(n for n in z.namelist() if n.endswith(".xml"))))
    out = {}
    for norm in root.findall("norm"):
        enbez = (norm.findtext("metadaten/enbez") or "").strip()
        m = re.fullmatch(r"§\s*([0-9]+[a-z]?)", enbez)
        if not m:
            continue
        # ' '.join: mục đánh số (<DT>1.</DT><DD>der …</DD>) không bị dính chữ ('1.der')
        paras = [re.sub(r"\s+", " ", " ".join(p.itertext())).strip() for p in norm.iter("P")]
        out[m.group(1)] = f"§ {m.group(1)} {(norm.findtext('metadaten/titel') or '').strip()}\n" + "\n".join(paras)
    return out


def _versions(law: str, buzer: int, offline: bool) -> List[Dict[str, Any]]:
    index = _get(f"https://www.buzer.de/gesetz/{buzer}/l.htm", CACHE / law / "l.htm", offline).decode("latin-1")
    links = sorted({m.group(1): m.group(3) for m in _VLINK.finditer(index) if m.group(2) == str(buzer)}.items())
    return [parse_version_page(_get(f"https://www.buzer.de{href}", CACHE / law / f"{name}.htm", offline)
                               .decode("latin-1")) for href, name in links]


def build(offline: bool) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    for law, src in LAWS.items():
        versions = _versions(law, src["buzer"], offline)
        current = _current_sections(law, src["gii"], offline)
        labels = sorted({*current, *(s for v in versions for s in v["sections"])},
                        key=lambda s: (int(re.match(r"\d+", s).group()), s))
        for sec in labels:
            by_text: Dict[str, Dict[str, Any]] = {}
            for year in YEARS:
                text = section_text_or_none(sec, text_at(sec, date(year, *REFERENCE_DAY), versions, current))
                first_line = text.split("\n", 1)[0] if text else ""
                if not text or "(weggefallen)" in first_line or "(aufgehoben)" in first_line:
                    continue
                for part in split_absaetze(text):
                    if not part["text"] or _REPEALED.fullmatch(part["text"]):
                        continue  # § chưa tồn tại năm đó (bản cũ chỉ còn nhãn '§'), hoặc khoản đã bãi bỏ
                    key = f"{part['absatz']}|{part['text']}"
                    entry = by_text.setdefault(key, {**part, "years": []})
                    entry["years"].append(year)
            for entry in by_text.values():
                absatz = f"({entry['absatz']})" if entry["absatz"] else ""
                yrs = entry["years"]
                suffix = "" if yrs == list(YEARS) else "@" + "-".join(str(y) for y in yrs)
                chunks.append({"node_id": f"DE-{law}:§{sec}{absatz}{suffix}", "doc_id": f"DE-{law}", "law": law,
                               "section": sec, "absatz": entry["absatz"], "article_title": entry["title"],
                               "years": yrs, "text": entry["text"], "language": "de",
                               "refs": extract_de_references(entry["text"], law)})
        sys.stdout.write(f"{law}: {len(versions)} lần sửa đổi trên buzer, {len(current)} § hiện hành\n")
    return chunks


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--offline", action="store_true")
    chunks = build(p.parse_args().offline)
    OUT.write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")
    split = sum(1 for c in chunks if "@" in c["node_id"])
    sys.stdout.write(f"Ghi {OUT}: {len(chunks)} khoản ({split} khoản có văn bản khác nhau giữa các năm)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
