"""
Nhãn REVIEW (M9, đăng ký trước B7) + bảng giữ lại — rủi ro cho các cấu hình trong một thư mục kết quả. Không gọi API.

Chạy:  python scripts/review_flags.py --pred-dir results/cap_cerebras_v12 [--configs Y N] [--gold …] [--no-log]
Đọc:   <pred-dir>/predictions_<cfg>.json; đồ thị luật; data/processed/<bộ>_mapping_graph.json (MAPS_TO, S2);
       log BPIC2018 (S1, nạp ~30 s; --no-log để bỏ S1); gold (chỉ để đếm sai / đúng trong bảng, không đổi nhãn)
Ghi:   <pred-dir>/review_flags_<cfg>.json và .md
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_proof_traces import _graph  # noqa: E402
from scripts.run_cap_generation import DATASETS, load_grounding  # noqa: E402
from scripts.score_cap import CONFIG_ORDER  # noqa: E402
from src.evaluation.cap_gold import scored_clauses  # noqa: E402
from src.evaluation.proof_trace import build_traces  # noqa: E402
from src.evaluation.review_flags import markdown, risk_coverage, rule_signals, summary  # noqa: E402
from src.symbolic.constraint_set_checks import check_constraint_set  # noqa: E402
from src.symbolic.process_checks import MassViolationChecker  # noqa: E402

PROCESSED = PROJECT_ROOT / "data" / "processed"
DEFAULT_GOLD = PROJECT_ROOT / "data" / "review" / "cap_gold_approved.json"
DOC_PREFIX = "Doc:"


def clause_doctypes(dataset: str) -> Optional[Dict[str, FrozenSet[str]]]:
    """Khoản → loại giấy tờ qua cạnh MAPS_TO của tầng Cầu nối; None nếu chưa dựng (S2 không xét)."""
    path = PROCESSED / f"{dataset}_mapping_graph.json"
    if not path.exists():
        return None
    out: Dict[str, set] = {}
    for e in json.loads(path.read_text(encoding="utf-8"))["edges"]:
        if e["type"] == "MAPS_TO":
            out.setdefault(e["source"], set()).add(e["target"][len(DOC_PREFIX):])
    return {k: frozenset(v) for k, v in out.items()}


def flags_for(doc: Dict[str, Any], dataset: str, mass: Optional[MassViolationChecker],
              doctypes: Optional[Dict[str, FrozenSet[str]]], years: Dict[str, Any]) -> Dict[str, Any]:
    preds = doc["predictions"]
    rules = {n: q["ast"] for n, q in preds.items() if q.get("outcome") == "RULE" and q.get("ast")}
    traces = build_traces(doc, json.loads(_graph(dataset).read_text(encoding="utf-8")), check_constraint_set(rules))
    out = {}
    for t in traces:
        nid = t["clause"]
        rec = None
        if mass is not None:
            rec = mass.assess(rules[nid], years=years[nid]) if years.get(nid) else mass.assess(rules[nid])
        out[nid] = rule_signals(t, rules[nid], rec,
                                doctypes.get(nid, frozenset()) if doctypes is not None else None)
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--pred-dir", required=True)
    p.add_argument("--configs", nargs="*", default=None, help="mặc định: mọi cấu hình có file dự đoán")
    p.add_argument("--gold", default=str(DEFAULT_GOLD), help="gold (chỉ để đếm trong bảng); không có file → bỏ")
    p.add_argument("--no-log", action="store_true", help="không nạp log (bỏ tín hiệu S1)")
    args = p.parse_args()
    pred_dir = Path(args.pred_dir)
    configs = [c for c in (args.configs or CONFIG_ORDER) if (pred_dir / f"predictions_{c}.json").exists()]
    if not configs:
        raise SystemExit(f"Không có predictions_*.json phù hợp trong {pred_dir}")
    gold_path = Path(args.gold)
    gold = scored_clauses(json.loads(gold_path.read_text(encoding="utf-8"))) if gold_path.exists() else None
    mass = None if args.no_log else MassViolationChecker(load_grounding().engine)
    for cfg in configs:
        doc = json.loads((pred_dir / f"predictions_{cfg}.json").read_text(encoding="utf-8"))
        dataset = doc.get("dataset", "cap")
        years = {c["node_id"]: c.get("years")
                 for c in json.loads(DATASETS[dataset][0].read_text(encoding="utf-8"))}
        flags = flags_for(doc, dataset, mass, clause_doctypes(dataset), years)
        curve = risk_coverage(flags, doc["predictions"], gold)
        base = pred_dir / f"review_flags_{cfg}"
        base.with_suffix(".json").write_text(json.dumps(
            {"config": cfg, "preregistration": "docs/V2_DANG_KY_TRUOC.md B7", "log_checked": mass is not None,
             "summary": summary(flags), "risk_coverage": curve, "rules": flags}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        base.with_suffix(".md").write_text(markdown(cfg, flags, curve), encoding="utf-8")
        s = summary(flags)
        sys.stdout.write(f"{cfg}: {s['rules']} luật, REVIEW {s['review']}; theo tín hiệu {s['by_signal']} "
                         f"→ {base.name}.md / .json\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
