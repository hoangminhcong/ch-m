"""
T1.4 – Nạp một tầng KG (file JSON do các bước trước sinh ra) vào Neo4j.

Chạy:  python scripts/load_kg_to_neo4j.py data/processed/legal_graph.json
       python scripts/load_kg_to_neo4j.py data/processed/legal_graph.json --replace
(--replace: xoá các node cùng nhãn đã có trước khi nạp, để nạp lại sạch)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.neo4j_store import Neo4jKGStore  # noqa: E402
from src.kg.schema import KnowledgeGraph  # noqa: E402

logger = logging.getLogger("load_kg_to_neo4j")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("graph_json", type=Path, nargs="+",
                        help="một hoặc nhiều file; nhiều file được gộp rồi mới kiểm cạnh treo — tầng Cầu nối cần nạp "
                             "CÙNG đồ thị luật + tiến trình, VD cap_legal_graph.json bpic2018_process_graph.json "
                             "cap_mapping_graph.json")
    parser.add_argument("--replace", action="store_true", help="xoá node cùng nhãn trước khi nạp")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    graph = KnowledgeGraph()
    for path in args.graph_json:
        with open(path, encoding="utf-8") as f:
            part = KnowledgeGraph.from_dict(json.load(f))
        graph = graph.merge(part.nodes, part.edges)
    problems = graph.validate()
    if problems:
        logger.error("Đồ thị có cạnh treo, dừng nạp: %s", problems[:5])
        return 1

    store = Neo4jKGStore.from_env()
    try:
        store.ensure_constraints()
        if args.replace:
            labels = sorted({n.label for n in graph.nodes})
            store.clear_labels(labels)
            logger.info("Đã xoá node cũ thuộc nhãn: %s", labels)
        counts = store.write_graph(graph)
    finally:
        store.close()
    for name, count in counts.items():
        logger.info("  %-15s %6d", name, count)
    logger.info("Xong. Mở http://localhost:7474 để xem đồ thị.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
