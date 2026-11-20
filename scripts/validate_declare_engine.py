"""
TN4 – Kiểm định engine DECLARE của NSAI so với chuẩn (pm4py + định nghĩa tường minh).

Chạy mọi template trên MỌI hồ sơ độ dài 1..4 trên bảng chữ {A, B, C} (120 hồ sơ, kiểm thử vét cạn),
in bảng số hồ sơ hai bên kết luận khác nhau, và ghi results/tn4_engine_validation.json.

Chạy:  python scripts/validate_declare_engine.py
"""

import json
import sys
from pathlib import Path
from typing import get_args

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.declare_engine_validation import (  # noqa: E402
    REFERENCE,
    compare_template,
    exhaustive_log,
    vacuity_mislabels,
)
from src.mde.constraint_ast import TemplateLiteral  # noqa: E402

ALPHABET = ["A", "B", "C"]
MAX_LEN = 4
OUTPUT = PROJECT_ROOT / "results" / "tn4_engine_validation.json"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    df = exhaustive_log(ALPHABET, MAX_LEN)
    results = []
    for template in get_args(TemplateLiteral):
        acts = ["A", "B"] if REFERENCE[template][2] == 2 else ["A"]
        row = compare_template(df, template, acts)
        row["vacuity_mislabels"] = vacuity_mislabels(df, template, acts)
        results.append(row)

    OUTPUT.write_text(json.dumps({"alphabet": ALPHABET, "max_len": MAX_LEN, "results": results},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    n = results[0]["n_traces"]
    sys.stdout.write(f"\n{n} hồ sơ vét cạn (độ dài 1..{MAX_LEN} trên {ALPHABET})\n\n")
    sys.stdout.write(f"{'Template':<24} {'Khớp':>5} {'Lệch':>5}  {'Gắn sai vacuity*':>16}  Ví dụ lệch\n")
    for r in results:
        example = r["examples"][0] if r["examples"] else None
        shown = f"{example['trace']}: engine={example['engine']}, chuẩn={example['reference']}" if example else ""
        sys.stdout.write(f"{r['template'] + '(' + ','.join(r['activities']) + ')':<24} "
                         f"{r['n_agree']:>5} {r['n_disagree']:>5}  {r['vacuity_mislabels']:>16}  {shown}\n")
    bad = [r["template"] for r in results if r["n_disagree"]]
    sys.stdout.write(f"\nTemplate lệch chuẩn: {bad or 'không có'}\n"
                     "* số hồ sơ KHÔNG kích hoạt nhưng bị gắn 'Violated' khi gọi với consider_vacuity=False\n"
                     f"Đã ghi {OUTPUT.relative_to(PROJECT_ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
