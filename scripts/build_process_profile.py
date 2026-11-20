"""
v2: dựng hồ sơ tầng Tiến trình của BPIC2018 (src/kg/process_profile.py) → data/processed/bpic2018_process_profile.json.

Chạy:  python scripts/build_process_profile.py
Đọc:   data/interim/bpic2018_events.parquet, bpic2018_cases.parquet
Không đổi Γ v1 (gamma_bpic2018.json) và không gọi API.
"""

import json
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.process_graph_builder import with_composite_activity  # noqa: E402
from src.kg.process_profile import build_process_profile  # noqa: E402

INTERIM = PROJECT_ROOT / "data" / "interim"
OUT = PROJECT_ROOT / "data" / "processed" / "bpic2018_process_profile.json"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    start = time.perf_counter()
    events = with_composite_activity(pd.read_parquet(INTERIM / "bpic2018_events.parquet"))
    cases = pd.read_parquet(INTERIM / "bpic2018_cases.parquet")
    profile = build_process_profile(events, cases)
    OUT.write_text(json.dumps(profile, ensure_ascii=False, indent=1), encoding="utf-8")
    acts = profile["activities"]
    partial = sum(1 for a in acts.values() if a["years"] != profile["years"])
    with_sibling = sum(1 for a in acts.values() if a["same_step"])
    sys.stdout.write(f"Ghi {OUT} ({time.perf_counter() - start:.0f}s)\n"
                     f"  {len(acts)} activity, năm {profile['years']}; {partial} activity chỉ có ở một phần các năm; "
                     f"{with_sibling} activity có bước tương ứng ở loại giấy tờ khác\n"
                     f"  tài liệu: {len(profile['documents'])} loại giấy tờ\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
