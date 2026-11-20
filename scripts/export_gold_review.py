"""
TN2 bước 2 – Sinh phiếu gán nhãn (rà soát) cho toàn bộ rule gold của bộ đề.

Phiếu đặt cạnh nhau: nguyên văn luật (chép tự động từ directive_chunks.json, không chép tay),
gold đang ghi, và (trừ chế độ --blind) nhận xét sơ bộ của trợ lý (data/review/gold_review_notes.json).
Người gán nhãn điền quyết định GIỮ / SỬA / BẪY / LOẠI theo docs/HUONG_DAN_GAN_NHAN.md.

Chạy:  python scripts/export_gold_review.py           -> docs/GOLD_REVIEW.md        (có nhận xét trợ lý)
       python scripts/export_gold_review.py --blind   -> docs/GOLD_REVIEW_BLIND.md  (cho người gán độc lập)
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHUNKS_PATH = PROJECT_ROOT / "data" / "processed" / "directive_chunks.json"
NOTES_PATH = PROJECT_ROOT / "data" / "review" / "gold_review_notes.json"
OUTPUT_PATH = PROJECT_ROOT / "docs" / "GOLD_REVIEW.md"
BLIND_OUTPUT_PATH = PROJECT_ROOT / "docs" / "GOLD_REVIEW_BLIND.md"

VERDICT_LABEL = {"OK": "✅ hợp lý", "XEM": "⚠ cần xem", "SAI": "❌ gold không khớp luật"}

LABEL_GUIDE = """## Cách gán nhãn

Đọc **docs/HUONG_DAN_GAN_NHAN.md** trước khi bắt đầu. Tóm tắt: với mỗi rule, trả lời
*"Từ khoản luật này, có viết được một ràng buộc kiểm tra được trên log BPIC2017 mà đúng với
**nội dung** luật không?"*

| Nhãn | Khi nào |
|---|---|
| **GIỮ** | Gold đúng nội dung luật (chấp nhận proxy hợp lý) |
| **SỬA** | Luật có nghĩa vụ kiểm được, nhưng gold ghi sai → ghi ràng buộc đúng |
| **BẪY** | Luật không cho ra ràng buộc kiểm được trên log → đáp án đúng là BASELESS |
| **LOẠI** | Khoản này không phải nghĩa vụ (VD phạm vi áp dụng, định nghĩa, giả định tính toán) |

**Độ chắc chắn:** Cao / TB / Thấp.
"""

HEADER = """# Phiếu gán nhãn Gold — toàn bộ {n} rule (TN2, bước 2)

> File này được **sinh tự động** bởi `scripts/export_gold_review.py`. Nguyên văn luật chép từ
> `data/processed/directive_chunks.json`; gold chép từ `BENCHMARK_RULES`. Nhận xét là **ý kiến sơ bộ
> của trợ lý** (`data/review/gold_review_notes.json`) — **bạn là người quyết định**.

{guide}
## Tổng hợp nhận xét sơ bộ của trợ lý

{summary}

## Bảng quyết định (điền vào đây rồi gửi lại)

| Rule | Tier | Tập | Điều | Trợ lý đề xuất | **Quyết định của bạn** | Ràng buộc mới (nếu SỬA) | Độ chắc chắn | Lý do ngắn |
|---|---|---|---|---|---|---|---|---|
{decision_rows}

---
"""

BLIND_HEADER = """# Phiếu gán nhãn Gold — bản độc lập ({n} rule)

> Phiếu dành cho **người gán nhãn độc lập**. Hãy tự đánh giá, **không trao đổi** với người gán nhãn khác
> và không xem phiếu của họ cho đến khi cả hai đã nộp. Nguyên văn luật được chép tự động từ dữ liệu.

Người gán nhãn: ____________ · Ngày: ____________ · Thời gian làm (phút): ______

{guide}
## Bảng quyết định (điền vào đây rồi gửi lại)

| Rule | Tier | Tập | Điều | **Quyết định** | Ràng buộc mới (nếu SỬA) | Độ chắc chắn | Lý do ngắn |
|---|---|---|---|---|---|---|---|
{decision_rows}

