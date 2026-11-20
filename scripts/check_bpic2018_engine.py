"""
Kiểm tra engine Declare4Py trên BPIC2018 THẬT (đề xuất 1–3): nạp bảng hồ sơ riêng, điều kiện thuộc tính
hồ sơ có dấu cách, điều kiện ngày lịch — chạy cùng ràng buộc theo UTC và theo giờ Đức để thấy độ lệch.

CHỈ để kiểm tra engine. Các ràng buộc dưới đây là VÍ DỤ do người viết code chọn (mốc 15/5 theo
R809 Art13(1), cửa sổ chi trả 1/12–30/6 năm sau theo R1306 Art75(1), 'mail income' / 'begin payment' là
proxy), KHÔNG phải gold, không dùng làm kết quả bài. Gold cho CAP lấy từ phiếu gán nhãn.

Chạy:  python scripts/check_bpic2018_engine.py
Đọc:   data/interim/bpic2018_events.parquet, data/interim/bpic2018_cases.parquet (bước C1)
Ghi:   results/bpic2018_engine_check.json
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.process_graph_builder import with_composite_activity  # noqa: E402
from src.symbolic.declare4py_verifier import Declare4Py  # noqa: E402

INTERIM = PROJECT_ROOT / "data" / "interim"
OUT = PROJECT_ROOT / "results" / "bpic2018_engine_check.json"
APP = "Payment application / Application"
RULES = [
    f"Absence[{APP} / mail income] | A.date > year-05-15 | |",
    f"Absence[{APP} / begin payment] | A.date < year-12-01 | |",
    f"Absence[{APP} / begin payment] | A.date > year+1-06-30 | |",
    f"Response[{APP} / mail income, {APP} / begin payment] | A.case:young farmer == True | |",
    f"Absence[{APP} / mail income] | A.case:young farmer == True and A.date > year-05-15 | |",
]
TIMEZONES = ["UTC", "Europe/Berlin"]


def _summarise(engine: Declare4Py, rules: List[str]) -> Dict[str, Dict[str, int]]:
    with tempfile.NamedTemporaryFile("w", suffix=".decl", delete=False, encoding="utf-8") as f:
        f.write("\n".join(rules) + "\n")
        path = f.name
    try:
        engine.parse_decl_model(path)
        res = engine.conformance_checking(consider_vacuity=True)
    finally:
        os.unlink(path)
    summary = {r: {"Satisfied": 0, "Violated": 0, "Vacuously Satisfied": 0} for r in rules}
    for per_rule in res.values():
        for rule, r in per_rule.items():
            summary[rule][r.state] += 1
    return summary


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    # Tên activity ghép 'loại giấy tờ / tiến trình con / hành động' — GIỐNG Γ và KG (bước C3). Parquet gốc chỉ có
    # 'mail income' (41 tên); không ghép thì mọi ràng buộc 0 kích hoạt.
    events = with_composite_activity(pd.read_parquet(INTERIM / "bpic2018_events.parquet"))
    cases = pd.read_parquet(INTERIM / "bpic2018_cases.parquet")
    known = set(events["concept:name"].unique())
    missing = {a.strip() for r in RULES for a in r.split("[", 1)[1].split("]", 1)[0].split(",")} - known
    if missing:
        raise SystemExit(f"Activity không có trong log: {sorted(missing)}")
    report = {"cases": len(cases), "events": len(events), "note": "ràng buộc ví dụ, không phải gold", "runs": {}}
    for tz in TIMEZONES:
        start = time.perf_counter()
        engine = Declare4Py(events, cases=cases, timezone=tz)
        loaded = time.perf_counter() - start
        summary = _summarise(engine, RULES)
        checked = time.perf_counter() - start - loaded
        report["runs"][tz] = {"load_seconds": round(loaded, 1), "check_seconds": round(checked, 1), "rules": summary}
        sys.stdout.write(f"\n== {tz}: nạp {loaded:.0f}s, kiểm {checked:.0f}s ==\n")
        for rule, counts in summary.items():
            sys.stdout.write(f"  vi phạm {counts['Violated']:>6} · thoả {counts['Satisfied']:>6} · "
                             f"không kích hoạt {counts['Vacuously Satisfied']:>6}   {rule.replace(APP + ' / ', '')}\n")
        del engine
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stdout.write(f"\nĐã ghi {OUT.relative_to(PROJECT_ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
