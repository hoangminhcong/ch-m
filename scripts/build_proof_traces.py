"""
Proof trace cho mọi ràng buộc (outcome RULE) của một cấu hình: khoản luật → ngữ cảnh → phân tích nghĩa vụ → các vòng
kiểm → dòng .decl → bằng chứng trên log → kiểm tập ràng buộc (src/evaluation/proof_trace.py). Không gọi API, không đọc gold.

Chạy:  python scripts/build_proof_traces.py --pred-dir results/cap_cerebras_v12 --config Y [--dataset cap|de]
Đọc:   <pred-dir>/predictions_<config>.json, data/processed/{cap_legal_graph_v2|cap_legal_graph|de_legal_graph}.json
Ghi:   <pred-dir>/proof_traces_<config>.html, <pred-dir>/proof_traces_<config>.json
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.proof_trace import build_traces, render_html, summarize  # noqa: E402
from src.symbolic.constraint_set_checks import check_constraint_set  # noqa: E402

PROCESSED = PROJECT_ROOT / "data" / "processed"
GRAPHS = {"cap": ("cap_legal_graph_v2.json", "cap_legal_graph.json"), "de": ("de_legal_graph.json",)}


def _graph(dataset: str) -> Path:
    for name in GRAPHS[dataset]:
        if (PROCESSED / name).exists():
            return PROCESSED / name
    raise SystemExit(f"Chưa dựng đồ thị luật cho bộ '{dataset}' ({', '.join(GRAPHS[dataset])})")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--pred-dir", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--dataset", choices=sorted(GRAPHS), default=None, help="mặc định: lấy từ file dự đoán")
    args = p.parse_args()
    src = Path(args.pred_dir) / f"predictions_{args.config}.json"
    if not src.exists():
        raise SystemExit(f"Không có {src}")
    doc = json.loads(src.read_text(encoding="utf-8"))
    dataset = args.dataset or doc.get("dataset", "cap")
    graph = json.loads(_graph(dataset).read_text(encoding="utf-8"))
    rules = {n: q["ast"] for n, q in doc["predictions"].items() if q.get("outcome") == "RULE" and q.get("ast")}
    findings = check_constraint_set(rules)
    traces = build_traces(doc, graph, findings)
    summary = summarize(traces, findings)
    base = Path(args.pred_dir) / f"proof_traces_{args.config}"
    base.with_suffix(".json").write_text(json.dumps({"summary": summary, "set_checks": findings, "traces": traces},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    title = f"Proof trace — cấu hình {args.config} ({dataset}, {doc.get('model', '?')})"
    base.with_suffix(".html").write_text(render_html(traces, title, summary), encoding="utf-8")
    sys.stdout.write(f"Ghi {base}.html / .json: {summary['rules']} ràng buộc; dẫn chứng ({summary['evidence_checked']} "
                     f"kiểm được): nguyên văn {summary['evidence_verbatim']}, gần nguyên văn {summary['evidence_near']}, "
                     f"không có căn cứ {summary['evidence_unsupported']}; kiểm tập: "
                     f"{summary['set_kinds'] or 'không phát hiện'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
