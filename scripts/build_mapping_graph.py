"""
Dựng tầng Cầu nối của KG từ ontology loại giấy tờ ĐÃ DUYỆT (src/kg/mapping_graph_builder.py). Không gọi API.

Chạy:  python scripts/build_mapping_graph.py [--check]   (--check: chỉ kiểm file trên đĩa khớp dữ liệu hiện tại)
Đọc:   data/review/bpic2018_ontology.json (status=approved), data/processed/{cap,de}_legal_graph.json,
       data/processed/bpic2018_process_graph.json
Ghi:   data/processed/cap_mapping_graph.json, data/processed/de_mapping_graph.json
Mỗi đồ thị cầu nối được kiểm metamodel trên HỢP (đồ thị luật + tiến trình + cầu nối); vi phạm → không ghi, exit 1.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.mapping_graph_builder import build_mapping_graph  # noqa: E402
from src.kg.metamodel import summary, validate_graph  # noqa: E402

PROCESSED = PROJECT_ROOT / "data" / "processed"
ONTOLOGY = PROJECT_ROOT / "data" / "review" / "bpic2018_ontology.json"
PROCESS_GRAPH = PROCESSED / "bpic2018_process_graph.json"
BRIDGES = {"cap": (PROCESSED / "cap_legal_graph.json", PROCESSED / "cap_mapping_graph.json"),
           "de": (PROCESSED / "de_legal_graph.json", PROCESSED / "de_mapping_graph.json")}


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def union(*graphs: Mapping[str, Any]) -> Dict[str, Any]:
    return {"nodes": [n for g in graphs for n in g["nodes"]], "edges": [e for g in graphs for e in g["edges"]]}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--check", action="store_true", help="chỉ kiểm file cầu nối trên đĩa khớp dữ liệu, không ghi")
    args = p.parse_args()
    ontology, process = _load(ONTOLOGY), _load(PROCESS_GRAPH)
    if ontology.get("status") != "approved":
        sys.stdout.write("Ontology CHƯA DUYỆT — không dựng tầng Cầu nối (docs/ONTOLOGY_BPIC2018_DUYET.md)\n")
        return 1
    ok = True
    for name, (legal_path, out_path) in BRIDGES.items():
        if not legal_path.exists():
            sys.stdout.write(f"{name}: bỏ qua, chưa có {legal_path.name}\n")
            continue
        legal = _load(legal_path)
        bridge = build_mapping_graph(ontology, legal, process)
        violations = validate_graph(union(legal, process, bridge))
        m = bridge["meta"]
        if violations:
            sys.stdout.write(f"{name}: {len(violations)} VI PHẠM metamodel — không ghi\n{summary(violations, 5)}\n")
            ok = False
            continue
        if args.check:
            same = out_path.exists() and _load(out_path) == bridge
            sys.stdout.write(f"{name}: {out_path.name} {'KHỚP' if same else 'LỆCH / chưa dựng'}\n")
            ok &= same
            continue
        out_path.write_text(json.dumps(bridge, ensure_ascii=False, indent=1), encoding="utf-8")
        sys.stdout.write(
            f"{name}: ghi {out_path.relative_to(PROJECT_ROOT)} — {len(bridge['nodes'])} DocumentType, "
            f"{len(bridge['edges'])} cạnh; khoản có MAPS_TO {m['provisions_mapped']}/{m['provisions_with_text']}; "
            f"theo loại {m['maps_to_per_doctype']}; activity không thuộc loại nào: {m['unmapped_activities'] or '—'}\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
