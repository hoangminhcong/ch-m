"""
TN2 bước 2 (tiếp) – Thống nhất nhãn gold từ phiếu của người gán nhãn + 3 điều chỉnh đã thống nhất.

Nhãn gốc của người gán được GIỮ NGUYÊN (trường `annotator`); kết quả sau điều chỉnh nằm ở
`final_decision` / `final_constraint`, mỗi điều chỉnh ghi lý do trong `adjustments`:
  A1 – Gộp câu trùng: nhiều rule cùng (khoản luật, ràng buộc) chỉ thành MỘT câu đề.
  A2 – "Gửi thông tin cho khách" phải gồm cả hai kênh O_Sent (dùng một kênh báo oan 190 hồ sơ).
  A3 – Câu bẫy xét CHÍNH ràng buộc trong gold; nghĩa vụ hợp lệ khác của khoản luật thuộc câu khác.
Khi có thêm phiếu Phần B (61 khoản):
  A4 – Người gán tự mâu thuẫn giữa Phần A và Phần B về "quan sát được" → lấy câu có độ chắc chắn cao hơn.
  A5 – Bỏ ràng buộc có con số không xuất hiện trong văn bản khoản luật (quy tắc mục 7 của hướng dẫn).
  A6 – Khoản chỉ có ở Phần B được thêm thành câu đề; gắn điều kiện phạm vi mà chính khoản luật nêu
       (SCOPE_CONDITIONS, mỗi mục kèm lý do).

Chạy:  python scripts/adjudicate_gold.py
Đọc:   data/review/labels_annotator_B.txt, labels_annotator_B_partB.txt, item_candidates.json
Ghi:   data/review/gold_adjudicated.json
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LABELS_PATH = PROJECT_ROOT / "data" / "review" / "labels_annotator_B.txt"
PARTB_PATH = PROJECT_ROOT / "data" / "review" / "labels_annotator_B_partB.txt"
CANDIDATES_PATH = PROJECT_ROOT / "data" / "review" / "item_candidates.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "review" / "gold_adjudicated.json"

CONSTRAINT_MARKER = "Ràng buộc mới:"
O_SENT_MAIL = "O_Sent (mail and online)"
O_SENT_ANY = "{O_Sent (mail and online) | O_Sent (online only)}"
_LINE = re.compile(
    r"^(R\d+):\s*\*\*Quyết định:\*\*\s*(\S+)\s*·\s*\*\*Độ chắc chắn:\*\*\s*(\S+)\s*·\s*\*\*Lý do:\*\*\s*(.*)$",
    re.MULTILINE,
)
ADJ_A1 = "A1: gộp với {others} — cùng khoản luật, cùng ràng buộc"
ADJ_A2 = "A2: O_Sent gồm cả hai kênh (mail and online | online only); một kênh báo oan 190 hồ sơ"
ADJ_A3 = "A3: câu bẫy xét chính ràng buộc trong gold (không có căn cứ) → GIỮ; nghĩa vụ hợp lệ khác thuộc câu khác"
ADJ_A4 = ("A4: tự mâu thuẫn — Phần A: quan sát được (độ chắc chắn {a}); Phần B: không quan sát được "
          "(độ chắc chắn {b}) → theo Phần B: BẪY")
ADJ_A5 = "A5: con số {nums} không có trong văn bản {para} (mục 7: con số phải lấy từ luật) → bỏ"
ADJ_A6 = "A6: khoản chỉ có ở Phần B; thêm điều kiện phạm vi: {why}"

_PARTB_LINE = re.compile(
    r"^(Art[\w()]+):\s*\*\*Quan sát được:\*\*\s*(\S+)\s*·\s*\*\*Ràng buộc mới:\*\*\s*(.*?)\s*·\s*"
    r"\*\*Cần điều tham chiếu:\*\*\s*(.*?)\s*·\s*\*\*Độ chắc chắn:\*\*\s*(.*?)\s*·\s*\*\*Lý do:\*\*\s*(.*)$",
    re.MULTILINE,
)
_NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*(?![\w])")
CONFIDENCE_RANK = {"Thấp": 0, "TB": 1, "Trung bình": 1, "Cao": 2}

# Điều kiện phạm vi do CHÍNH khoản luật nêu (không phải do người gán tự đặt ra).
SCOPE_CONDITIONS: Dict[str, Tuple[str, str]] = {
    "Art8(2)": (
        'A.case:ApplicationType == "Limit raise"',
        "Điều 8(2) chỉ áp dụng khi thay đổi tổng số tiền tín dụng sau khi đã ký; log ghi trường hợp này là "
        "case:ApplicationType = Limit raise (người gán nêu trong lý do). 'Significant increase' không có "
        "ngưỡng trong luật nên áp cho mọi hồ sơ Limit raise.",
    ),
}


def extract_constraint(text: str) -> Optional[str]:
    """Lấy ràng buộc sau 'Ràng buộc mới:', đếm ngoặc cân bằng (tên activity có thể chứa ngoặc)."""
    start = text.find(CONSTRAINT_MARKER)
    if start < 0:
        return None
    body = text[start + len(CONSTRAINT_MARKER):].lstrip()
    open_at = body.find("(")
    if open_at < 0:
        return None
    depth = 0
    for i, ch in enumerate(body[open_at:], start=open_at):
        depth += (ch == "(") - (ch == ")")
        if depth == 0:
            return body[: i + 1].strip()
    return None


def parse_labels(text: str) -> Dict[str, Dict[str, Any]]:
    """Đọc phiếu dạng 'Rxx: **Quyết định:** … · **Độ chắc chắn:** … · **Lý do:** …'."""
    return {
        m.group(1): {
            "decision": m.group(2),
            "confidence": m.group(3),
            "constraint": extract_constraint(m.group(4)),
            "reason": m.group(4).strip(),
        }
        for m in _LINE.finditer(text)
    }


def parse_partb_labels(text: str) -> Dict[str, Dict[str, Any]]:
    """Đọc phiếu Phần B 'ArtX(n): **Quan sát được:** … · **Ràng buộc mới:** … · … · **Lý do:** …'."""
    out = {}
    for m in _PARTB_LINE.finditer(text):
        raw = m.group(3).strip()
        constraints = [] if raw in {"", "—", "-"} else [c.strip() for c in raw.split(";") if c.strip()]
        out[m.group(1)] = {"observable": m.group(2) == "Có", "constraints": constraints,
                           "needs_ref": m.group(4).strip(), "confidence": m.group(5).strip(),
                           "reason": m.group(6).strip()}
    return out


def paragraph_key(article_id: str) -> str:
    """'Article 5(1)' → 'Art5(1)' (khoá dùng trong phiếu Phần B)."""
    return re.sub(r"^Article\s*", "Art", article_id.strip())


def article_id_of(key: str) -> str:
    """'Art5(1)' → 'Article 5(1)'."""
    return re.sub(r"^Art", "Article ", key)


def numbers_not_in_text(constraint: str, text: str) -> List[str]:
    """Các con số trong ràng buộc không xuất hiện (như một số đứng riêng) trong văn bản luật."""
    in_text = set(_NUMBER.findall(text))
    return [n for n in _NUMBER.findall(constraint) if n not in in_text]


def _rank(confidence: str) -> int:
    return CONFIDENCE_RANK.get(confidence, CONFIDENCE_RANK["TB"])


def _apply_a4(rule: Dict[str, Any], label: Mapping[str, Any], b: Optional[Mapping[str, Any]]) -> None:
    """A4: Phần A nói quan sát được, Phần B nói không và chắc chắn hơn → câu bẫy."""
    if b is None or rule["kind"] != "positive" or b["observable"]:
        return
    if _rank(b["confidence"]) <= _rank(label["confidence"]):
        return
    rule.update(final_decision="BẪY", final_constraint=None, kind="trap")
    rule["adjustments"].append(ADJ_A4.format(a=label["confidence"], b=b["confidence"]))


def _both_channels(constraint: str) -> str:
    return constraint if "online only" in constraint else constraint.replace(O_SENT_MAIL, O_SENT_ANY)


def _partb_items(
    partb: Mapping[str, Mapping[str, Any]], covered: set, texts: Mapping[str, str]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """A5 + A6: câu mới từ các khoản 'quan sát được' ở Phần B. Trả về (câu mới, ràng buộc bị bỏ)."""
    items, dropped = [], []
    for key in sorted(k for k, v in partb.items() if v["observable"]):
        for constraint in map(_both_channels, partb[key]["constraints"]):
            bad = numbers_not_in_text(constraint, texts.get(key, ""))
            if bad:
                dropped.append({"paragraph": key, "constraint": constraint,
                                "reason": ADJ_A5.format(nums=", ".join(bad), para=key)})
                continue
            adjustments = []
            if key in SCOPE_CONDITIONS:
                cond, why = SCOPE_CONDITIONS[key]
                constraint = f"{constraint} | {cond}"
                adjustments.append(ADJ_A6.format(why=why))
            if (article_id_of(key), constraint) in covered:
                continue
            items.append({"kind": "positive", "article_id": article_id_of(key), "constraint": constraint,
                          "source_rules": [f"PartB:{key}"], "confidence": partb[key]["confidence"],
                          "adjustments": adjustments})
    return items, dropped


def _decide(label: Mapping[str, Any], meta: Mapping[str, Any]) -> Dict[str, Any]:
    """Áp A2, A3 cho một rule. Trả về quyết định cuối, ràng buộc cuối, loại câu, các điều chỉnh."""
    decision, constraint, adjustments = label["decision"], label["constraint"], []
    if meta.get("is_trap") and decision == "SỬA" and constraint is None:
        decision = "GIỮ"
        adjustments.append(ADJ_A3)
    if constraint and O_SENT_MAIL in constraint and "online only" not in constraint:
        constraint = constraint.replace(O_SENT_MAIL, O_SENT_ANY)
        adjustments.append(ADJ_A2)
    if decision == "LOẠI":
        kind = "excluded"
    elif decision == "BẪY" or (decision == "GIỮ" and meta.get("is_trap")):
        kind = "trap"
    else:
        kind = "positive"
        constraint = constraint or meta.get("gold")
    return {"final_decision": decision, "final_constraint": constraint, "kind": kind,
            "adjustments": adjustments}


def _merge_positives(rules: Dict[str, Dict[str, Any]], metas: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """A1: gộp các rule cùng (khoản luật, ràng buộc) thành một câu đề."""
    groups: Dict[tuple, List[str]] = {}
    for rid, r in rules.items():
        if r["kind"] == "positive":
            groups.setdefault((metas[rid]["article_id"], r["final_constraint"]), []).append(rid)
    items = []
    for n, ((article, constraint), rids) in enumerate(sorted(groups.items()), start=1):
        rids = sorted(rids)
        for rid in rids:
            others = [o for o in rids if o != rid]
            if others:
                rules[rid]["adjustments"].append(ADJ_A1.format(others=", ".join(others)))
        items.append({"item_id": f"P{n:02d}", "kind": "positive", "article_id": article,
                      "constraint": constraint, "source_rules": rids})
    return items


def adjudicate(
    labels: Mapping[str, Mapping[str, Any]],
    metas: Mapping[str, Mapping[str, Any]],
    partb: Optional[Mapping[str, Mapping[str, Any]]] = None,
    paragraph_texts: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Nhãn người gán + điều chỉnh A1–A3 (thêm A4–A6 nếu có phiếu Phần B). Thiếu nhãn → KeyError."""
    missing = sorted(set(metas) - set(labels))
    if missing:
        raise KeyError(f"Thiếu nhãn cho: {missing}")
    rules = {rid: {"annotator": dict(labels[rid]), **_decide(labels[rid], metas[rid])} for rid in sorted(metas)}
    if partb is not None:
        for rid, rule in rules.items():
            _apply_a4(rule, labels[rid], partb.get(paragraph_key(metas[rid]["article_id"])))
    items = _merge_positives(rules, metas)
    dropped: List[Dict[str, Any]] = []
    if partb is not None:
        covered = {(i["article_id"], i["constraint"]) for i in items}
        new_items, dropped = _partb_items(partb, covered, paragraph_texts or {})
        items += [{"item_id": f"P{len(items) + n:02d}", **i} for n, i in enumerate(new_items, start=1)]
    items += [
        {"item_id": f"T-{rid}", "kind": "trap", "article_id": metas[rid]["article_id"],
         "constraint": None, "source_rules": [rid]}
        for rid, r in rules.items() if r["kind"] == "trap"
    ]
    excluded = [rid for rid, r in rules.items() if r["kind"] == "excluded"]
    return {"rules": rules, "items": items, "excluded": excluded, "dropped_constraints": dropped,
            "summary": dict(Counter(i["kind"] for i in items))}


