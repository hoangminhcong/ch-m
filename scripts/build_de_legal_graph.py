"""
Tập Đức: đồ thị Pháp lý (src/kg/de_legal_graph.py) → data/processed/de_legal_graph.json.

Chạy:  python scripts/build_de_legal_graph.py
Đọc:   data/processed/de_chunks.json (scripts/fetch_de_laws.py), cap_legal_graph.json (giữ nguyên). Không gọi API.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.de_legal_graph import build_de_legal_graph  # noqa: E402

PROCESSED = PROJECT_ROOT / "data" / "processed"
OUT = PROCESSED / "de_legal_graph.json"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    de = json.loads((PROCESSED / "de_chunks.json").read_text(encoding="utf-8"))
    cap = json.loads((PROCESSED / "cap_legal_graph.json").read_text(encoding="utf-8"))
    g = build_de_legal_graph(de, cap)
    OUT.write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    ids = {n["id"] for n in g["nodes"]}
    de_edges = [e for e in g["edges"] if e["type"] == "REFERS_TO" and e["source"].startswith("DE-")]
    usable = sum(1 for e in de_edges if e["props"]["in_scope"] and e["target"] in ids)
    to_eu = sum(1 for e in de_edges if e["props"]["in_scope"] and e["target"] in ids and e["target"].startswith("R"))
    sys.stdout.write(f"Ghi {OUT}: {len(de)} khoản Đức, {len(de_edges)} cạnh REFERS_TO từ khoản Đức "
                     f"({usable} dùng được, trong đó {to_eu} tới Quy định EU)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
