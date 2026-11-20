"""
v2: tầng Pháp lý giàu hơn (src/kg/legal_enrichment.py) → data/processed/cap_legal_graph_v2.json.

  = đồ thị v1 (cap_legal_graph.json, KHÔNG đổi) + DefinedTerm + DEFINES / USES_TERM + ghi chú phạm vi quốc gia.
Chạy:  python scripts/build_cap_legal_v2.py
Đọc:   data/processed/cap_chunks.json, cap_legal_graph.json. Không gọi API.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.legal_enrichment import build_legal_enrichment, scope_note  # noqa: E402

PROCESSED = PROJECT_ROOT / "data" / "processed"
OUT = PROCESSED / "cap_legal_graph_v2.json"


def build(chunks: list, graph_v1: dict) -> dict:
    enrichment = build_legal_enrichment(chunks)
    notes = {c["node_id"]: note for c in chunks if (note := scope_note(c["text"]))}
    return {"nodes": graph_v1["nodes"] + enrichment["graph"]["nodes"],
            "edges": graph_v1["edges"] + enrichment["graph"]["edges"],
            "definitions": enrichment["definitions"], "scope_notes": notes}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    chunks = json.loads((PROCESSED / "cap_chunks.json").read_text(encoding="utf-8"))
    v1 = json.loads((PROCESSED / "cap_legal_graph.json").read_text(encoding="utf-8"))
    v2 = build(chunks, v1)
    OUT.write_text(json.dumps(v2, ensure_ascii=False, indent=1), encoding="utf-8")
    terms = sum(1 for n in v2["nodes"] if n["label"] == "DefinedTerm")
    uses = sum(1 for e in v2["edges"] if e["type"] == "USES_TERM")
    sys.stdout.write(f"Ghi {OUT}\n  {terms} DefinedTerm, {uses} cạnh USES_TERM ở {len(v2['definitions'])} khoản; "
                     f"{len(v2['scope_notes'])} khoản có ghi chú phạm vi quốc gia\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
