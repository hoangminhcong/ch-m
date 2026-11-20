"""
TN7 bộ CAP — phán quyết từng hồ sơ trên TOÀN BỘ log BPIC2018 (≈43 800 hồ sơ, tên activity ghép, giờ Europe/Berlin).

Với mỗi khoản 'positive' của gold đã duyệt: chạy engine cho mọi gold và cho ràng buộc hệ thống sinh (cấu hình X, Y)
→ so phán quyết từng hồ sơ (src/evaluation/cap_conformance.py). Ngoài ra ghi hồ sơ của chính từng gold
(số hồ sơ vi phạm / kích hoạt) — đây là kết quả kiểm toán tuân thủ.

Chạy:  python scripts/run_cap_conformance.py [--gold …] [--pred-dir results/cap] [--configs X Y] [--allow-candidate]
Đọc:   data/interim/bpic2018_events.parquet, bpic2018_cases.parquet, gold, predictions_<config>.json
Ghi:   <pred-dir>/conformance.json
"""

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.score_cap import DEFAULT_GOLD, DEFAULT_PRED, load_gold, load_predictions  # noqa: E402
from src.evaluation.cap_conformance import best_gold_match, rule_profile  # noqa: E402
from src.evaluation.cap_gold import scored_clauses  # noqa: E402
from src.evaluation.cap_scoring import RULE  # noqa: E402
from src.kg.process_graph_builder import with_composite_activity  # noqa: E402
from src.mde.constraint_ast import DeclareConstraintAST, activity_members  # noqa: E402
from src.symbolic.declare4py_verifier import Declare4Py  # noqa: E402

INTERIM = PROJECT_ROOT / "data" / "interim"
TIMEZONE = "Europe/Berlin"  # log ghi UTC, nghiệp vụ theo giờ Đức (xem C3c của runbook)


def decl_line(ast: Mapping[str, Any]) -> str:
    return DeclareConstraintAST.model_validate(dict(ast)).to_declare4py_line().strip()


def collect_lines(gold: Mapping[str, Any], preds: Mapping[str, Mapping[str, Any]],
                  years_of: Optional[Mapping[str, List[int]]] = None) -> Dict[str, Any]:
    """Mỗi khoản positive: dòng .decl của gold và của dự đoán RULE từng cấu hình.
    years_of (tập Đức): năm của khoản → chỉ so trên hồ sơ của các năm đó; None = mọi hồ sơ (bộ CAP)."""
    plan: Dict[str, Any] = {}
    for nid, c in scored_clauses(gold).items():
        if c["kind"] != "positive":
            continue
        plan[nid] = {"tier4": c["tier4"], "gold": [decl_line(a) for a in c["gold"]],
                     "pred": {cfg: decl_line(p[nid]["ast"]) for cfg, p in preds.items()
                              if nid in p and p[nid]["outcome"] == RULE},
                     "years": (years_of or {}).get(nid)}
    return plan


def _scoped(states: Mapping[str, List[str]], case_years: Optional[List[int]],
            years: Optional[List[int]]) -> Mapping[str, List[str]]:
    if not years or case_years is None:
        return states
    keep = [i for i, y in enumerate(case_years) if y in set(years)]
    return {ln: [s[i] for i in keep] for ln, s in states.items()}


def unknown_activities(lines: List[str], known: Set[str]) -> Set[str]:
    """Activity trong các dòng .decl mà log không có; nhóm '{A | B}' được kiểm từng thành viên (như engine)."""
    names = {a for ln in lines for a in ln.split("[", 1)[1].split("]", 1)[0].split(",")}
    return {m for a in names for m in activity_members(a)} - known


