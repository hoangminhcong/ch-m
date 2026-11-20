"""
Bộ CAP — dựng gold từ phiếu gán nhãn. Hai bước, bước 2 do NGƯỜI DUYỆT bấm (quyết định gold thuộc người duyệt):

  1. python scripts/build_cap_gold.py --labels CAP_ITEM_CANDIDATES_<tên>.txt
       → data/review/cap_gold_candidates.json  + docs/CAP_GOLD_REVIEW.md (bảng để đọc duyệt)
       Không sửa nhãn: khoản lỗi ký hiệu → 'invalid' (ghi lỗi), số/ngày không có trong luật → cảnh báo.
  2. python scripts/build_cap_gold.py --labels … --approve "<tên người duyệt>"
       → data/review/cap_gold_approved.json  (từ chối nếu còn khoản 'invalid' — sửa phiếu rồi chạy lại)

Đọc:  file nhãn, data/review/cap_item_candidates.json, data/processed/gamma_bpic2018.json
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.cap_gold import approval_blockers, build_gold_candidates, parse_label_sheet  # noqa: E402

REVIEW = PROJECT_ROOT / "data" / "review"
CANDIDATES = REVIEW / "cap_item_candidates.json"
GAMMA = PROJECT_ROOT / "data" / "processed" / "gamma_bpic2018.json"
OUT_CANDIDATE = REVIEW / "cap_gold_candidates.json"
OUT_APPROVED = REVIEW / "cap_gold_approved.json"
OUT_MD = PROJECT_ROOT / "docs" / "CAP_GOLD_REVIEW.md"
KIND_VI = {"positive": "Có ràng buộc", "trap": "Bẫy (BASELESS)", "uncertain": "Không chắc — chưa chấm",
           "invalid": "LỖI — sửa phiếu", "unlabeled": "Chưa điền"}


def _ast_line(ast: Mapping[str, Any]) -> str:
    from src.mde.constraint_ast import DeclareConstraintAST
    return DeclareConstraintAST.model_validate(ast).to_declare4py_line()


def render_review(gold: Mapping[str, Any], labels_name: str) -> str:
    s = gold["summary"]
    lines = [f"# Duyệt gold CAP — từ `{labels_name}`", "",
             "Sinh bởi `scripts/build_cap_gold.py`. Cột **Gold (AST)** là cách máy hiểu ký hiệu của người gán —",
             "kiểm tra từng dòng có đúng ý người gán không, rồi chạy lại với `--approve \"<tên>\"`.", "",
             "| Loại | Số khoản |", "|---|---|"]
    lines += [f"| {KIND_VI[k]} | {s[k]} |" for k in KIND_VI] + [f"| Trong đó Tier 4 | {s['tier4']} |",
                                                               f"| Có cảnh báo số/ngày | {s['with_warnings']} |", ""]
    lines += ["| Khoản | Đợt | Loại | Tier 4 | Gold (AST, dòng .decl) | Lỗi / cảnh báo |", "|---|---|---|---|---|---|"]
    for nid, c in gold["clauses"].items():
        if c["kind"] == "unlabeled":
            continue
        golds = "<br>".join(f"`{_ast_line(a)}`" for a in c["gold"]) or "—"
        notes = "<br>".join(c["errors"] + c["warnings"]).replace("|", "\\|") or ""
        lines.append(f"| {nid} | {c['round']} | {KIND_VI[c['kind']]} | {'Có' if c['tier4'] else ''} | "
                     f"{golds.replace('|', chr(92) + '|')} | {notes} |")
    return "\n".join(lines) + "\n"


def _outputs(out_dir: Any) -> tuple:
    """(gold ứng viên, gold đã duyệt, bảng duyệt .md) — mặc định data/review + docs."""
    if out_dir is None:
        return OUT_CANDIDATE, OUT_APPROVED, OUT_MD
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d / OUT_CANDIDATE.name, d / OUT_APPROVED.name, d / OUT_MD.name


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--labels", required=True)
    p.add_argument("--approve", metavar="REVIEWER", default=None)
    p.add_argument("--out-dir", default=None, help="ghi mọi file ra thư mục này (VD chạy thử với nhãn giả)")
    p.add_argument("--candidates", default=str(CANDIDATES),
                   help="phiếu khoản (mặc định CAP); tập Đức: data/review/de_item_candidates.json + --out-dir riêng")
    args = p.parse_args()
    if Path(args.candidates).resolve() != CANDIDATES.resolve() and args.out_dir is None:
        raise SystemExit("Phiếu khác phiếu CAP → cần --out-dir riêng (VD data/review/de_gold) để KHÔNG ghi đè gold CAP.")
    out_cand, out_appr, out_md = _outputs(args.out_dir)
    raw = Path(args.labels).read_bytes()
    try:
        # utf-8-sig: bỏ BOM mà Notepad (Windows) thêm vào đầu file — nếu không, dòng đầu bị coi là không có mã khoản
        labels = parse_label_sheet(raw.decode("utf-8-sig"))
    except ValueError as exc:
        raise SystemExit(f"{exc}\nSửa các dòng trên trong {Path(args.labels).name} rồi chạy lại.") from exc
    if not labels:
        raise SystemExit("Không đọc được dòng nhãn nào — kiểm tra định dạng 'Mẫu trả lời'.")
    gold = build_gold_candidates(labels, json.loads(Path(args.candidates).read_text(encoding="utf-8")),
                                 json.loads(GAMMA.read_text(encoding="utf-8")))
    gold["source"] = {"labels_file": Path(args.labels).name, "sha256": hashlib.sha256(raw).hexdigest()}
    out_cand.write_text(json.dumps(gold, ensure_ascii=False, indent=1), encoding="utf-8")
    out_md.write_text(render_review(gold, Path(args.labels).name), encoding="utf-8")
    sys.stdout.write(f"Đọc {len(labels)} dòng nhãn. Tổng hợp: {gold['summary']}\n"
                     f"Đã ghi {out_cand} và {out_md}\n")
    blockers = approval_blockers(gold)
    for b in blockers:
        sys.stdout.write(f"  LỖI {b}\n")
    if args.approve is None:
        return 0
    if blockers:
        sys.stdout.write("Chưa duyệt được: còn khoản lỗi ở trên.\n")
        return 1
    approved = {**gold, "status": "approved", "approved_by": args.approve,
                "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    out_appr.write_text(json.dumps(approved, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.stdout.write(f"Đã duyệt → {out_appr} (người duyệt: {args.approve})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
