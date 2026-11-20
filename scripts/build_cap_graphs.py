"""
Dựng KG cho bộ dữ liệu thứ hai (BPIC2018 + 4 Quy định CAP): tầng Pháp lý và tầng Tiến trình.

Chạy:  python scripts/build_cap_graphs.py
Đọc:   data/processed/cap_chunks.json, data/interim/bpic2018_events.parquet, bpic2018_cases.parquet
Ghi:   data/processed/cap_legal_graph.json, data/processed/bpic2018_process_graph.json
"""

import collections
import json
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.process_graph_builder import build_process_graph, with_composite_activity  # noqa: E402
from src.kg.regulation_graph_builder import build_regulation_graph_file  # noqa: E402
from src.kg.schema import EdgeType, NodeLabel  # noqa: E402

PROCESSED = PROJECT_ROOT / "data" / "processed"
INTERIM = PROJECT_ROOT / "data" / "interim"


def _legal() -> None:
    g = build_regulation_graph_file(PROCESSED / "cap_chunks.json", PROCESSED / "cap_legal_graph.json",
                                    PROCESSED / "cap_annexes.json")
    labels = collections.Counter(n.label for n in g.nodes)
    out_scope = sum(1 for n in g.nodes if not n.props.get("in_scope", True))
    refs = g.edges_of_type(EdgeType.REFERS_TO)
    kinds = collections.Counter(
        "sang văn bản khác trong bộ" if e.props["kind"] == "external" and e.props["in_scope"]
        else "sang văn bản ngoài bộ" if e.props["kind"] == "external" else "trong cùng văn bản" for e in refs)
    sys.stdout.write(f"Tầng Pháp lý: {dict(labels)} (ngoài phạm vi: {out_scope}); REFERS_TO {len(refs)} = {dict(kinds)}\n")


def _process() -> None:
    start = time.perf_counter()
    events = pd.read_parquet(INTERIM / "bpic2018_events.parquet")
    cases = pd.read_parquet(INTERIM / "bpic2018_cases.parquet")
    g = build_process_graph(with_composite_activity(events), cases=cases)
    (PROCESSED / "bpic2018_process_graph.json").write_text(
        json.dumps(g.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    acts = g.nodes_with_label(NodeLabel.ACTIVITY)
    attrs = g.nodes_with_label(NodeLabel.ATTRIBUTE)
    levels = collections.Counter(a.props["level"] for a in attrs)
    sys.stdout.write(
        f"Tầng Tiến trình: {len(acts)} activity, {len(attrs)} thuộc tính {dict(levels)}, "
        f"DIRECTLY_FOLLOWS {len(g.edges_of_type(EdgeType.DIRECTLY_FOLLOWS))}, "
        f"HAS_ATTRIBUTE {len(g.edges_of_type(EdgeType.HAS_ATTRIBUTE))} · {time.perf_counter() - start:.0f} giây\n")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    _legal()
    if "--legal-only" not in sys.argv:  # dựng lại tầng Pháp lý mà không chạy lại tầng Tiến trình (vài phút)
        _process()
    return 0


if __name__ == "__main__":
    sys.exit(main())