---
"""


def format_gold(rule: Mapping[str, Any]) -> str:
    """Viết gold dạng đọc được: Template(A → B) [điều kiện] [thời hạn]."""
    acts = rule["act_a"] if not rule.get("act_b") else f"{rule['act_a']} → {rule['act_b']}"
    parts = [f"`{rule['template']}({acts})`"]
    if rule.get("attr"):
        parts.append(f"với `{rule['attr']} {rule['op']} {rule['val']}`")
    if rule.get("time_max") is not None:
        parts.append(f"trong ≤ {rule['time_max']} ngày")
    return " ".join(parts)


def _split_name(rule_id: str, dev_ids: Set[str]) -> str:
    return "dev" if rule_id in dev_ids else "heldout_test"


def _law_text(
    article_id: str, chunks_by_id: Mapping[str, Mapping[str, Any]], hardcoded: Mapping[str, str]
) -> str:
    if article_id in chunks_by_id:
        return f"> {chunks_by_id[article_id]['text']}"
    if article_id in hardcoded:
        return (
            "> ⚠ Không có trong văn bản đã parse — đoạn này được **viết cứng** trong code, "
            f"cần đối chiếu EUR-Lex:\n>\n> {hardcoded[article_id]}"
        )
    raise KeyError(f"Không có văn bản luật cho {article_id}")


def _summary(rules: Iterable[Mapping[str, Any]], notes: Mapping[str, Mapping[str, str]]) -> str:
    rules = list(rules)
    by_verdict = Counter(notes[r["rule_id"]]["verdict"] for r in rules)
    by_suggest = Counter(notes[r["rule_id"]]["suggest"] for r in rules)
    verdict_line = ", ".join(f"{VERDICT_LABEL[k]}: **{by_verdict.get(k, 0)}**" for k in VERDICT_LABEL)
    suggest_line = ", ".join(f"{k}: **{v}**" for k, v in sorted(by_suggest.items()))
    return f"- Đánh giá: {verdict_line}\n- Đề xuất: {suggest_line}"


def _decision_row(
    rule: Mapping[str, Any], note: Optional[Mapping[str, str]], dev_ids: Set[str]
) -> str:
    base = (
        f"| {rule['rule_id']} | {rule['tier'].split('_')[0]} | {_split_name(rule['rule_id'], dev_ids)} "
        f"| {rule['article_id']} |"
    )
    suggest = f" {note['suggest']} |" if note else ""
    return f"{base}{suggest} | | | |"


def _opinion_block(note: Optional[Mapping[str, str]]) -> str:
    if not note:
        return ""
    hint = f"\n- **Gợi ý sửa:** {note['fix_hint']}" if note.get("fix_hint") else ""
    return (
        f"**Nhận xét sơ bộ của trợ lý:** {VERDICT_LABEL[note['verdict']]} — đề xuất **{note['suggest']}**\n"
        f"- {note['issue']}{hint}\n\n"
    )


def _rule_section(
    rule: Mapping[str, Any], note: Optional[Mapping[str, str]], law: str, dev_ids: Set[str]
) -> str:
    kind = "BẪY (đáp án đúng: BASELESS)" if rule.get("is_trap") else "ràng buộc đúng"
    return (
        f"## {rule['rule_id']} — {rule['article_id']} · {rule['tier']} · tập "
        f"`{_split_name(rule['rule_id'], dev_ids)}`\n\n"
        f"**Luật nói (nguyên văn):**\n\n{law}\n\n"
        f"**Gold đang ghi ({kind}):** {format_gold(rule)}\n\n"
        f"**Mô tả gold:** {rule['description']}\n\n"
        f"{_opinion_block(note)}"
        f"**Quyết định:** ______ · **Độ chắc chắn:** ______ · **Lý do:** \n\n---\n"
    )


def build_review_markdown(
    rules: List[Mapping[str, Any]],
    chunks_by_id: Mapping[str, Mapping[str, Any]],
    notes: Mapping[str, Mapping[str, str]],
    dev_ids: Set[str],
    hardcoded_texts: Optional[Mapping[str, str]] = None,
    blind: bool = False,
) -> str:
    """
    Ghép phiếu gán nhãn. Thiếu văn bản luật của bất kỳ rule nào thì báo KeyError.
    blind=True: bỏ toàn bộ nhận xét/đề xuất của trợ lý (không cần `notes`).
    """
    hardcoded = hardcoded_texts or {}
    if not blind:
        missing = [r["rule_id"] for r in rules if r["rule_id"] not in notes]
        if missing:
            raise KeyError(f"Thiếu nhận xét cho: {missing}")
    note_of = (lambda _rid: None) if blind else (lambda rid: notes[rid])
    sections = [
        _rule_section(r, note_of(r["rule_id"]), _law_text(r["article_id"], chunks_by_id, hardcoded), dev_ids)
        for r in rules
    ]
    rows = "\n".join(_decision_row(r, note_of(r["rule_id"]), dev_ids) for r in rules)
    if blind:
        header = BLIND_HEADER.format(n=len(rules), guide=LABEL_GUIDE, decision_rows=rows)
    else:
        header = HEADER.format(
            n=len(rules), guide=LABEL_GUIDE, summary=_summary(rules, notes), decision_rows=rows
        )
    return header + "\n" + "\n".join(sections)


def main(argv: List[str]) -> int:
    sys.path.insert(0, str(PROJECT_ROOT))
    from src.evaluation.benchmark_builder import ANNEX_I_TEXT, BENCHMARK_RULES, DEV_RULE_IDS

    blind = "--blind" in argv
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks_by_id: Dict[str, Any] = {c["article_id"]: c for c in json.load(f)}
    notes: Dict[str, Any] = {}
    if not blind:
        with open(NOTES_PATH, encoding="utf-8") as f:
            notes = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

    markdown = build_review_markdown(
        list(BENCHMARK_RULES), chunks_by_id, notes, set(DEV_RULE_IDS),
        hardcoded_texts={"Annex I(II)": ANNEX_I_TEXT}, blind=blind,
    )
    output = BLIND_OUTPUT_PATH if blind else OUTPUT_PATH
    output.write_text(markdown, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(f"Đã ghi {output.relative_to(PROJECT_ROOT)} ({len(BENCHMARK_RULES)} rule)\n")
    if not blind:
        sys.stdout.write(_summary(BENCHMARK_RULES, notes) + "\n")
    return 0


if __name__ == "__main__":
    # Bộ BPIC2017 đang tạm vô hiệu (src/datasets.py); mở lại: $env:NSAI_ENABLE_BPIC2017 = "1"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.datasets import require_bpic2017
    require_bpic2017(__file__)
    sys.exit(main(sys.argv[1:]))