def run_engine(engine: Declare4Py, lines: List[str]) -> Dict[str, List[str]]:
    """Trạng thái của từng dòng trên mọi hồ sơ, theo cùng thứ tự hồ sơ."""
    with tempfile.NamedTemporaryFile("w", suffix=".decl", delete=False, encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        path = f.name
    try:
        engine.parse_decl_model(path)
        res = engine.conformance_checking(consider_vacuity=True)
    finally:
        os.unlink(path)
    ordered = [res[k] for k in sorted(res)]
    return {ln: [per[ln].state for per in ordered] for ln in lines}


def evaluate(plan: Mapping[str, Any], states: Mapping[str, List[str]],
             case_years: Optional[List[int]] = None) -> Dict[str, Any]:
    """case_years: năm của từng hồ sơ theo cùng thứ tự với states (cần khi có khoản mang 'years')."""
    clauses = {}
    for nid, item in plan.items():
        st = _scoped(states, case_years, item.get("years"))
        clauses[nid] = {"tier4": item["tier4"],
                        "gold": [{"line": gl, **rule_profile(st[gl])} for gl in item["gold"]],
                        "pred": {cfg: {"line": pl, **best_gold_match(item["gold"], pl, st)}
                                 for cfg, pl in item["pred"].items()}}
        if item.get("years"):
            clauses[nid]["years"] = item["years"]
    return clauses


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--gold", default=str(DEFAULT_GOLD))
    p.add_argument("--pred-dir", default=str(DEFAULT_PRED))
    p.add_argument("--configs", nargs="*", default=["X", "Y"])
    p.add_argument("--allow-candidate", action="store_true")
    p.add_argument("--candidates", default=None,
                   help="phiếu khoản có 'years' (tập Đức: data/review/de_item_candidates.json) → mỗi khoản chỉ so "
                        "trên hồ sơ của các năm của nó; mặc định: mọi hồ sơ (bộ CAP)")
    args = p.parse_args()
    gold = load_gold(Path(args.gold), args.allow_candidate)
    preds = {k: v for k, v in load_predictions(Path(args.pred_dir)).items() if k in args.configs}
    years_of = ({c["node_id"]: c["years"] for c in json.loads(Path(args.candidates).read_text(encoding="utf-8"))
                 if c.get("years")} if args.candidates else {})
    # gold dựng sau 2026-11-18 tự mang 'years' (rà soát E-H5); --candidates chỉ cần cho gold cũ
    years_of = {**years_of, **{nid: c["years"] for nid, c in gold["clauses"].items() if c.get("years")}} or None
    unscoped = [nid for nid in scored_clauses(gold) if nid.startswith("DE-") and nid not in (years_of or {})]
    if unscoped:
        raise SystemExit(f"Khoản tập Đức không có năm ({len(unscoped)}, VD {unscoped[:3]}) — sẽ bị so trên mọi năm. "
                         "Dựng lại gold, hoặc thêm --candidates data/review/de_item_candidates.json.")
    plan = collect_lines(gold, preds, years_of)
    lines = sorted({ln for it in plan.values() for ln in it["gold"] + list(it["pred"].values())})
    if not lines:
        raise SystemExit("Không có khoản positive nào để kiểm.")
    start = time.perf_counter()
    events = with_composite_activity(pd.read_parquet(INTERIM / "bpic2018_events.parquet"))
    cases = pd.read_parquet(INTERIM / "bpic2018_cases.parquet")
    unknown = unknown_activities(lines, set(events["concept:name"].unique()))
    if unknown:
        raise SystemExit(f"Activity không có trong log: {sorted(unknown)}")
    engine = Declare4Py(events, cases=cases, timezone=TIMEZONE, calendar_periods=True)
    sys.stdout.write(f"Nạp log: {len(cases)} hồ sơ, {len(events)} event ({time.perf_counter() - start:.0f}s); "
                     f"kiểm {len(lines)} ràng buộc...\n")
    states = run_engine(engine, lines)
    result = {"gold_status": gold.get("status"), "timezone": TIMEZONE, "cases": len(cases),
              "clauses": evaluate(plan, states, engine.trace_years() if years_of else None)}
    empty = [nid for nid, c in result["clauses"].items() if c["gold"] and c["gold"][0]["cases"] == 0]
    if empty:
        raise SystemExit(f"Khoản không có hồ sơ nào trong phạm vi năm của nó: {empty} (kiểm 'years' và case:year).")
    # khoản positive mà cấu hình KHÔNG sinh luật (BASELESS / FAILED) — không có trong biểu đồ kappa (rà soát E-M2)
    result["no_rule"] = {cfg: sorted(nid for nid, it in plan.items() if cfg not in it["pred"]) for cfg in preds}
    out = Path(args.pred_dir) / "conformance.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for nid, c in result["clauses"].items():
        g = c["gold"][0]
        sys.stdout.write(f"{nid:<18} gold: vi phạm {g['violated']:>6} / kích hoạt {g['activated']:>6}\n")
        for cfg, r in c["pred"].items():
            sys.stdout.write(f"   {cfg:<3} khớp {r['agreement']}  kappa {r['kappa']}  P {r['precision']}  "
                             f"R {r['recall']}{'  RỖNG' if r['vacuous'] else ''}\n")
    sys.stdout.write(f"\nĐã ghi {out} ({time.perf_counter() - start:.0f}s)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
