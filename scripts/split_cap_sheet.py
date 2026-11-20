"""
Chia phiếu CAP thành các ĐỢT để gửi cho AI gán nhãn (HUONG_DAN_GAN_NHAN_CAP.md, mục 10.3).

Mỗi đợt: theo đúng thứ tự phiếu, tối đa --max-items khoản VÀ tối đa --max-kb KB (khoản kèm nhiều văn bản dẫn chiếu
rất dài); một khoản dài hơn giới hạn vẫn đứng riêng một đợt. Mỗi file đợt gồm phần "Mẫu trả lời" của chính các khoản
trong đợt + nguyên văn từng khoản (cùng định dạng với docs/CAP_ITEM_CANDIDATES.md). Mọi AI nhận đúng cùng các file.

Chạy:  python scripts/split_cap_sheet.py [--max-items 15] [--max-kb 60] [--out-dir docs/cap_batches]
Đọc:   data/review/cap_item_candidates.json (bản máy đọc của phiếu)
Ghi:   <out-dir>/dot_01.md … và <out-dir>/DANH_SACH_DOT.md (đợt nào gồm khoản nào)
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_cap_candidates import DOC_NAME, JSON_PATH, _answer_line, _quote, _ref_block  # noqa: E402

DEFAULT_OUT = PROJECT_ROOT / "docs" / "cap_batches"
DEFAULT_MAX_ITEMS = 15
DEFAULT_MAX_KB = 60


def render_clause(rec: Mapping[str, Any]) -> str:
    """Một khoản, đúng định dạng phiếu (dẫn chiếu lấy từ trường 'referenced' đã lưu)."""
    flags = [DOC_NAME.get(rec["doc_id"], rec["doc_id"])] + (["có con số"] if rec["has_numeric_bound"] else [])
    refs = "".join(_ref_block(r) for r in rec.get("referenced", []))
    return f"### {rec['node_id']} · {rec['article_title']} · {' · '.join(flags)}\n\n{_quote(rec['text'])}\n{refs}\n---\n"


def make_batches(records: Sequence[Mapping[str, Any]], max_items: int, max_bytes: int) -> List[List[Mapping[str, Any]]]:
    batches: List[List[Mapping[str, Any]]] = [[]]
    size = 0
    for rec in records:
        n = len(render_clause(rec).encode("utf-8"))
        if batches[-1] and (len(batches[-1]) >= max_items or size + n > max_bytes):
            batches.append([])
            size = 0
        batches[-1].append(rec)
        size += n
    return [b for b in batches if b]


def render_batch(batch: Sequence[Mapping[str, Any]], k: int, total: int) -> str:
    ids = [r["node_id"] for r in batch]
    lines = "\n".join(_answer_line(i) for i in ids)
    body = "\n".join(render_clause(r) for r in batch)
    return (f"# Phiếu CAP — đợt {k}/{total} ({len(batch)} khoản: {ids[0]} … {ids[-1]})\n\n"
            f"Gán nhãn đúng {len(batch)} khoản dưới đây theo `HUONG_DAN_GAN_NHAN_CAP.md`. Trả về đúng {len(batch)} dòng "
            f"theo mẫu sau (thay `___`), mỗi khoản một dòng, không thêm dòng nào khác:\n\n"
            f"```\n{lines}\n```\n\n---\n\n{body}")


def render_index(batches: Sequence[Sequence[Mapping[str, Any]]]) -> str:
    rows = [f"| dot_{k:02d}.md | {len(b)} | {sum(len(render_clause(r).encode('utf-8')) for r in b) // 1024} KB | "
            f"Đợt {'/'.join(sorted({str(r['round']) for r in b}))} | {', '.join(r['node_id'] for r in b)} |"
            for k, b in enumerate(batches, start=1)]
    return ("# Danh sách đợt gán nhãn CAP\n\nGửi cho MỌI AI đúng các file này, cùng `HUONG_DAN_GAN_NHAN_CAP.md`, "
            "`CAP_VOCABULARY.md` và câu lệnh mục 10.4. Nối câu trả lời các đợt theo thứ tự vào "
            "`CAP_ITEM_CANDIDATES_<tên-AI>.txt`.\n\n| File | Số khoản | Dung lượng | Đợt phiếu | Khoản |\n"
            "|---|---:|---:|---|---|\n" + "\n".join(rows) + "\n")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)
    p.add_argument("--max-kb", type=int, default=DEFAULT_MAX_KB)
    p.add_argument("--out-dir", default=str(DEFAULT_OUT))
    args = p.parse_args()
    records = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    batches = make_batches(records, args.max_items, args.max_kb * 1024)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("dot_*.md"):
        old.unlink()  # chia lại → xoá các đợt cũ trong thư mục đợt (chỉ file dot_*.md)
    for k, b in enumerate(batches, start=1):
        (out / f"dot_{k:02d}.md").write_text(render_batch(b, k, len(batches)), encoding="utf-8")
    (out / "DANH_SACH_DOT.md").write_text(render_index(batches), encoding="utf-8")
    sizes: Dict[str, int] = {f"dot_{k:02d}": len(b) for k, b in enumerate(batches, start=1)}
    sys.stdout.write(f"{len(records)} khoản → {len(batches)} đợt trong {out}\n{sizes}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
