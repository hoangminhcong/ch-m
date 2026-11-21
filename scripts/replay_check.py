"""
T3 (kiểm thử 2026-11-20) — phát lại cache LLM của một thư mục kết quả bằng code hiện tại (src/evaluation/replay.py).

Không gọi API: sao file cache sang thư mục tạm, chạy run_cap_generation.py --cache-only --force, so từng khoản
(outcome, AST, trạng thái từng vòng) với file gốc. Thư mục kết quả gốc KHÔNG bị ghi.
Cấu hình có kiểm rỗng (B) nạp log ~40 s mỗi cấu hình.

Chạy:  python scripts/replay_check.py --pred-dir results/cap_cerebras_v12 [--configs Y X] [--report out.json]
Exit 1 nếu có khoản khác — kèm danh sách để biết đổi là CỐ Ý (một lần sửa lỗi) hay không.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.replay import compare_predictions, run_command  # noqa: E402

GENERATOR = PROJECT_ROOT / "scripts" / "run_cap_generation.py"


def replay_config(pred_dir: Path, cfg: str) -> dict:
    doc = json.loads((pred_dir / f"predictions_{cfg}.json").read_text(encoding="utf-8"))
    caches = [pred_dir / f"llm_cache_{cfg}.json", pred_dir / f"llm_cache_{cfg}_judge.json"]
    if not caches[0].exists():
        return {"config": cfg, "skipped": f"không có {caches[0].name}"}
    with tempfile.TemporaryDirectory() as tmp:
        for c in caches:
            if c.exists():
                shutil.copy2(c, Path(tmp) / c.name)
        cmd = run_command(sys.executable, str(GENERATOR), cfg, doc, tmp, only=sorted(doc["predictions"]))
        proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
        out = Path(tmp) / f"predictions_{cfg}.json"
        if proc.returncode != 0 or not out.exists():
            return {"config": cfg, "error": (proc.stderr or proc.stdout)[-800:]}
        replayed = json.loads(out.read_text(encoding="utf-8"))["predictions"]
    return {"config": cfg, **compare_predictions(doc["predictions"], replayed)}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[1])
    p.add_argument("--pred-dir", required=True)
    p.add_argument("--configs", nargs="*", default=None, help="mặc định: mọi cấu hình có file dự đoán")
    p.add_argument("--report", default=None, help="ghi kết quả JSON ra file này (mặc định không ghi)")
    args = p.parse_args()
    pred_dir = Path(args.pred_dir)
    configs = args.configs or sorted(f.stem.split("_", 1)[1] for f in pred_dir.glob("predictions_*.json"))
    results, failed = [], False
    for cfg in configs:
        sys.stdout.write(f"Phát lại {cfg}...\n")
        sys.stdout.flush()
        r = replay_config(pred_dir, cfg)
        results.append(r)
        if "skipped" in r:
            sys.stdout.write(f"  bỏ qua: {r['skipped']}\n")
        elif "error" in r:
            failed = True
            sys.stdout.write(f"  LỖI khi phát lại: {r['error']}\n")
        else:
            failed |= bool(r["differences"])
            sys.stdout.write(f"  {r['identical']}/{r['compared']} khoản giống hệt; {len(r['differences'])} khác; "
                             f"{len(r['skipped_error'])} khoản ERROR gốc không so\n")
            for d in r["differences"][:10]:
                sys.stdout.write(f"    {d['clause']}: {d['kind']} {d.get('original', '')} → {d.get('replayed', '')}\n")
    if args.report:
        Path(args.report).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
