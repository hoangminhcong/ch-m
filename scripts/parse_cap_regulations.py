"""
Tách 4 Quy định CAP (đi kèm BPIC2018) thành từng khoản + dẫn chiếu.

Chạy:  python scripts/parse_cap_regulations.py [--pdf-dir "<thư mục chứa CELEX_*.pdf>"]
Ghi:   data/processed/cap_chunks.json, data/processed/cap_annexes.json (Phụ lục — kiểm toán đợt 2)
"""

import argparse
import collections
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.preprocessing.parse_eu_act import parse_regulation_annexes, parse_regulation_pdf  # noqa: E402

PDF_FILES = {
    "R1306": "CELEX_32013R1306_EN_TXT.pdf",
    "R1307": "CELEX_32013R1307_EN_TXT.pdf",
    "R640": "CELEX_32014R0640_EN_TXT.pdf",
    "R809": "CELEX_32014R0809_EN_TXT.pdf",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-dir", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "data" / "processed" / "cap_chunks.json")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    chunks, annexes = [], []
    for doc_id, name in PDF_FILES.items():
        path = args.pdf_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Thiếu {path}")
        doc_chunks = parse_regulation_pdf(path, doc_id)
        chunks.extend(doc_chunks)
        annexes.extend(parse_regulation_annexes(path, doc_id))
        kinds = collections.Counter(
            "sang văn bản khác (trong 4 văn bản)" if r["kind"] == "external" and r["in_scope"]
            else "sang văn bản ngoài bộ" if r["kind"] == "external" else "trong cùng văn bản"
            for c in doc_chunks for r in c["refs"]
        )
        articles = {c["node_id"].split("(")[0] for c in doc_chunks}
        sys.stdout.write(f"{doc_id}: {len(articles)} điều, {len(doc_chunks)} khoản, dẫn chiếu {dict(kinds)}\n")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stdout.write(f"Tổng {len(chunks)} khoản → {args.out}\n")
    annex_out = args.out.with_name("cap_annexes.json")
    annex_out.write_text(json.dumps(annexes, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stdout.write(f"{len(annexes)} Phụ lục ({', '.join(a['node_id'] for a in annexes)}) → {annex_out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
