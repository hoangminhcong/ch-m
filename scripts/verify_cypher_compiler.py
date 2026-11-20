"""
M8 — đối chiếu Cypher (src/kg/cypher_compiler.py) với engine Python TRÊN CÙNG DỮ LIỆU, từng hồ sơ. Cần Neo4j chạy
(Docker: `docker start nsai-neo4j`; .env có NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD). Không gọi API LLM.

Chạy:  python scripts/verify_cypher_compiler.py --synthetic
           (1) 17 mẫu × (không / có điều kiện hồ sơ) trên MỌI vết độ dài 1..3 của {A, B, C} — kiểm ngữ nghĩa vét cạn
           (2) 9 mẫu có thời hạn × 9 cửa sổ (ngày, tuần, tháng lịch, ngày làm việc, giờ) + điều kiện ngày, trên log
               có thời điểm rơi vào cuối tuần, cuối tháng, tháng 2 năm nhuận, ngày đổi giờ, 23:30 giờ Đức
       python scripts/verify_cypher_compiler.py --pred-dir results/cap_cerebras_v12 --config Y --cases 2000
           mọi luật dịch được của cấu hình, trên 2000 hồ sơ BPIC2018 chọn ngẫu nhiên (seed 2018)
Ghi đè nhãn :EvCase / :Ev trong Neo4j (không đụng node KG). Thoát mã 1 nếu có hồ sơ lệch.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.declare_engine_validation import exhaustive_log  # noqa: E402
from src.kg.cypher_compiler import UnsupportedConstraint, compile_constraint  # noqa: E402
from src.kg.event_graph import event_graph_rows, select_cases, write_event_graph  # noqa: E402
from src.mde.constraint_ast import BINARY_TEMPLATES, UNARY_TEMPLATES  # noqa: E402
from src.symbolic.declare4py_verifier import Declare4Py  # noqa: E402


def synthetic() -> Tuple[Declare4Py, Dict[str, Dict[str, Any]]]:
    df = exhaustive_log(["A", "B", "C"], 3)
    ids = sorted(df["case:concept:name"].unique())
    cases = pd.DataFrame({"case:concept:name": ids, "case:flag": [i % 2 == 0 for i in range(len(ids))]})
    rules = {}
    for tpl in sorted(UNARY_TEMPLATES | BINARY_TEMPLATES):
        for cond in (None, ("case:flag", "==", True)):
            ast = {"article_id": "s", "template_name": tpl, "activation_activity": "A",
                   "target_activity": None if tpl in UNARY_TEMPLATES else "B"}
            if cond:
                ast.update(activation_attr=cond[0], activation_op=cond[1], activation_val=cond[2])
            rules[f"{tpl}{' | flag' if cond else ''}"] = ast
    return Declare4Py(df, cases=cases), rules


TIMED = ("Response", "Alternate Response", "Chain Response", "Responded Existence", "Precedence",
         "Alternate Precedence", "Chain Precedence", "Not Precedence", "Not Response")
WINDOWS = ((0, 1, "d"), (0, 7, "d"), (1, 3, "d"), (0, 1, "w"), (0, 1, "mo"), (0, 2, "wd"), (1, 5, "wd"), (0, 3, "h"),
           (0, 48, "h"))
BASES = ("2016-01-29", "2016-01-30", "2016-01-31", "2016-02-26", "2017-01-31", "2016-03-25", "2016-10-28")
CLOCKS = ("10:00", "23:30")
GAPS = (0, 1, 2, 3, 6, 7, 8, 13, 14, 28, 29, 30, 31, 35, 60)
SEQUENCES = ("AB", "BA", "ABB", "AAB", "ABA", "BAB")


def synthetic_timed() -> Tuple[Declare4Py, Dict[str, Dict[str, Any]]]:
    """Log có thời gian (giờ Đức) — mọi ca biên của Quy định 1182/71 mà engine xử lý; engine như bộ CAP."""
    rows, cases = [], []
    for base in BASES:
        for clock in CLOCKS:
            for gap in GAPS:
                for seq in SEQUENCES:
                    cid = f"{seq}|{base}T{clock}|+{gap}d"
                    t0 = pd.Timestamp(f"{base} {clock}", tz="Europe/Berlin")
                    for k, act in enumerate(seq):
                        rows.append({"case:concept:name": cid, "concept:name": act,
                                     "time:timestamp": (t0 + pd.Timedelta(days=gap * k)).tz_convert("UTC")})
                    cases.append({"case:concept:name": cid, "case:year": base[:4]})
    engine = Declare4Py(pd.DataFrame(rows), cases=pd.DataFrame(cases), timezone="Europe/Berlin", calendar_periods=True)
    rules: Dict[str, Dict[str, Any]] = {}
    for tpl in TIMED:
        for lo, hi, unit in WINDOWS:
            rules[f"{tpl} [{lo},{hi},{unit}]"] = {"article_id": "t", "template_name": tpl, "activation_activity": "A",
                                                  "target_activity": "B", "time_min": lo, "time_max": hi,
                                                  "time_unit": unit}
    dated = {"Absence A date > year-01-30": ("Absence", None, ">", "year-01-30"),
             "Existence A date <= year-02-28": ("Existence", None, "<=", "year-02-28"),
             "Precedence date(B) >= year-03-01": ("Precedence", "B", ">=", "year-03-01"),
             "Response date(A) == year-01-31": ("Response", "B", "==", "year-01-31"),
             "Not Response date(A) < year+1-01-01": ("Not Response", "B", "<", "year+1-01-01"),
             "Absence A date >= 2016-02-01": ("Absence", None, ">=", "2016-02-01"),
             "Alternate Response date(A) != year-01-29": ("Alternate Response", "B", "!=", "year-01-29")}
    for name, (tpl, tgt, op, val) in dated.items():
        rules[name] = {"article_id": "t", "template_name": tpl, "activation_activity": "A", "target_activity": tgt,
                       "activation_attr": "date", "activation_op": op, "activation_val": val}
    rules["Response [0,7,d] + date(A) <= year-02-28"] = {**rules["Response [0,7,d]"], "activation_attr": "date",
                                                         "activation_op": "<=", "activation_val": "year-02-28"}
    return engine, rules


def real(pred_dir: Path, config: str) -> Tuple[Declare4Py, Dict[str, Dict[str, Any]]]:
    from scripts.run_cap_generation import load_grounding
    doc = json.loads((pred_dir / f"predictions_{config}.json").read_text(encoding="utf-8"))
    rules = {n: p["ast"] for n, p in doc["predictions"].items() if p.get("outcome") == "RULE" and p.get("ast")}
    return load_grounding().engine, rules


def engine_violated(engine: Declare4Py, decl: str, case_ids: set) -> set:
    parsed = engine.parse_decl_lines([decl])[0]
    return {cid for cid, res, _ in engine.case_results(parsed) if cid in case_ids and res.state == "Violated"}


def compare(engine: Declare4Py, rules: Mapping[str, Mapping[str, Any]], session: Any, case_ids: List[str]
            ) -> Tuple[List[Tuple[str, int, int, int]], List[Tuple[str, str]]]:
    rows, skipped = [], []
    wanted = set(case_ids)
    for name, ast in sorted(rules.items()):
        try:
            compiled = compile_constraint(ast, engine.calendar_periods)
        except UnsupportedConstraint as exc:
            skipped.append((name, str(exc)))
            continue
        cy = {r["case_id"] for r in session.run(compiled.cypher) if r["violated"]}
        py = engine_violated(engine, compiled.decl, wanted)
        rows.append((name, len(py), len(cy), len(py ^ cy)))
    return rows, skipped


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--synthetic", action="store_true")
    p.add_argument("--pred-dir")
    p.add_argument("--config", default="Y")
    p.add_argument("--cases", type=int, default=2000)
    args = p.parse_args()
    if not args.synthetic and not args.pred_dir:
        raise SystemExit("Chọn --synthetic hoặc --pred-dir")
    runs = [synthetic(), synthetic_timed()] if args.synthetic else [real(Path(args.pred_dir), args.config)]
    from src.kg.neo4j_store import Neo4jKGStore
    store = Neo4jKGStore.from_env()
    rows, skipped, n_cases, n_events = [], [], 0, 0
    try:
        with store._session() as session:
            for engine, rules in runs:
                case_ids = select_cases(engine._trace_index, None if args.synthetic else args.cases)
                cases, events = event_graph_rows(engine._trace_index, case_ids, engine.timezone)
                write_event_graph(session, cases, events)
                r, sk = compare(engine, rules, session, case_ids)
                rows, skipped = rows + r, skipped + sk
                n_cases, n_events = n_cases + len(case_ids), n_events + len(events)
    finally:
        store.close()
    bad = [r for r in rows if r[3]]
    sys.stdout.write(f"{n_cases} hồ sơ, {n_events} event; {len(rows)} luật so được, {len(skipped)} chưa dịch\n")
    for name, py, cy, diff in rows:
        sys.stdout.write(f"  {'LỆCH' if diff else 'khớp'} {name:<40} vi phạm: engine {py}, Cypher {cy}, lệch {diff}\n")
    for name, why in skipped:
        sys.stdout.write(f"  bỏ qua {name}: {why}\n")
    sys.stdout.write("KẾT LUẬN: " + ("Cypher khớp engine từng hồ sơ trên mọi luật so được\n" if not bad
                                     else f"{len(bad)} luật LỆCH — xem trên\n"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
