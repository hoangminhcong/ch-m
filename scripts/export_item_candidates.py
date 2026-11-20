"""
TN2 bước 3 – Sinh phiếu SOẠN CÂU MỚI cho bộ đề: rà lại toàn bộ Directive + ứng viên Tier 4.

Lấy mọi khoản luật có từ ngữ nghĩa vụ (shall / must) ngoài Điều 1–3 (đối tượng, phạm vi, định nghĩa).
Khoản có tham chiếu sang điều khác xếp lên đầu và hiện kèm NGUYÊN VĂN khoản được tham chiếu (lấy từ
cạnh REFERS_TO của đồ thị pháp lý, TN1). Phiếu không chứa gold hay ý kiến của trợ lý.

Người gán nhãn trả lời cho từng khoản: quan sát được trên log không / ràng buộc mới /
có cần đọc điều được tham chiếu không (Có → câu Tier 4). Xem docs/HUONG_DAN_GAN_NHAN.md, Phần B.

Chạy:  python scripts/export_item_candidates.py
Ra:    docs/ITEM_CANDIDATES.md, data/review/item_candidates.json
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = PROJECT_ROOT / "data" / "processed" / "legal_graph.json"
MD_PATH = PROJECT_ROOT / "docs" / "ITEM_CANDIDATES.md"
JSON_PATH = PROJECT_ROOT / "data" / "review" / "item_candidates.json"

DEFAULT_EXCLUDED_ARTICLES = frozenset({1, 2, 3})  # đối tượng, phạm vi, định nghĩa
GROUP_ORDER = {"cross": 0, "intra": 1, "none": 2}
GROUP_LABEL = {"cross": "tham chiếu sang điều khác", "intra": "tham chiếu trong cùng điều", "none": "không tham chiếu"}

_OBLIGATION = re.compile(r"\b(shall|must)\b", re.IGNORECASE)
_NOT_APPLY = re.compile(r"\bshall\s+not\s+apply\b", re.IGNORECASE)
_UNIT = r"(?:calendar\s+|working\s+)?(?:days?|weeks?|months?|years?|hours?)\b"
_NUMBER_WORD = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fourteen|thirty)"
_NUMERIC = [
    re.compile(rf"\b\d+\s*{_UNIT}", re.IGNORECASE),
    re.compile(rf"\b{_NUMBER_WORD}\s+{_UNIT}", re.IGNORECASE),
    re.compile(r"\bEUR\s*\d", re.IGNORECASE),
    re.compile(r"\d\s*%"),
]
_NODE_ID = re.compile(r"^Art(\d+)(?:\((\d+)\))?$")


# ---------------------------------------------------------------------------- heuristics


def is_obligation(text: str) -> bool:
    """Có từ ngữ nghĩa vụ (shall/must), không tính cụm 'shall not apply' (điều khoản phạm vi)."""
    return bool(_OBLIGATION.search(_NOT_APPLY.sub("", text)))


def has_numeric_bound(text: str) -> bool:
    """Có con số / thời hạn / số tiền / phần trăm (tự động, có thể sót)."""
    return any(p.search(text) for p in _NUMERIC)


def _order_key(node_id: str) -> Tuple[int, int]:
    match = _NODE_ID.match(node_id)
    return (int(match.group(1)), int(match.group(2) or 0)) if match else (10**6, 0)


def _article_of(node_id: str) -> Optional[int]:
    match = _NODE_ID.match(node_id)
    return int(match.group(1)) if match else None


# ------------------------------------------------------------------------- graph access


def referenced_texts(graph: Mapping[str, Any], source: str) -> List[Dict[str, Any]]:
    """Văn bản các khoản được `source` tham chiếu. Tham chiếu cả Điều → ghép mọi khoản của Điều đó."""
    nodes = {n["id"]: n for n in graph["nodes"]}
    targets = [e["target"] for e in graph["edges"] if e["type"] == "REFERS_TO" and e["source"] == source]
    refs = []
    for target in targets:
        props = nodes.get(target, {}).get("props", {})
        in_scope = bool(props.get("in_scope", True))
        if not in_scope:
            text = "(Điều này nằm ngoài phần văn bản đã parse — tra EUR-Lex nếu cần)"
        elif props.get("text"):
            text = props["text"]
        else:
            paragraphs = sorted((i for i in nodes if i.startswith(f"{target}(")), key=_order_key)
            text = "\n\n".join(nodes[p]["props"].get("text", "") for p in paragraphs)
        refs.append({"target": target, "in_scope": in_scope, "text": text})
    return refs


def _ref_group(node_id: str, refs: Iterable[Mapping[str, Any]]) -> str:
    in_scope = [r for r in refs if r["in_scope"]]
    if not in_scope:
        return "none"
    own = _article_of(node_id)
    return "cross" if any(_article_of(r["target"]) != own for r in in_scope) else "intra"


def build_candidates(
    graph: Mapping[str, Any],
    used: Mapping[str, List[str]],
    excluded_articles: Set[int] = DEFAULT_EXCLUDED_ARTICLES,
) -> List[Dict[str, Any]]:
    """Mọi khoản nghĩa vụ ngoài các Điều bị loại; khoản tham chiếu chéo xếp trước."""
    titles = {n["id"]: n["props"].get("title", "") for n in graph["nodes"] if n["label"] == "Article"}
    candidates = []
    for node in graph["nodes"]:
        text = node["props"].get("text")
        article = _article_of(node["id"])
        if not text or article is None or article in excluded_articles or not is_obligation(text):
            continue
        refs = referenced_texts(graph, node["id"])
        candidates.append({
            "node_id": node["id"],
            "article_title": titles.get(f"Art{article}", ""),
            "text": text,
            "has_numeric": has_numeric_bound(text),
            "refs": refs,
            "ref_group": _ref_group(node["id"], refs),
            "used_by": list(used.get(node["id"], [])),
        })
    return sorted(candidates, key=lambda c: (GROUP_ORDER[c["ref_group"]], _order_key(c["node_id"])))


# ------------------------------------------------------------------------------ markdown

HEADER = """# Phiếu soạn câu mới cho bộ đề — {n} khoản luật (TN2, bước 3)

