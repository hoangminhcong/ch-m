"""
T2 (kiểm thử 2026-11-20) — kiểm bất biến trên mọi đầu ra của pipeline 'post' (src/evaluation/output_invariants.py).

Chạy:  python scripts/check_outputs.py --pred-dir results/cap_cerebras_v12 [--gold …]
Ghi:   <pred-dir>/output_invariants.json. Có vi phạm → exit 1 (run_pipeline post dừng).
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_cap_generation import CONFIGS, DATASETS, GAMMA  # noqa: E402
from scripts.score_cap import DEFAULT_GOLD  # noqa: E402
from src.evaluation.cap_gold import scored_clauses  # noqa: E402
from src.evaluation.output_invariants import check_outputs  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[1])
    p.add_argument("--pred-dir", required=True)
    p.add_argument("--gold", default=str(DEFAULT_GOLD))
    args = p.parse_args()
    pred_dir = Path(args.pred_dir)
    files = sorted(pred_dir.glob("predictions_*.json"))
    if not files:
        raise SystemExit(f"Không có predictions_*.json trong {pred_dir}")
    dataset = json.loads(files[0].read_text(encoding="utf-8")).get("dataset", "cap")
    candidates = {c["node_id"]: c for c in json.loads(DATASETS[dataset][0].read_text(encoding="utf-8"))}
    gold_path = Path(args.gold)
    gold = scored_clauses(json.loads(gold_path.read_text(encoding="utf-8"))) if gold_path.exists() else None
    gamma = json.loads(GAMMA.read_text(encoding="utf-8"))
    result = check_outputs(pred_dir, gold, gamma, candidates, CONFIGS)
    (pred_dir / "output_invariants.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                                     encoding="utf-8")
    bad = result["violations"]
    sys.stdout.write(f"Cấu hình: {result['configs']} — {len(bad)} vi phạm bất biến\n")
    for msg in bad[:60]:
        sys.stdout.write(f"  - {msg}\n")
    if len(bad) > 60:
        sys.stdout.write(f"  … và {len(bad) - 60} vi phạm khác (xem output_invariants.json)\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
