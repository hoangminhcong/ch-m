"""
Chuyển BPI Challenge 2018 (XES 1,9 GB) sang hai bảng parquet bằng cách đọc tuần tự.

Chạy:  python scripts/convert_bpic2018.py --xes "<đường dẫn tới BPI Challenge 2018.xes>"
Ghi:   data/interim/bpic2018_events.parquet, data/interim/bpic2018_cases.parquet
"""

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.preprocessing.xes_stream import convert_xes  # noqa: E402

DEFAULT_XES = Path.home() / "Downloads" / "BPI Challenge 2018_1_all" / "BPI Challenge 2018.xes" / "BPI Challenge 2018.xes"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xes", type=Path, default=DEFAULT_XES)
    parser.add_argument("--out-dir", type=Path, default=PROJECT_ROOT / "data" / "interim")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    events_out = args.out_dir / "bpic2018_events.parquet"
    cases_out = args.out_dir / "bpic2018_cases.parquet"

    sys.stdout.reconfigure(encoding="utf-8")
    start = time.perf_counter()
    stats = convert_xes(args.xes, events_out, cases_out)
    sys.stdout.write(
        f"Hồ sơ: {stats['cases']:,} · Event: {stats['events']:,} · {time.perf_counter() - start:.0f} giây\n"
        f"Đã ghi {events_out} và {cases_out}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