> Sinh tự động bởi `scripts/export_item_candidates.py` từ đồ thị pháp lý (TN1). Nguyên văn luật chép từ dữ liệu.
> Phiếu **không** chứa đáp án hay ý kiến nào. Đọc **docs/HUONG_DAN_GAN_NHAN.md — Phần B** trước khi làm.

Thứ tự: khoản có **tham chiếu sang điều khác** ({cross}) → **tham chiếu trong cùng điều** ({intra}) →
**không tham chiếu** ({none}). Cờ "có con số" được phát hiện tự động, có thể sót.

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


def _section(c: Mapping[str, Any]) -> str:
    flags = [GROUP_LABEL[c["ref_group"]]] + (["có con số"] if c["has_numeric"] else [])
    used = f"\n_Khoản này đã được dùng trong bộ đề cũ ({', '.join(c['used_by'])})._\n" if c["used_by"] else ""
    refs = "".join(
        f"\n<details><summary>Khoản được tham chiếu: <b>{r['target']}</b></summary>\n\n> "
        + r["text"].replace("\n\n", "\n>\n> ") + "\n\n</details>\n"
        for r in c["refs"]
    )
    return (f"## {c['node_id']} · {c['article_title']} · {' · '.join(flags)}\n{used}\n"
            f"> {c['text']}\n{refs}\n---\n")


def build_markdown(candidates: List[Mapping[str, Any]]) -> str:
    counts = {g: sum(1 for c in candidates if c["ref_group"] == g) for g in GROUP_ORDER}
    header = HEADER.format(
        n=len(candidates), **counts,
        answer_lines="\n".join(_answer_line(c["node_id"]) for c in candidates),
    )
    return header + "\n" + "\n".join(_section(c) for c in candidates)


# ---------------------------------------------------------------------------------- main


def _used_paragraphs() -> Dict[str, List[str]]:
    from src.evaluation.benchmark_builder import BENCHMARK_RULES
    from src.kg.legal_graph_builder import paragraph_node_id, parse_paragraph_id

    used: Dict[str, List[str]] = {}
    for rule in BENCHMARK_RULES:
        try:
            node_id = paragraph_node_id(*parse_paragraph_id(rule["article_id"]))
        except ValueError:  # VD 'Annex I(II)' không phải Article
            continue
        used.setdefault(node_id, []).append(rule["rule_id"])
    return used


def main() -> int:
    sys.path.insert(0, str(PROJECT_ROOT))
    with open(GRAPH_PATH, encoding="utf-8") as f:
        graph = json.load(f)
    candidates = build_candidates(graph, _used_paragraphs())
    MD_PATH.write_text(build_markdown(candidates), encoding="utf-8")
    JSON_PATH.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    groups = {g: sum(1 for c in candidates if c["ref_group"] == g) for g in GROUP_ORDER}
    sys.stdout.write(f"Đã ghi {MD_PATH.relative_to(PROJECT_ROOT)} và {JSON_PATH.relative_to(PROJECT_ROOT)}\n"
                     f"{len(candidates)} khoản nghĩa vụ: {groups}, có con số: "
                     f"{sum(c['has_numeric'] for c in candidates)}\n")
    return 0


if __name__ == "__main__":
    # Bộ BPIC2017 đang tạm vô hiệu (src/datasets.py); mở lại: $env:NSAI_ENABLE_BPIC2017 = "1"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.datasets import require_bpic2017
    require_bpic2017(__file__)
    sys.exit(main())
