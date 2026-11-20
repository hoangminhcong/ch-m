"""
T1.2 – Dựng tầng Pháp lý của KG (M1) từ directive_chunks.json và ghi ra legal_graph.json.

Chạy:  python scripts/build_legal_graph.py
"""

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.legal_graph_builder import build_legal_graph_file  # noqa: E402

logger = logging.getLogger("build_legal_graph")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", default=PROJECT_ROOT / "data/processed/directive_chunks.json")
    parser.add_argument("--output", default=PROJECT_ROOT / "data/processed/legal_graph.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    graph = build_legal_graph_file(args.chunks, args.output)
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
