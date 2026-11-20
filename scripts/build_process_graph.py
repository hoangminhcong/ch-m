"""
TN3 – Dựng tầng Tiến trình của KG (M3, mức lược đồ) từ event log và ghi ra process_graph.json.

Chạy:  python scripts/build_process_graph.py
Sau đó nạp vào Neo4j:
       python scripts/load_kg_to_neo4j.py data/processed/process_graph.json --replace
"""

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.process_graph_builder import build_process_graph  # noqa: E402

logger = logging.getLogger("build_process_graph")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", type=Path, default=PROJECT_ROOT / "data/interim/bpic2017_events.parquet")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data/processed/process_graph.json")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    df = pd.read_parquet(args.log)
    logger.info("Log: %d event, %d hồ sơ", len(df), df["case:concept:name"].nunique())
    graph = build_process_graph(df)
    problems = graph.validate()
    if problems:
        logger.error("Đồ thị có cạnh treo: %s", problems[:5])
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(graph.to_dict(), f, ensure_ascii=False, indent=2)
    logger.info("Nodes: %s", dict(Counter(n.label for n in graph.nodes)))
    logger.info("Edges: %s", dict(Counter(e.type for e in graph.edges)))
    logger.info("Đã ghi %s", args.output)
    return 0


if __name__ == "__main__":
    # Bộ BPIC2017 đang tạm vô hiệu (src/datasets.py); mở lại: $env:NSAI_ENABLE_BPIC2017 = "1"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.datasets import require_bpic2017
    require_bpic2017(__file__)
    sys.exit(main())
