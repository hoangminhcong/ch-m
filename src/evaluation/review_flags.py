"""
Nhãn REVIEW (M9; đăng ký trước B7, docs/V2_DANG_KY_TRUOC.md) — mô tả, KHÔNG đổi đầu ra, KHÔNG đổi điểm.

Mỗi luật (outcome RULE) nhận 5 tín hiệu cố định; mức nghi ngờ = số tín hiệu; REVIEW = mức ≥ 1.
  S1 vi phạm hàng loạt trên log     tỉ lệ hồ sơ kích hoạt vi phạm > MASS_VIOLATION_THRESHOLD (0,20, như Z)
  S2 không có hỗ trợ từ KG          loại giấy tờ của activity ⊄ loại giấy tờ của khoản qua MAPS_TO (quy tắc N4)
  S3 mâu thuẫn trong tập            CONFLICT / CONFLICT_IF_ACTIVATED với luật khác cùng cấu hình
  S4 dẫn chứng không có căn cứ      proof trace: evidence level 'unsupported'
  S5 rỗng mà vẫn được chấp nhận     grounding.vacuous = true
Bảng giữ lại — rủi ro (selective prediction): ngưỡng k = 1..5, giữ luật có mức < k; theo gold đếm luật sai trên bẫy
và luật đúng (EQ) trên positive trong số giữ lại. Không chọn ngưỡng "tốt nhất".
"""

from typing import Any, Dict, FrozenSet, List, Mapping, Optional

from src.evaluation.cap_scoring import is_correct, score_clause
from src.symbolic.norm_frame import kg_support
from src.symbolic.process_checks import MASS_VIOLATION_THRESHOLD

SIGNALS = ("S1_mass_violation", "S2_no_kg_support", "S3_set_conflict", "S4_evidence_unsupported",
           "S5_vacuous_accepted")
CONFLICT_KINDS = ("CONFLICT", "CONFLICT_IF_ACTIVATED")
MAX_LEVEL = len(SIGNALS)


def rule_signals(trace: Mapping[str, Any], ast: Mapping[str, Any], mass: Optional[Mapping[str, Any]],
                 clause_doctypes: Optional[FrozenSet[str]]) -> Dict[str, Any]:
    """trace = proof_trace.trace_record của luật; mass = MassViolationChecker.assess (None = không có log);
    clause_doctypes = loại giấy tờ của khoản qua MAPS_TO (None = chưa có ontology đã duyệt → S2 không xét)."""
    support = kg_support(ast, clause_doctypes) if clause_doctypes is not None else None
    conflicts = sorted({f["b"] if f.get("a") == trace["clause"] else f["a"]
                        for f in trace.get("set_findings", []) if f.get("kind") in CONFLICT_KINDS})
    signals = {
        "S1_mass_violation": bool(mass) and mass.get("activated", 0) > 0
        and mass.get("ratio", 0.0) > MASS_VIOLATION_THRESHOLD,
        "S2_no_kg_support": support is not None and not support["supported"],
        "S3_set_conflict": bool(conflicts),
        "S4_evidence_unsupported": trace.get("evidence", {}).get("level") == "unsupported",
        "S5_vacuous_accepted": bool((trace.get("grounding") or {}).get("vacuous")),
    }
    return {"clause": trace["clause"], "decl": trace.get("decl"), "signals": signals,
            "level": sum(signals.values()), "review": any(signals.values()),
            "evidence": {"mass": {k: mass.get(k) for k in ("activated", "violated", "ratio")} if mass else None,
                         "kg_support": support, "conflicts_with": conflicts,
                         "evidence_level": trace.get("evidence", {}).get("level")}}


def risk_coverage(flags: Mapping[str, Mapping[str, Any]], predictions: Mapping[str, Mapping[str, Any]],
                  gold_clauses: Optional[Mapping[str, Mapping[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Mỗi ngưỡng k: giữ luật có mức < k (k = MAX_LEVEL + 1 = giữ tất cả)."""
    rows = []
    for k in range(MAX_LEVEL + 1, 0, -1):
        kept = sorted(n for n, f in flags.items() if f["level"] < k)
        row: Dict[str, Any] = {"keep_if_level_below": k, "kept": len(kept), "total": len(flags)}
        if gold_clauses is not None:
            scored = [n for n in kept if n in gold_clauses]
            classes = {n: score_clause(gold_clauses[n], predictions[n]) for n in scored}
            row.update(false_on_trap=sum(c == "TRAP_FALSE_RULE" for c in classes.values()),
                       correct_on_positive=sum(is_correct(c) and gold_clauses[n]["kind"] != "trap"
                                               for n, c in classes.items()),
                       wrong_on_positive=sum(not is_correct(c) and gold_clauses[n]["kind"] != "trap"
                                             for n, c in classes.items()),
                       not_scored=len(kept) - len(scored))
        rows.append(row)
    return rows


def summary(flags: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    by_level: Dict[int, int] = {}
    for f in flags.values():
        by_level[f["level"]] = by_level.get(f["level"], 0) + 1
    return {"rules": len(flags), "review": sum(f["review"] for f in flags.values()),
            "by_signal": {s: sum(f["signals"][s] for f in flags.values()) for s in SIGNALS},
            "by_level": dict(sorted(by_level.items()))}


def markdown(config: str, flags: Mapping[str, Mapping[str, Any]], curve: List[Mapping[str, Any]]) -> str:
    s = summary(flags)
    lines = [f"## Nhãn REVIEW — cấu hình {config} (đăng ký trước B7; mô tả, không đổi điểm)", "",
             f"Luật: {s['rules']} · REVIEW (≥ 1 tín hiệu): {s['review']} · theo mức: {s['by_level']}", "",
             "| Tín hiệu | Số luật |", "|---|---|"]
    lines += [f"| {name} | {n} |" for name, n in s["by_signal"].items()]
    has_gold = bool(curve) and "false_on_trap" in curve[0]
    head = "| Giữ luật có mức < k | Giữ lại |" + (" Sai trên bẫy | Đúng trên positive | Sai trên positive | "
                                                    "Không chấm |" if has_gold else "")
    lines += ["", f"Bảng giữ lại — rủi ro (k = {MAX_LEVEL + 1}: giữ tất cả):", "", head,
              "|---|---|" + ("---|---|---|---|" if has_gold else "")]
    for r in curve:
        cells = [str(r["keep_if_level_below"]), f"{r['kept']}/{r['total']}"]
        if has_gold:
            cells += [str(r["false_on_trap"]), str(r["correct_on_positive"]), str(r["wrong_on_positive"]),
                      str(r["not_scored"])]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "| Khoản | Mức | Tín hiệu | .decl |", "|---|---|---|---|"]
    for n, f in sorted(flags.items(), key=lambda x: (-x[1]["level"], x[0])):
        on = ", ".join(k.split("_", 1)[0] for k, v in f["signals"].items() if v) or "—"
        lines.append(f"| {n} | {f['level']} | {on} | `{(f['decl'] or '').replace('|', '¦')}` |")
    return "\n".join(lines) + "\n"
