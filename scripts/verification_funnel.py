"""
Phễu kiểm chứng cho mọi cấu hình trong một thư mục kết quả (src/evaluation/verification_funnel.py). Không gọi API.

Chạy:  python scripts/verification_funnel.py --pred-dir results/cap_cerebras_v12 [--gold data/review/cap_gold_approved.json]
Đọc:   <pred-dir>/predictions_*.json (+ gold nếu có, chỉ để đếm luật sai lọt qua ở khoản bẫy)
Ghi:   <pred-dir>/verification_funnel.json và .md (bảng dán thẳng vào bài / báo cáo)
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.verification_funnel import funnel, markdown_table  # noqa: E402

ORDER = ["X", "Y", "Y-noL12", "Y-noL3", "Y-retry1", "Y-noVac", "Y-noDomain", "Y-noDuty", "R", "N", "Z",
         "Z-noLegal", "Z-noProcess", "Z-noMass", "Z-noNotes", "Z-noHint"]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--pred-dir", required=True)
    p.add_argument("--gold", default=str(PROJECT_ROOT / "data" / "review" / "cap_gold_approved.json"))
    args = p.parse_args()
    pred_dir = Path(args.pred_dir)
    gold_path = Path(args.gold)
    gold = json.loads(gold_path.read_text(encoding="utf-8"))["clauses"] if gold_path.exists() else None
    results = {}
    for cfg in ORDER:
        path = pred_dir / f"predictions_{cfg}.json"
        if path.exists():
            results[cfg] = funnel(json.loads(path.read_text(encoding="utf-8"))["predictions"], gold)
    if not results:
        raise SystemExit(f"Không có predictions_*.json trong {pred_dir}")
    errors = {c: r["outcomes"].get("ERROR", 0) for c, r in results.items() if r["outcomes"].get("ERROR")}
    table = markdown_table(results)
    (pred_dir / "verification_funnel.json").write_text(json.dumps(results, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")
    (pred_dir / "verification_funnel.md").write_text(table, encoding="utf-8")
    sys.stdout.write(table)
    if errors:
        sys.stdout.write(f"\nCHÚ Ý: còn khoản ERROR (chưa có kết quả, không được đếm vòng): {errors}\n")
    sys.stdout.write(f"\nĐã ghi {pred_dir / 'verification_funnel.md'} và .json\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
