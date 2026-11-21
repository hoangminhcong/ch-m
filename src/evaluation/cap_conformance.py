"""
TN7 bộ CAP: so phán quyết TỪNG HỒ SƠ của ràng buộc hệ thống sinh với ràng buộc gold trên toàn bộ log BPIC2018.

Một ràng buộc cho mỗi hồ sơ một trạng thái engine: Satisfied | Violated | Vacuously Satisfied (không kích hoạt).
Lớp nhị phân dùng để so: "vi phạm" (Violated) vs "không vi phạm" — đúng câu hỏi kiểm toán "hồ sơ nào vi phạm?".
  agreement      tỉ lệ hồ sơ hai ràng buộc cho cùng phán quyết
  precision      trong các hồ sơ hệ thống báo vi phạm, bao nhiêu gold cũng báo (báo oan = 1 − precision)
  recall         trong các hồ sơ gold báo vi phạm, hệ thống bắt được bao nhiêu
  kappa          Cohen's kappa (trừ phần trùng ngẫu nhiên — agreement cao có thể chỉ vì hầu hết không vi phạm)
  vacuous        ràng buộc không kích hoạt trên hồ sơ nào (kiểm tra rỗng của Tầng 3)
"""

from typing import Any, Dict, List, Mapping, Optional, Sequence

VIOLATED, VACUOUS = "Violated", "Vacuously Satisfied"


def rule_profile(states: Sequence[str]) -> Dict[str, int]:
    return {"cases": len(states), "violated": sum(s == VIOLATED for s in states),
            "activated": sum(s != VACUOUS for s in states)}


def _ratio(a: int, b: int) -> Optional[float]:
    return round(a / b, 4) if b else None


def cohen_kappa(tp: int, fp: int, fn: int, tn: int) -> Optional[float]:
    n = tp + fp + fn + tn
    if n == 0:
        return None
    po = (tp + tn) / n
    pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / (n * n)
    if pe == 1:  # cả hai phía cùng một nhãn cho mọi hồ sơ (VD không vi phạm nào): kappa không xác định
        return None  # rà soát 2026-11-18 E-M1: trước đây trả 1.0 — "hoàn hảo" giả
    return round((po - pe) / (1 - pe), 4) + 0.0  # + 0.0: không in '-0.0' (rà soát 2026-11-20, lỗi 13)


def compare_verdicts(gold_states: Sequence[str], pred_states: Sequence[str]) -> Dict[str, Any]:
    if len(gold_states) != len(pred_states):
        raise ValueError("Hai dãy phán quyết phải cùng thứ tự hồ sơ và cùng độ dài")
    g = [s == VIOLATED for s in gold_states]
    p = [s == VIOLATED for s in pred_states]
    tp = sum(a and b for a, b in zip(g, p, strict=True))
    fp = sum(b and not a for a, b in zip(g, p, strict=True))
    fn = sum(a and not b for a, b in zip(g, p, strict=True))
    tn = len(g) - tp - fp - fn
    pred = rule_profile(pred_states)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "agreement": _ratio(tp + tn, len(g)),
            "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn), "kappa": cohen_kappa(tp, fp, fn, tn),
            "pred_violated": pred["violated"], "pred_activated": pred["activated"], "vacuous": pred["activated"] == 0}


def best_gold_match(gold_lines: Sequence[str], pred_line: str,
                    states: Mapping[str, Sequence[str]]) -> Dict[str, Any]:
    """Khoản có nhiều gold → so với gold khớp nhất (cùng quy tắc 'lớp tốt nhất' như TN5): theo kappa trước, rồi
    agreement. Rà soát 2026-11-20 (lỗi 13): trước đây theo agreement — gần như luôn chọn gold ít vi phạm nhất (đa số
    hồ sơ không vi phạm) chứ không phải gold khớp phán quyết nhất."""
    rows: List[Dict[str, Any]] = []
    for gl in gold_lines:
        rows.append({"gold_line": gl, **compare_verdicts(states[gl], states[pred_line])})
    # trùng khớp hoàn toàn đứng đầu (kappa không xác định khi cả hai cùng một nhãn cho mọi hồ sơ)
    return max(rows, key=lambda r: (r["agreement"] == 1.0, r["kappa"] if r["kappa"] is not None else -2.0,
                                    r["agreement"] or 0))
