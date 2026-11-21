"""
Chạy pipeline theo thứ tự cố định, có cổng kiểm — mọi bước KHÔNG gọi API (sinh luật gọi API: bạn tự chạy).

  pre   trước khi sinh luật:  KG tuân thủ metamodel (M2) → Γ trên đĩa đúng là phép chiếu của KG → in dấu dữ liệu
        đầu vào của các cấu hình (để đối chiếu với file kết quả)
        → T1: dữ liệu phái sinh (đồ thị luật, đồ thị / hồ sơ Tiến trình) đúng là kết quả dựng lại từ nguồn
  post  sau khi sinh luật:    chấm (cổng: thiếu khoản / ERROR / lẫn lần chạy / lẫn PHIÊN BẢN DỮ LIỆU) → phễu kiểm
        chứng → xuất ràng buộc + kiểm tập ràng buộc → proof trace → [đối chiếu từng hồ sơ] → báo cáo HTML
        → T2: bất biến trên mọi đầu ra (chấm lại, đếm lại, KG không cạnh treo, trace = AST, …)
  replay  T3: phát lại cache LLM bằng code hiện tại, so từng khoản với file gốc (sau mỗi lần sửa code; nạp log)

Bước nào lỗi (exit ≠ 0) thì DỪNG — không chạy bước sau trên dữ liệu chưa qua cổng.

Chạy:  python scripts/run_pipeline.py pre
       python scripts/run_cap_generation.py --config Y ...      (từng cấu hình — gọi API, bạn tự chạy)
       python scripts/run_pipeline.py post --pred-dir results/cap_cerebras_v12 [--configs Y R] [--conformance]
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_cap_generation import CONFIGS, input_paths  # noqa: E402
from src.evaluation.run_inputs import fingerprint, inputs_id  # noqa: E402

SCRIPTS = PROJECT_ROOT / "scripts"
DEFAULT_TRACE_CONFIGS = ("Y",)
SCORE_FLAGS = ("allow_mixed", "allow_errors", "allow_missing", "allow_candidate")


def _run(step: str, args: Sequence[str]) -> None:
    sys.stdout.write(f"\n=== {step}\n$ python {' '.join(args)}\n")
    sys.stdout.flush()
    start = time.perf_counter()
    code = subprocess.call([sys.executable, *args], cwd=PROJECT_ROOT)
    if code != 0:
        raise SystemExit(f"\nDỪNG ở bước '{step}' (exit {code}). Sửa lỗi trên rồi chạy lại; các bước sau chưa chạy.")
    sys.stdout.write(f"--- xong '{step}' ({time.perf_counter() - start:.0f}s)\n")


def pre(dataset: str) -> None:
    _run("KG tuân thủ metamodel", [str(SCRIPTS / "check_kg_metamodel.py")])
    _run("Γ khớp phép chiếu của KG", [str(SCRIPTS / "build_gamma_from_kg.py"), "--check"])
    _run("Tầng Cầu nối (MAPS_TO) khớp ontology đã duyệt + đồ thị",
         [str(SCRIPTS / "build_mapping_graph.py"), "--check"])
    _run("T1 — dữ liệu phái sinh khớp nguồn (nạp log ~15 s)", [str(SCRIPTS / "check_derived_data.py")])
    sys.stdout.write(f"\n=== Dấu dữ liệu đầu vào (bộ '{dataset}') — file kết quả mới sẽ ghi đúng mã này\n")
    for cfg in CONFIGS:
        fp = fingerprint(input_paths(cfg, dataset))
        missing = [k for k, v in fp.items() if v == "missing"]
        sys.stdout.write(f"  {cfg:<12} inputs_id={inputs_id(fp)}  {', '.join(fp)}"
                         + (f"  !!! THIẾU: {missing}" if missing else "") + "\n")


def _existing(pred_dir: Path, configs: Sequence[str]) -> List[str]:
    return [c for c in configs if (pred_dir / f"predictions_{c}.json").exists()]


def post(args: argparse.Namespace) -> None:
    pred = Path(args.pred_dir)
    if not pred.is_absolute():
        pred = PROJECT_ROOT / pred
    if not any(pred.glob("predictions_*.json")):
        raise SystemExit(f"Không có predictions_*.json trong {pred}")
    gold = ["--gold", args.gold] if args.gold else []
    flags = [f"--{f.replace('_', '-')}" for f in SCORE_FLAGS if getattr(args, f)]
    _run("Chấm + cổng kiểm dự đoán", [str(SCRIPTS / "score_cap.py"), "--pred-dir", str(pred), *gold, *flags])
    _run("Phễu kiểm chứng", [str(SCRIPTS / "verification_funnel.py"), "--pred-dir", str(pred), *gold])
    traced = _existing(pred, args.configs)
    skipped = sorted(set(args.configs) - set(traced))
    if skipped:
        sys.stdout.write(f"\n(bỏ qua xuất ràng buộc / proof trace cho cấu hình chưa có kết quả: {skipped})\n")
    for cfg in traced:
        _run(f"Xuất ràng buộc + kiểm tập — {cfg}",
             [str(SCRIPTS / "export_verified_constraints.py"), "--pred-dir", str(pred), "--config", cfg])
        _run(f"KG đầy đủ 5 tầng + kiểm metamodel — {cfg}",
             [str(SCRIPTS / "build_full_kg.py"), "--pred-dir", str(pred), "--config", cfg])
        _run(f"Proof trace — {cfg}", [str(SCRIPTS / "build_proof_traces.py"), "--pred-dir", str(pred), "--config", cfg])
    if traced:
        _run("Nhãn REVIEW + bảng giữ lại — rủi ro (B7, nạp log)",
             [str(SCRIPTS / "review_flags.py"), "--pred-dir", str(pred), *gold, "--configs", *traced])
    if args.conformance:
        _run("Đối chiếu từng hồ sơ (TN7, nạp log)",
             [str(SCRIPTS / "run_cap_conformance.py"), "--pred-dir", str(pred), *gold, "--configs", *traced])
    _run("Báo cáo HTML", [str(SCRIPTS / "build_cap_report.py"), "--dir", str(pred)])
    _run("T2 — bất biến trên mọi đầu ra", [str(SCRIPTS / "check_outputs.py"), "--pred-dir", str(pred), *gold])
    sys.stdout.write(f"\nPipeline 'post' xong cho {pred}.\n")


def replay(args: argparse.Namespace) -> None:
    pred = Path(args.pred_dir)
    pred = pred if pred.is_absolute() else PROJECT_ROOT / pred
    configs = ["--configs", *args.configs] if args.configs else []
    _run("T3 — phát lại cache LLM bằng code hiện tại", [str(SCRIPTS / "replay_check.py"), "--pred-dir", str(pred),
                                                       *configs, "--report", str(pred / "replay_check.json")])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    sub = p.add_subparsers(dest="stage", required=True)
    p_pre = sub.add_parser("pre", help="cổng kiểm trước khi sinh luật")
    p_pre.add_argument("--dataset", choices=("cap", "de"), default="cap")
    p_post = sub.add_parser("post", help="chấm + phân tích sau khi sinh luật")
    p_post.add_argument("--pred-dir", required=True)
    p_post.add_argument("--gold", default=None, help="mặc định: gold của score_cap.py")
    p_post.add_argument("--configs", nargs="*", default=list(DEFAULT_TRACE_CONFIGS),
                        help="cấu hình cần xuất ràng buộc / proof trace / đối chiếu (mặc định: Y)")
    p_post.add_argument("--conformance", action="store_true", help="chạy cả TN7 (đối chiếu từng hồ sơ, nạp log)")
    for f in SCORE_FLAGS:
        p_post.add_argument(f"--{f.replace('_', '-')}", action="store_true", help="chuyển cho score_cap.py")
    p_rep = sub.add_parser("replay", help="T3: phát lại cache bằng code hiện tại (không gọi API)")
    p_rep.add_argument("--pred-dir", required=True)
    p_rep.add_argument("--configs", nargs="*", default=None, help="mặc định: mọi cấu hình có file dự đoán")
    args = p.parse_args()
    if args.stage == "pre":
        pre(args.dataset)
    elif args.stage == "replay":
        replay(args)
    else:
        post(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
