"""
Bộ dữ liệu thứ hai (BPIC2018 + 4 Quy định CAP) – sinh phiếu gán nhãn Phần B và bảng từ vựng log.

Hai đợt, KHÔNG lọc theo phạm vi hay từ ngữ nghĩa vụ (người gán nhãn quyết định, giữ dữ liệu phong phú):
  Đợt 1: mọi khoản có dẫn chiếu sang văn bản KHÁC trong bộ 4 Quy định (ứng viên Tier 4 / Graph-RAG).
  Đợt 2: mẫu ngẫu nhiên phân tầng theo văn bản (tỉ lệ số khoản, phần dư lớn nhất) từ các khoản còn lại,
         seed cố định để tái lập được. Đợt này cho biết tỉ lệ khoản quan sát được ở phần "không chọn".
Mỗi khoản kèm NGUYÊN VĂN các khoản được dẫn chiếu (dẫn chiếu cả Điều → ghép mọi khoản của Điều đó).
Phiếu không chứa đáp án hay ý kiến của trợ lý.

Chạy:  python scripts/export_cap_candidates.py [--sample 60] [--seed 2018]
Đọc:   data/processed/cap_chunks.json, data/processed/bpic2018_process_graph.json
Ghi:   docs/CAP_ITEM_CANDIDATES.md, docs/CAP_VOCABULARY.md, data/review/cap_item_candidates.json
"""

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHUNKS_PATH = PROJECT_ROOT / "data" / "processed" / "cap_chunks.json"
ANNEX_PATH = PROJECT_ROOT / "data" / "processed" / "cap_annexes.json"
PROCESS_GRAPH_PATH = PROJECT_ROOT / "data" / "processed" / "bpic2018_process_graph.json"
MD_PATH = PROJECT_ROOT / "docs" / "CAP_ITEM_CANDIDATES.md"
VOCAB_PATH = PROJECT_ROOT / "docs" / "CAP_VOCABULARY.md"
JSON_PATH = PROJECT_ROOT / "data" / "review" / "cap_item_candidates.json"

DEFAULT_SAMPLE = 60
DEFAULT_SEED = 2018
DOC_ORDER = ("R1306", "R1307", "R640", "R809")
DOC_NAME = {
    "R1306": "Regulation (EU) No 1306/2013",
    "R1307": "Regulation (EU) No 1307/2013",
    "R640": "Delegated Regulation (EU) No 640/2014",
    "R809": "Implementing Regulation (EU) No 809/2014",
}
_NODE = re.compile(r"^(?P<doc>[^:]+):Art(?P<art>\d+)(?:\((?P<para>\d+)\))?$")


# ------------------------------------------------------------------------------ helpers


def _order_key(node_id: str) -> Tuple[int, str, int, int]:
    m = _NODE.match(node_id)
    if not m:
        return (len(DOC_ORDER), node_id, 0, 0)
    doc = m.group("doc")
    rank = DOC_ORDER.index(doc) if doc in DOC_ORDER else len(DOC_ORDER)
    return (rank, doc, int(m.group("art")), int(m.group("para") or 0))


def _article_of(node_id: str) -> str:
    m = _NODE.match(node_id)
    return f"{m.group('doc')}:Art{m.group('art')}" if m else node_id


def is_cross_document(chunk: Mapping[str, Any]) -> bool:
    """Có dẫn chiếu sang một Quy định khác TRONG bộ (không tính văn bản ngoài bộ, dẫn chiếu nội bộ)."""
    return any(r["kind"] == "external" and r["in_scope"] for r in chunk.get("refs", []))


