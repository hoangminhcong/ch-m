"""
Phễu kiểm chứng: LLM đề xuất sai bao nhiêu lần, mỗi lớp kiểm chặn bao nhiêu, bao nhiêu lọt qua.

Trả lời câu hỏi "sinh bằng LLM có được kiểm soát không": đếm trạng thái của MỌI vòng sinh–kiểm (trajectory) của mọi
khoản, gom theo lớp kiểm. Luật cuối cùng (outcome RULE) luôn đã qua mọi lớp — "lọt qua" chỉ đo được khi so với gold:
khoản bẫy (gold: không có nghĩa vụ quan sát được) mà hệ thống vẫn đưa ra luật.
"""

from typing import Any, Dict, Mapping, Optional

# trạng thái một vòng → lớp kiểm (src/evaluation/real_llm_client.py); trạng thái lạ giữ nguyên tên
LAYER_OF = {
    "PASSED": "qua mọi lớp",
    "DECLINED_NO_OBLIGATION": "LLM tự từ chối (D: không có nghĩa vụ quan sát được)",
    "DETECTED_BASELESS_TRAP": "Tầng 3 — giám khảo kết luận BASELESS",
    "FAILED_L1_SYNTAX": "Tầng 1 — trả lời không đọc được thành AST (kiểm tối thiểu khi tắt Tầng 1–2)",
    "FAILED_L1_L2": "Tầng 1–2 — sai cú pháp / kiểu (Γ, miền giá trị C)",
    "FAILED_L3_ROUNDTRIP": "Tầng 3 — đọc ngược không khớp luật / Entity Matcher (E)",
    "FAILED_VACUITY": "B — ràng buộc rỗng trên log",
    "FAILED_OBLIGATION_CONSISTENCY": "D — chủ thể nghĩa vụ mâu thuẫn với ràng buộc",
    "FAILED_OBLIGATION_ANALYSIS": "D — thiếu / sai phân tích nghĩa vụ",
    # cấu hình N (đăng ký trước B6): khung chuẩn tắc
    "FAILED_NORM_FRAME": "N1 — khung chuẩn tắc sai định dạng",
    "DECLINED_NORM_TYPE": "N2 — loại chuẩn tắc không diễn đạt được bằng DECLARE (→ BASELESS)",
    "FAILED_NORM_DEADLINE": "N3 — thời hạn đã trích không có trong ràng buộc",
    "FAILED_NORM_TEMPLATE": "N5 — mẫu DECLARE không hợp loại chuẩn tắc",
    "FAILED_KG_SUPPORT": "N4 — activity không thuộc loại giấy tờ mà khoản nối tới (KG, MAPS_TO)",
    # v2 (cấu hình Z): kiểm tầng Tiến trình
    "FAILED_ATTRIBUTE_PLACEMENT": "v2 — thuộc tính đặt sai mức (hồ sơ / sự kiện)",
    "FAILED_YEAR_COVERAGE": "v2 — activity không có ở các năm của khoản",
    "FAILED_MASS_VIOLATION": "v2 — vi phạm hàng loạt (> 20% hồ sơ kích hoạt)",
}
REJECTING = ("FAILED_L1_SYNTAX", "FAILED_L1_L2", "FAILED_L3_ROUNDTRIP", "FAILED_VACUITY", "FAILED_OBLIGATION_CONSISTENCY",
             "FAILED_OBLIGATION_ANALYSIS", "FAILED_ATTRIBUTE_PLACEMENT", "FAILED_YEAR_COVERAGE",
             "FAILED_MASS_VIOLATION", "FAILED_NORM_FRAME", "FAILED_NORM_DEADLINE", "FAILED_NORM_TEMPLATE",
             "FAILED_KG_SUPPORT")


def funnel(predictions: Mapping[str, Mapping[str, Any]],
           gold_clauses: Optional[Mapping[str, Mapping[str, Any]]] = None) -> Dict[str, Any]:
    """predictions: khoản → bản ghi dự đoán (có 'trajectory', 'outcome'); gold_clauses (tuỳ chọn) để đếm luật lọt qua."""
    rounds: Dict[str, int] = {}
    first: Dict[str, int] = {}
    outcomes: Dict[str, int] = {}
    rejected_then_fixed = 0
    for p in predictions.values():
        outcomes[p.get("outcome", "?")] = outcomes.get(p.get("outcome", "?"), 0) + 1
        statuses = [t.get("status") for t in p.get("trajectory") or []]
        for i, s in enumerate(statuses):
            rounds[s] = rounds.get(s, 0) + 1
            if i == 0:
                first[s] = first.get(s, 0) + 1
        if p.get("outcome") == "RULE" and any(s in REJECTING for s in statuses):
            rejected_then_fixed += 1
    out: Dict[str, Any] = {
        "clauses": len(predictions), "llm_rounds": sum(rounds.values()), "rounds_by_status": rounds,
        "first_round_by_status": first, "rejected_rounds": sum(rounds.get(s, 0) for s in REJECTING),
        "rules_fixed_after_rejection": rejected_then_fixed, "outcomes": outcomes,
        "final_rules_not_passed": sum(1 for p in predictions.values() if p.get("outcome") == "RULE"
                                      and (p.get("trajectory") or [{}])[-1].get("status") != "PASSED"),
    }
    if gold_clauses is not None:
        traps = [n for n, g in gold_clauses.items() if g.get("kind") == "trap" and n in predictions]
        out["gold_traps"] = len(traps)
        out["false_rules_on_traps"] = sorted(n for n in traps if predictions[n].get("outcome") == "RULE")
    return out


def _status_order(status: Optional[str]) -> tuple:
    return (list(LAYER_OF).index(status) if status in LAYER_OF else 99, status or "")


def markdown_table(results: Mapping[str, Mapping[str, Any]]) -> str:
    """Bảng: mỗi cấu hình một cột; hàng = lớp kiểm (số VÒNG theo trạng thái), rồi tổng kết."""
    configs = list(results)
    statuses = sorted({s for r in results.values() for s in r["rounds_by_status"]}, key=_status_order)
    head = "| Lớp kiểm (số vòng) | " + " | ".join(configs) + " |\n|---|" + "---|" * len(configs) + "\n"
    rows = [f"| {LAYER_OF.get(s, s)} | " + " | ".join(str(results[c]["rounds_by_status"].get(s, 0)) for c in configs)
            + " |" for s in statuses]
    extra = [("**Tổng vòng gọi LLM**", "llm_rounds"), ("Vòng bị chặn (Tầng 1–3, B, D)", "rejected_rounds"),
             ("Luật được sửa đúng sau khi bị chặn", "rules_fixed_after_rejection"),
             ("Luật cuối KHÔNG ở trạng thái PASSED", "final_rules_not_passed")]
    rows += [f"| {label} | " + " | ".join(str(results[c][key]) for c in configs) + " |" for label, key in extra]
    if all("false_rules_on_traps" in r for r in results.values()):
        rows.append("| **Luật sai lọt qua** (khoản bẫy vẫn ra luật, theo gold) | "
                    + " | ".join(f"{len(results[c]['false_rules_on_traps'])}/{results[c]['gold_traps']}"
                                 for c in configs) + " |")
    return head + "\n".join(rows) + "\n"
