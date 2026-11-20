"""
Hiệu lực theo thời gian của 4 Quy định CAP: so nguyên văn từng khoản trên phiếu (bản gốc, data/processed/cap_chunks.json)
với bản HỢP NHẤT có hiệu lực ngày 15/5 của từng năm log (2015–2017), tải từ Cellar (Văn phòng Xuất bản EU).

Chạy:  python scripts/check_cap_versions.py [--download-dir <thư mục ngoài repo>]
Đọc:   data/processed/cap_chunks.json, data/review/cap_item_candidates.json, data/review/cap_gold_approved.json (chỉ
       để đếm theo loại khoản — không sửa gold)
Ghi:   data/review/cap_temporal_versions.json (khoản khác nội dung / chỉ khác chữ số, theo năm — cho phân tích độ
       nhạy của score_cap.py, đăng ký trước B5); tải bản hợp nhất (XHTML, ~2 MB) vào --download-dir (mặc định ~/Downloads/cap_consolidated)
Cần mạng ở lần đầu (chỉ tải văn bản luật công khai). So ở mức CHỮ (bỏ dấu cách, dấu câu, số chú thích '( n )'), tách
khoản bằng đúng bộ tách của hệ thống; khác biệt chỉ ở chữ số (đánh số chú thích / định nghĩa) được tách riêng.
"""

import argparse
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.preprocessing.parse_eu_act import split_articles  # noqa: E402

# Danh sách bản hợp nhất: truy vấn SPARQL Cellar (cdm:resource_legal_id_celex) ngày 2026-11-19. None = bản gốc còn
# hiệu lực (bản hợp nhất đầu tiên có sau ngày 15/5 năm đó). R640 2014-06-20 là ngày có hiệu lực ban đầu (= bản gốc).
IN_FORCE = {"R1306": {2015: "02013R1306-20140101", 2016: "02013R1306-20140101", 2017: "02013R1306-20140101"},
            "R1307": {2015: "02013R1307-20150101", 2016: "02013R1307-20150603", 2017: "02013R1307-20150603"},
            "R640": {2015: None, 2016: None, 2017: "02014R0640-20160822"},
            "R809": {2015: None, 2016: "02014R0809-20160101", 2017: "02014R0809-20160822"}}
CELLAR = "http://publications.europa.eu/resource/celex/{}"
OUT = PROJECT_ROOT / "data" / "review" / "cap_temporal_versions.json"


def _years(rows: list) -> list:
    return sorted({int(r.split(":", 1)[0]) for r in rows})


def _download(version: str, folder: Path) -> Path:
    path = folder / f"{version}.html"
    if not path.exists():
        req = urllib.request.Request(CELLAR.format(version), headers={
            "Accept": "application/xhtml+xml;q=0.9, text/html;q=0.8", "Accept-Language": "eng",
            "User-Agent": "research-script"})
        with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310 — URL cố định của Cellar
            path.write_bytes(resp.read())
    return path


def _text(path: Path) -> str:
    t = re.sub(r"<(script|style)[\s\S]*?</\1>", "", path.read_text(encoding="utf-8"))
    t = re.sub(r"[▼►]\s?[A-Z]\d*|◄", "", html.unescape(re.sub(r"<[^>]+>", "\n", t)))
    return "\n".join(line.strip() for line in t.splitlines() if line.strip())


def _letters(s: str) -> str:
    return re.sub(r"[\W_]", "", re.sub(r"\(\s+\d+\s+\)", "", s.replace("\xa0", " "))).lower()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--download-dir", type=Path, default=Path.home() / "Downloads" / "cap_consolidated")
    p.add_argument("--out", type=Path, default=OUT, help="file kết quả (máy đọc) cho phân tích độ nhạy")
    args = p.parse_args()
    args.download_dir.mkdir(parents=True, exist_ok=True)
    orig = {c["node_id"]: c["text"] for c in
            json.loads((PROJECT_ROOT / "data/processed/cap_chunks.json").read_text(encoding="utf-8"))}
    sheet = [r["node_id"] for r in
             json.loads((PROJECT_ROOT / "data/review/cap_item_candidates.json").read_text(encoding="utf-8"))]
    gold_path = PROJECT_ROOT / "data/review/cap_gold_approved.json"
    kind = ({k: v["kind"] for k, v in json.loads(gold_path.read_text(encoding="utf-8"))["clauses"].items()}
            if gold_path.exists() else {})
    versions = {}
    real, digits = {}, {}
    for nid in sheet:
        doc = nid.split(":")[0]
        for year, version in IN_FORCE[doc].items():
            if version is None:
                continue
            if version not in versions:
                versions[version] = {c["node_id"]: c["text"]
                                     for c in split_articles(_text(_download(version, args.download_dir)), doc)}
            new = versions[version].get(nid)
            a, b = _letters(orig[nid]), _letters(new or "")
            if new is None or a != b:
                bucket = digits if new is not None and re.sub(r"\d", "", a) == re.sub(r"\d", "", b) else real
                bucket.setdefault(nid, []).append(f"{year}:{version}" + ("" if new is not None else " (không thấy)"))
    count = lambda d: {k: sum(kind.get(n) == k for n in d) for k in ("positive", "uncertain", "trap")}  # noqa: E731
    sys.stdout.write(f"{len(sheet)} khoản phiếu. Khác nội dung so với bản có hiệu lực: {len(real)} {count(real)}; "
                     f"chỉ khác chữ số (đánh số chú thích / định nghĩa): {len(digits)}\n")
    for nid, rows in real.items():
        sys.stdout.write(f"  {nid} [{kind.get(nid, '?')}] {', '.join(rows)}\n")
    args.out.write_text(json.dumps({
        "method": "so mức chữ với bản hợp nhất có hiệu lực 15/5 mỗi năm (Cellar); xem docs/CAP_HIEU_LUC_THOI_GIAN.md",
        "in_force": IN_FORCE, "sheet_clauses": len(sheet),
        "amended": {n: {"years": _years(r), "versions": r} for n, r in sorted(real.items())},
        "digits_only": {n: {"years": _years(r), "versions": r} for n, r in sorted(digits.items())},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.stdout.write(f"Đã ghi {args.out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