def main() -> int:
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.export_gold_review import format_gold
    from src.evaluation.benchmark_builder import BENCHMARK_RULES

    metas = {r["rule_id"]: {"article_id": r["article_id"], "is_trap": bool(r["is_trap"]),
                            "gold": format_gold(r).replace("`", "")} for r in BENCHMARK_RULES}
    labels = parse_labels(LABELS_PATH.read_text(encoding="utf-8"))
    partb = parse_partb_labels(PARTB_PATH.read_text(encoding="utf-8"))
    texts = {c["node_id"]: c["text"] for c in json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))}
    result = adjudicate(labels, metas, partb=partb, paragraph_texts=texts)
    result["_about"] = (__doc__.strip().splitlines()[0]
                        + f" Nguồn nhãn: {LABELS_PATH.name}, {PARTB_PATH.name} ({len(partb)} khoản).")
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(f"Đã ghi {OUTPUT_PATH.relative_to(PROJECT_ROOT)}\nTổng hợp câu đề: {result['summary']}, "
                     f"loại bỏ: {result['excluded']}\n\nCâu thường (sau gộp):\n")
    for item in (i for i in result["items"] if i["kind"] == "positive"):
        sys.stdout.write(f"  {item['item_id']} {item['article_id']:<14} {item['constraint']}  ← {item['source_rules']}\n")
    sys.stdout.write("\nĐiều chỉnh đã áp:\n")
    for rid, r in result["rules"].items():
        for adj in r["adjustments"]:
            sys.stdout.write(f"  {rid}: {adj}\n")
    for item in result["items"]:
        for adj in item.get("adjustments", []):
            sys.stdout.write(f"  {item['item_id']}: {adj}\n")
    for d in result["dropped_constraints"]:
        sys.stdout.write(f"  {d['paragraph']}: {d['constraint']}\n      {d['reason']}\n")
    return 0


if __name__ == "__main__":
    # Bộ BPIC2017 đang tạm vô hiệu (src/datasets.py); mở lại: $env:NSAI_ENABLE_BPIC2017 = "1"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.datasets import require_bpic2017
    require_bpic2017(__file__)
    sys.exit(main())