def referenced_texts(chunk: Mapping[str, Any], index: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Nguyên văn đích dẫn chiếu. found=False: văn bản ngoài bộ, hoặc trong bộ nhưng không tách được."""
    out = []
    for ref in chunk.get("refs", []):
        target = ref["target"]
        text = ""
        if ref["in_scope"]:
            if target in index:
                text = index[target]["text"]
            else:
                article = _article_of(target)
                parts = sorted((nid for nid in index if _article_of(nid) == article), key=_order_key)
                text = "\n\n".join(index[p]["text"] for p in parts)
        out.append({"target": target, "kind": ref["kind"], "in_scope": bool(ref["in_scope"]),
                    "found": bool(text), "text": text})
    return out


# ---------------------------------------------------------------------------- selection


def allocate(sizes: Mapping[str, int], total: int) -> Dict[str, int]:
    """Chia `total` theo tỉ lệ `sizes` (phương pháp phần dư lớn nhất), không vượt quá số có sẵn."""
    population = sum(sizes.values())
    if total >= population:
        return dict(sizes)
    quotas = {k: total * n / population for k, n in sizes.items()}
    alloc = {k: int(q) for k, q in quotas.items()}
    by_remainder = sorted(sizes, key=lambda k: (-(quotas[k] - alloc[k]), k))
    i = 0
    while sum(alloc.values()) < total:
        k = by_remainder[i % len(by_remainder)]
        if alloc[k] < sizes[k]:
            alloc[k] += 1
        i += 1
    return alloc


def select_rounds(
    chunks: Sequence[Mapping[str, Any]], sample: int = DEFAULT_SAMPLE, seed: int = DEFAULT_SEED
) -> Tuple[List[Mapping[str, Any]], List[Mapping[str, Any]]]:
    round1 = sorted((c for c in chunks if is_cross_document(c)), key=lambda c: _order_key(c["node_id"]))
    rest: Dict[str, List[Mapping[str, Any]]] = {}
    for c in sorted((c for c in chunks if not is_cross_document(c)), key=lambda c: _order_key(c["node_id"])):
        rest.setdefault(c["doc_id"], []).append(c)
    rng = random.Random(seed)
    round2: List[Mapping[str, Any]] = []
    for doc, n in allocate({d: len(cs) for d, cs in rest.items()}, sample).items():
        round2.extend(rng.sample(rest[doc], n))
    return round1, sorted(round2, key=lambda c: _order_key(c["node_id"]))


# ----------------------------------------------------------------------------- markdown

HEADER = """# Phiếu gán nhãn Phần B — bộ CAP (BPIC2018), {n} khoản

> Sinh tự động bởi `scripts/export_cap_candidates.py` từ `data/processed/cap_chunks.json`. Nguyên văn luật
> chép từ dữ liệu đã tách (PDF EUR-Lex). Phiếu **không** chứa đáp án hay ý kiến nào.
> Đọc **docs/HUONG_DAN_GAN_NHAN_CAP.md** trước khi làm; tên activity / thuộc tính tra ở **docs/CAP_VOCABULARY.md**.

| Đợt | Cách chọn | Số khoản |
|---|---|---|
| **Đợt 1** | Mọi khoản có dẫn chiếu sang một Quy định khác trong bộ 4 văn bản | {n1} |
| **Đợt 2** | Ngẫu nhiên phân tầng theo văn bản từ {rest} khoản còn lại (seed = {seed}): {alloc} | {n2} |

Văn bản: {docs}.
Không khoản nào bị loại trước vì phạm vi hay vì thiếu từ *shall/must* — bạn tự đánh giá.
Cờ "có con số" được phát hiện tự động, có thể sót.

## Mẫu trả lời

Chép khối dưới đây vào một file `.txt`, điền vào chỗ `___`, rồi gửi lại. Mỗi khoản một dòng.

```
{answer_lines}
```

---
"""


def _answer_line(node_id: str) -> str:
    return (f"{node_id}: **Quan sát được:** ___ · **Ràng buộc mới:** ___ · "
            f"**Cần điều tham chiếu:** ___ · **Độ chắc chắn:** ___ · **Lý do:** ___")


def _quote(text: str) -> str:
    return "> " + text.replace("\n\n", "\n>\n> ")


def _ref_block(ref: Mapping[str, Any]) -> str:
    if not ref["in_scope"]:
        return f"\n- Dẫn chiếu ra ngoài bộ 4 văn bản: **{ref['target']}** (không kèm nguyên văn — tra EUR-Lex nếu cần)\n"
    if not ref["found"]:
        return f"\n- Dẫn chiếu **{ref['target']}**: không tách được nguyên văn từ PDF — tra EUR-Lex nếu cần\n"
    where = "văn bản khác" if ref["kind"] == "external" else "cùng văn bản"
    return (f"\n<details><summary>Khoản được dẫn chiếu: <b>{ref['target']}</b> ({where})</summary>\n\n"
            f"{_quote(ref['text'])}\n\n</details>\n")


def _section(chunk: Mapping[str, Any], index: Mapping[str, Mapping[str, Any]]) -> str:
    refs = referenced_texts(chunk, index)
    flags = [DOC_NAME.get(chunk["doc_id"], chunk["doc_id"])] + (["có con số"] if chunk["has_numeric_bound"] else [])
    return (f"### {chunk['node_id']} · {chunk['article_title']} · {' · '.join(flags)}\n\n"
            f"{_quote(chunk['text'])}\n{''.join(_ref_block(r) for r in refs)}\n---\n")


def build_markdown(
    round1: Sequence[Mapping[str, Any]], round2: Sequence[Mapping[str, Any]],
    index: Mapping[str, Mapping[str, Any]], seed: int,
    text_index: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> str:
    """index = các khoản (tính số khoản còn lại); text_index = khoản + Phụ lục (tra nguyên văn dẫn chiếu)."""
    lookup = text_index if text_index is not None else index
    alloc: Dict[str, int] = {}
    for c in round2:
        alloc[c["doc_id"]] = alloc.get(c["doc_id"], 0) + 1
    header = HEADER.format(
        n=len(round1) + len(round2), n1=len(round1), n2=len(round2), seed=seed,
        rest=len(index) - len(round1),
        alloc=", ".join(f"{d} {n}" for d, n in sorted(alloc.items(), key=lambda kv: _order_key(kv[0] + ":Art0"))),
        docs="; ".join(f"**{k}** = {v}" for k, v in DOC_NAME.items()),
        answer_lines="\n".join(_answer_line(c["node_id"]) for c in [*round1, *round2]),
    )
    body = (f"\n## Đợt 1 — dẫn chiếu sang văn bản khác ({len(round1)} khoản)\n\n"
            + "\n".join(_section(c, lookup) for c in round1)
            + f"\n## Đợt 2 — mẫu ngẫu nhiên ({len(round2)} khoản)\n\n"
            + "\n".join(_section(c, lookup) for c in round2))
    return header + body


def _attribute_range(p: Mapping[str, Any]) -> str:
    if p.get("type") in ("number", "datetime"):
        return f"{p['min']} – {p['max']}"
    if "values" in p:
        return ", ".join(str(v) for v in p["values"])
    return f"{p.get('distinct_count', '?')} giá trị khác nhau"


def build_vocabulary_markdown(graph: Mapping[str, Any]) -> str:
    """Bảng activity (doctype / subprocess / activity) và thuộc tính của log BPIC2018, lấy từ tầng Tiến trình."""
    acts = sorted((n["props"] for n in graph["nodes"] if n["label"] == "Activity"), key=lambda p: p["name"])
    attrs = sorted((n["props"] for n in graph["nodes"] if n["label"] == "Attribute"),
                   key=lambda p: (p.get("level") != "case", p["name"]))
    lines = [
        "# Từ vựng log BPIC2018 (dùng khi viết ràng buộc cho bộ CAP)",
        "",
        "> Sinh tự động bởi `scripts/export_cap_candidates.py` từ `data/processed/bpic2018_process_graph.json`.",
        "> Tên activity = `loại giấy tờ / tiến trình con / hành động`. Viết ràng buộc bằng **đúng** tên trong bảng.",
        "",
        f"## Activity ({len(acts)})",
        "",
        "| Activity | Số hồ sơ | Tỉ lệ hồ sơ | Số event |",
        "|---|---:|---:|---:|",
        *(f"| `{p['name']}` | {p['case_count']} | {p['case_ratio']:.2%} | {p['event_count']} |" for p in acts),
        "",
        f"## Thuộc tính ({len(attrs)}) — `case:` = thuộc tính hồ sơ, còn lại = thuộc tính event",
        "",
        "| Thuộc tính | Kiểu | Giá trị / khoảng |",
        "|---|---|---|",
        *(f"| `{p['name']}` | {p.get('type', '?')} | {_attribute_range(p)} |" for p in attrs),
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------------- main


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(list(argv))

    chunks = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    index = {c["node_id"]: c for c in chunks}
    # Phụ lục (kiểm toán đợt 2, F-ANNEX): chỉ để tra nguyên văn dẫn chiếu 'Annex X', không vào phiếu / mẫu ngẫu nhiên
    annexes = json.loads(ANNEX_PATH.read_text(encoding="utf-8")) if ANNEX_PATH.exists() else []
    text_index = {**index, **{a["node_id"]: a for a in annexes}}
    round1, round2 = select_rounds(chunks, args.sample, args.seed)
    MD_PATH.write_text(build_markdown(round1, round2, index, args.seed, text_index), encoding="utf-8")
    records = [{**c, "round": r, "referenced": referenced_texts(c, text_index)}
               for r, cs in ((1, round1), (2, round2)) for c in cs]
    JSON_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    graph = json.loads(PROCESS_GRAPH_PATH.read_text(encoding="utf-8"))
    VOCAB_PATH.write_text(build_vocabulary_markdown(graph), encoding="utf-8")

    sys.stdout.reconfigure(encoding="utf-8")
    count = lambda cs: {d: sum(c["doc_id"] == d for c in cs) for d in DOC_ORDER}  # noqa: E731
    missing = sum(not r["found"] for rec in records for r in rec["referenced"] if r["in_scope"])
    sys.stdout.write(
        f"Đã ghi {MD_PATH.relative_to(PROJECT_ROOT)}, {VOCAB_PATH.relative_to(PROJECT_ROOT)}, "
        f"{JSON_PATH.relative_to(PROJECT_ROOT)}\n"
        f"Đợt 1: {len(round1)} {count(round1)}\nĐợt 2: {len(round2)} {count(round2)} (seed={args.seed})\n"
        f"Dẫn chiếu trong bộ không tìm được nguyên văn: {missing}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
