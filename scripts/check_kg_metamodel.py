"""
Kiểm mọi đồ thị KG theo metamodel (src/kg/metamodel.py) và báo chỗ lệch (drift). Không gọi API, không ghi file.

Chạy:  python scripts/check_kg_metamodel.py [đường_dẫn_đồ_thị.json ...]
Mặc định: data/processed/{cap_legal_graph, cap_legal_graph_v2, de_legal_graph, bpic2018_process_graph}.json
Thoát mã 1 nếu có vi phạm (dùng được trong CI / sau mỗi lần dựng đồ thị).
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.metamodel import drift, summary, validate_graph  # noqa: E402

PROCESS_GRAPH = "bpic2018_process_graph.json"
DEFAULT_GRAPHS = ("cap_legal_graph.json", "cap_legal_graph_v2.json", "de_legal_graph.json", PROCESS_GRAPH)
BRIDGES = (("cap_legal_graph.json", "cap_mapping_graph.json"), ("de_legal_graph.json", "de_mapping_graph.json"))


def union(*graphs: dict) -> dict:
    return {"nodes": [n for g in graphs for n in g["nodes"]], "edges": [e for g in graphs for e in g["edges"]]}


def main(argv: list) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    paths = [Path(a) for a in argv] or [PROJECT_ROOT / "data" / "processed" / n for n in DEFAULT_GRAPHS]
    graphs, total = {}, 0
    for path in paths:
        if not path.exists():
            sys.stdout.write(f"BỎ QUA (chưa dựng): {path.name}\n")
            continue
        graphs[path.name] = json.loads(path.read_text(encoding="utf-8"))
        violations = validate_graph(graphs[path.name])
        total += len(violations)
        g = graphs[path.name]
        sys.stdout.write(f"{path.name}: {len(g['nodes'])} node, {len(g['edges'])} cạnh — "
                         f"{'TUÂN THỦ' if not violations else f'{len(violations)} VI PHẠM'}\n")
        if violations:
            sys.stdout.write(summary(violations, 5) + "\n")
    if not argv:  # tầng Cầu nối: cạnh trỏ vào node của đồ thị luật + tiến trình → kiểm trên HỢP ba đồ thị
        processed = PROJECT_ROOT / "data" / "processed"
        for legal_name, bridge_name in BRIDGES:
            bridge_path = processed / bridge_name
            if not bridge_path.exists() or legal_name not in graphs or PROCESS_GRAPH not in graphs:
                sys.stdout.write(f"BỎ QUA (chưa dựng): {bridge_name}\n")
                continue
            bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
            merged = union(graphs[legal_name], graphs[PROCESS_GRAPH], bridge)
            violations = validate_graph(merged)
            total += len(violations)
            graphs[bridge_name] = merged  # drift cần lớp của node nguồn (nằm ở đồ thị luật / tiến trình)
            sys.stdout.write(f"{bridge_name} (trên hợp với {legal_name} + {PROCESS_GRAPH}): {len(bridge['nodes'])} "
                             f"node, {len(bridge['edges'])} cạnh — "
                             f"{'TUÂN THỦ' if not violations else f'{len(violations)} VI PHẠM'}\n")
            if violations:
                sys.stdout.write(summary(violations, 5) + "\n")
    d = drift(graphs)
    sys.stdout.write(f"Lệch: bộ ba không khai báo {d['undeclared_triples'] or 'không có'}; "
                     f"quan hệ khai báo chưa dùng {d['unused_relations'] or 'không có'}; "
                     f"lớp chưa dùng {d['unused_classes'] or 'không có'}\n")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
