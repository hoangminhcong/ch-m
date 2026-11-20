"""
Gộp MỌI tầng của KG thành một đồ thị cho một cấu hình: Pháp lý + Tiến trình + Cầu nối + Chuẩn tắc + Ràng buộc.
Kiểm metamodel trên toàn đồ thị (thế giới đóng, mọi cạnh liên tầng phải trỏ đúng lớp). Không gọi API.

Chạy:  python scripts/build_full_kg.py --pred-dir results/cap_cerebras_v12 --config Y
Đọc:   <pred-dir>/verified_constraints_<cfg>.json (scripts/export_verified_constraints.py), đồ thị luật của bộ dữ liệu,
       data/processed/bpic2018_process_graph.json, data/processed/<bộ>_mapping_graph.json (nếu đã dựng)
Ghi:   <pred-dir>/kg_full_<cfg>.json — nạp Neo4j bằng MỘT lệnh:
       python scripts/load_kg_to_neo4j.py <pred-dir>/kg_full_<cfg>.json --replace
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.metamodel import NODE_CLASSES, summary, validate_graph  # noqa: E402

PROCESSED = PROJECT_ROOT / "data" / "processed"
LEGAL = {"cap": ("cap_legal_graph_v2.json", "cap_legal_graph.json"), "de": ("de_legal_graph.json",)}


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def merge(parts: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """Hợp các tầng; node trùng id phải giống hệt (khác → báo lỗi, không lặng lẽ ghi đè)."""
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    for layer, g in parts.items():
        for n in g["nodes"]:
            if n["id"] in nodes and nodes[n["id"]] != n:
                raise ValueError(f"Node {n['id']} khác nhau giữa các tầng (gặp lại ở {layer})")
            nodes[n["id"]] = n
        edges += g["edges"]
    return {"nodes": list(nodes.values()), "edges": edges}


def layer_counts(graph: Mapping[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for n in graph["nodes"]:
        layer = NODE_CLASSES[n["label"]].layer if n["label"] in NODE_CLASSES else "?"
        out[layer] = out.get(layer, 0) + 1
    return dict(sorted(out.items()))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--pred-dir", required=True)
    p.add_argument("--config", required=True)
    args = p.parse_args()
    pred_dir = Path(args.pred_dir)
    constraints_path = pred_dir / f"verified_constraints_{args.config}.json"
    if not constraints_path.exists():
        raise SystemExit(f"Chưa có {constraints_path.name} — chạy export_verified_constraints.py trước.")
    dataset = _load(pred_dir / f"predictions_{args.config}.json").get("dataset", "cap")
    legal_path = next((PROCESSED / n for n in LEGAL[dataset] if (PROCESSED / n).exists()), None)
    if legal_path is None:
        raise SystemExit(f"Chưa dựng đồ thị luật cho bộ '{dataset}'")
    parts = {"legal": _load(legal_path), "process": _load(PROCESSED / "bpic2018_process_graph.json")}
    bridge = PROCESSED / f"{dataset}_mapping_graph.json"
    if bridge.exists():
        parts["bridge"] = _load(bridge)
    else:
        sys.stdout.write(f"(chưa có {bridge.name} — KG không có tầng Cầu nối)\n")
    parts["normative+constraint"] = _load(constraints_path)
    graph = merge(parts)
    violations = validate_graph(graph)
    if violations:
        sys.stdout.write(f"{len(violations)} VI PHẠM metamodel — không ghi\n{summary(violations, 8)}\n")
        return 1
    out = pred_dir / f"kg_full_{args.config}.json"
    out.write_text(json.dumps({**graph, "meta": {"config": args.config, "dataset": dataset,
                                                 "layers": layer_counts(graph), "sources": {
                                                     k: str(v) for k, v in {"legal": legal_path,
                                                                            "constraints": constraints_path}.items()}}},
                              ensure_ascii=False), encoding="utf-8")
    sys.stdout.write(f"Ghi {out}: {len(graph['nodes'])} node, {len(graph['edges'])} cạnh — TUÂN THỦ metamodel; "
                     f"node theo tầng {layer_counts(graph)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
