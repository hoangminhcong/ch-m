"""
Tập positive mới (docs/V2_DANG_KY_TRUOC.md mục 5–5.1): phiếu gán nhãn cho MỌI khoản InVeKoSV + DirektZahlDurchfV
(không lọc tay), theo từng năm nộp đơn; cùng định dạng dòng trả lời với phiếu CAP (cap_gold.parse_label_sheet).

Mỗi khoản kèm nguyên văn đích dẫn chiếu: điều khoản của 4 Quy định CAP (tiếng Anh, data/processed/cap_chunks.json)
và § tiếng Đức của văn bản có hiệu lực CÙNG năm (phiên bản trùng năm nhiều nhất). Phiếu không chứa đáp án.

Chạy:  python scripts/export_de_candidates.py
Đọc:   data/processed/de_chunks.json, cap_chunks.json      Ghi: docs/DE_ITEM_CANDIDATES.md,
       data/review/de_item_candidates.json (danh sách khoản cho run_cap_generation --candidates)
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_cap_candidates import _answer_line, _article_of, _order_key, _quote  # noqa: E402
from src.symbolic.verbalizer_roundtrip import extract_clause_dates, extract_clause_numeric_entities  # noqa: E402

PROCESSED = PROJECT_ROOT / "data" / "processed"
MD_PATH = PROJECT_ROOT / "docs" / "DE_ITEM_CANDIDATES.md"
JSON_PATH = PROJECT_ROOT / "data" / "review" / "de_item_candidates.json"
LAW_NAME = {"InVeKoSV": "InVeKoS-Verordnung (InVeKoSV)",
            "DirektZahlDurchfV": "Direktzahlungen-Durchführungsverordnung (DirektZahlDurchfV)"}

HEADER = """# Phiếu gán nhãn — tập Đức (InVeKoSV + DirektZahlDurchfV), {n} khoản

> Sinh tự động bởi `scripts/export_de_candidates.py` từ `data/processed/de_chunks.json` (văn bản có hiệu lực ngày
> 15/5 của từng năm nộp đơn 2015–2017, dựng lại từ lịch sử phiên bản trên buzer.de). Phiếu **không** chứa đáp án.
> Đọc **docs/HUONG_DAN_GAN_NHAN_CAP.md** (cách gán, ký hiệu ràng buộc) và mục "Tập Đức" ở
> **docs/DE_GAN_NHAN_BO_SUNG.md** trước khi làm; tên activity / thuộc tính tra ở **docs/CAP_VOCABULARY.md**.

- Mọi khoản của hai văn bản (không lọc). {n_eu} khoản có dẫn chiếu tới 4 Quy định EU (ứng viên Tier 4).
- Mã khoản có `@năm` khi văn bản khác nhau giữa các năm (VD `DE-InVeKoSV:§7(3)@2016`); không có `@` = giống nhau
  cả ba năm 2015–2017. Ràng buộc bạn ghi cho khoản có `@năm` chỉ áp cho hồ sơ của những năm đó.
- Nguyên văn tiếng Đức giữ nguyên (không dịch). Điều khoản EU được dẫn chiếu kèm bản tiếng Anh.

## Mẫu trả lời

Chép khối dưới đây vào một file `.txt`, điền vào chỗ `___`, rồi gửi lại. Mỗi khoản một dòng.

```
{answer_lines}
```

