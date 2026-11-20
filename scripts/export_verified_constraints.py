"""
v2: xuất luật đã kiểm chứng của một cấu hình vào KG (src/kg/constraint_export.py).

Chạy:  python scripts/export_verified_constraints.py --pred-dir results/cap_cerebras --config Z
Đọc:   <pred-dir>/predictions_<config>.json      Ghi: <pred-dir>/verified_constraints_<config>.json
Không gọi API. Nạp vào Neo4j cùng các tầng khác nếu cần trình bày (id node khớp tầng Pháp lý và Tiến trình).
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.constraint_export import export_constraints  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--pred-dir", required=True)
    p.add_argument("--config", required=True)
    args = p.parse_args()
    src = Path(args.pred_dir) / f"predictions_{args.config}.json"
    if not src.exists():
        raise SystemExit(f"Không có {src}")
    graph = export_constraints(json.loads(src.read_text(encoding="utf-8")))
    out = Path(args.pred_dir) / f"verified_constraints_{args.config}.json"
    out.write_text(json.dumps(graph, ensure_ascii=False, indent=1), encoding="utf-8")
    on = sum(1 for e in graph["edges"] if e["type"] == "ON")
    kinds: dict = {}
    for f in graph["set_checks"]:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
    count = lambda label: sum(1 for n in graph["nodes"] if n["label"] == label)  # noqa: E731
    sys.stdout.write(f"Ghi {out}: {count('VerifiedConstraint')} VerifiedConstraint, {count('Norm')} Norm, {on} cạnh ON; "
                     f"kiểm tập ràng buộc: {kinds or 'không phát hiện'}\n")
    for f in graph["set_checks"]:
        if f["kind"] != "DUPLICATE":
            sys.stdout.write(f"  {f['kind']}: {f['a']} ↔ {f['b']}\n    {f['decl_a']}\n    {f['decl_b']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