---
"""


def _base(node_id: str) -> str:
    return node_id.split("@", 1)[0]


def _de_text(target: str, years: Sequence[int], de: Sequence[Mapping[str, Any]]) -> str:
    """§ (hoặc khoản) tiếng Đức được dẫn chiếu, phiên bản trùng năm với khoản nguồn nhiều nhất."""
    section_level = "(" not in target
    cands = [c for c in de if (_base(c["node_id"]).split("(")[0] if section_level else _base(c["node_id"])) == target]
    if not cands and not section_level:  # khoản không có riêng → cả § (như de_legal_graph)
        return _de_text(target.split("(", 1)[0], years, de)
    if not cands:
        return ""
    overlapping = [c for c in cands if set(c["years"]) & set(years)] or list(cands)  # như de_legal_graph (M3)
    return "\n\n".join(f"[{c['node_id']}] {c['text']}" if len(overlapping) > 1 else c["text"]
                       for c in sorted(overlapping, key=lambda c: c["node_id"]))


def _cap_text(target: str, cap: Mapping[str, Mapping[str, Any]]) -> str:
    if target in cap:
        return cap[target]["text"]
    article = _article_of(target.split("(")[0])
    parts = sorted((nid for nid in cap if _article_of(nid) == article), key=_order_key)
    return "\n\n".join(cap[p]["text"] for p in parts)


def _ref_block(ref: Mapping[str, Any], chunk: Mapping[str, Any], de: Sequence[Mapping[str, Any]],
               cap: Mapping[str, Mapping[str, Any]]) -> str:
    target = ref["target"]
    if not ref["in_scope"]:
        return f"\n- Dẫn chiếu ra ngoài bộ: **{target}** (không kèm nguyên văn)\n"
    text = _cap_text(target, cap) if target.startswith("R") else _de_text(target, chunk["years"], de)
    if not text:
        return f"\n- Dẫn chiếu **{target}**: không tìm thấy nguyên văn trong bộ dữ liệu\n"
    where = "Quy định EU, tiếng Anh" if target.startswith("R") else "văn bản Đức, cùng năm"
    return (f"\n<details><summary>Được dẫn chiếu: <b>{target}</b> ({where})</summary>\n\n"
            f"{_quote(text)}\n\n</details>\n")


def section(chunk: Mapping[str, Any], de: Sequence[Mapping[str, Any]], cap: Mapping[str, Mapping[str, Any]]) -> str:
    years = ", ".join(str(y) for y in chunk["years"])
    flags = [LAW_NAME[chunk["law"]], f"năm {years}"]
    if any(r["kind"] == "eu" and r["in_scope"] for r in chunk["refs"]):
        flags.append("dẫn chiếu EU")
    return (f"### {chunk['node_id']} · {chunk['article_title']} · {' · '.join(flags)}\n\n"
            f"{_quote(chunk['text'])}\n{''.join(_ref_block(r, chunk, de, cap) for r in chunk['refs'])}\n---\n")


def build_markdown(de: Sequence[Mapping[str, Any]], cap: Mapping[str, Mapping[str, Any]]) -> str:
    n_eu = sum(1 for c in de if any(r["kind"] == "eu" and r["in_scope"] for r in c["refs"]))
    head = HEADER.format(n=len(de), n_eu=n_eu, answer_lines="\n".join(_answer_line(c["node_id"]) for c in de))
    body = []
    for law in LAW_NAME:
        items = [c for c in de if c["law"] == law]
        body.append(f"\n## {LAW_NAME[law]} — {len(items)} khoản\n\n" + "\n".join(section(c, de, cap) for c in items))
    return head + "".join(body)


BATCH_DIR = PROJECT_ROOT / "docs" / "de_batches"
MAX_ITEMS, MAX_KB = 15, 60  # như phiếu CAP (scripts/split_cap_sheet.py)


def batches(de: Sequence[Mapping[str, Any]], cap: Mapping[str, Mapping[str, Any]]) -> List[str]:
    """Đợt gửi AI gán nhãn: theo thứ tự phiếu, ≤ MAX_ITEMS khoản và ≤ MAX_KB KB (khoản quá dài đứng riêng)."""
    groups: List[List[tuple]] = [[]]
    for c in de:
        sec = section(c, de, cap)
        size = sum(len(s.encode("utf-8")) for _, s in groups[-1])
        if groups[-1] and (len(groups[-1]) >= MAX_ITEMS or size + len(sec.encode("utf-8")) > MAX_KB * 1024):
            groups.append([])
        groups[-1].append((c["node_id"], sec))
    pages = []
    for i, g in enumerate(groups, start=1):
        answers = "\n".join(_answer_line(nid) for nid, _ in g)
        pages.append(f"# Tập Đức — đợt {i:02d}/{len(groups):02d} ({len(g)} khoản)\n\n"
                     "Đọc docs/HUONG_DAN_GAN_NHAN_CAP.md và docs/DE_GAN_NHAN_BO_SUNG.md. Trả lời theo mẫu:\n\n"
                     f"```\n{answers}\n```\n\n---\n\n" + "\n".join(s for _, s in g))
    return pages


def candidates(de: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Danh sách khoản cho bước sinh (cùng khoá với cap_item_candidates.json; round = 1)."""
    # số kèm đơn vị hoặc ngày (Entity Matcher, có tiếng Đức) — rà soát M5: '\d' bất kỳ gắn cờ 253/256 khoản vì '(1)'
    return [{**c, "round": 1, "has_numeric_bound": bool(extract_clause_numeric_entities(c["text"])
                                                       or extract_clause_dates(c["text"]))} for c in de]


def main(argv: Optional[Sequence[str]] = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    de = json.loads((PROCESSED / "de_chunks.json").read_text(encoding="utf-8"))
    cap = {c["node_id"]: c for c in json.loads((PROCESSED / "cap_chunks.json").read_text(encoding="utf-8"))}
    MD_PATH.write_text(build_markdown(de, cap), encoding="utf-8")
    JSON_PATH.write_text(json.dumps(candidates(de), ensure_ascii=False, indent=1), encoding="utf-8")
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    for old in BATCH_DIR.glob("dot_*.md"):
        old.unlink()
    pages = batches(de, cap)
    for i, page in enumerate(pages, start=1):
        (BATCH_DIR / f"dot_{i:02d}.md").write_text(page, encoding="utf-8")
    sys.stdout.write(f"Ghi {MD_PATH} ({MD_PATH.stat().st_size // 1024} KB) và {JSON_PATH}: {len(de)} khoản; "
                     f"{len(pages)} đợt ở {BATCH_DIR}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
