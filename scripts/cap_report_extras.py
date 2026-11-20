"""
Các phần bổ sung của báo cáo HTML (C8, 2026-11-20) — chỉ ĐỌC các file phân tích đã có trong thư mục kết quả, không tính
lại gì. Phần nào thiếu file thì ghi rõ lệnh tạo, không ẩn đi.

  D  Kiểm chứng: B1 theo thành phần, phễu kiểm chứng, nhãn REVIEW + bảng giữ lại — rủi ro, dẫn chứng + kiểm tập
     (proof trace), KG đầy đủ 5 tầng
  E  Độ tin cậy của số liệu: cổng dấu dữ liệu, độ nhạy theo hiệu lực thời gian (B5)
Gọi từ scripts/build_cap_report.py (truyền vào các hàm vẽ bảng của nó để giữ cùng kiểu trình bày).
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

LEVELS = ("issue", "rule", "application", "conclusion")
LEVEL_VI = {"issue": "Nhận ra nghĩa vụ", "rule": "Đúng mẫu", "application": "Đúng activity", "conclusion": "Đúng hoàn toàn (EQ)"}


def _load(path: Path) -> Optional[Dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{100 * x:.1f}%"


def _missing(esc: Callable[[str], str], what: str, cmd: str) -> str:
    return f'<p class="sub">Chưa có {esc(what)} — tạo bằng <code>{esc(cmd)}</code>.</p>'


def _components(scores: Mapping[str, Any], cfgs: Sequence[str], label: Mapping[str, str], table: Callable) -> str:
    rows = []
    for c in cfgs:
        comp = scores["configs"][c].get("components") or {}
        if comp:
            rows.append([label.get(c, c), *(f"{comp[lv]['correct']}/{comp[lv]['n']} ({_pct(comp[lv]['rate'])})"
                                            for lv in LEVELS if lv in comp)])
    if not rows:
        return ""
    return ('<div class="card"><h3>B1 — khoản có ràng buộc, chấm theo thành phần (lồng nhau)</h3>'
            '<p class="sub">Mỗi mức chỉ đạt khi mức trước đạt. Cho thấy hệ thống hỏng ở bước nào.</p>'
            + table(["Cấu hình", *(LEVEL_VI[lv] for lv in LEVELS)], rows, True) + "</div>")


def _funnel(d: Path, cfgs: Sequence[str], label: Mapping[str, str], table: Callable, esc: Callable) -> str:
    f = _load(d / "verification_funnel.json")
    if not f:
        return _missing(esc, "phễu kiểm chứng", "python scripts/verification_funnel.py --pred-dir <dir>")
    present = [c for c in cfgs if c in f]
    statuses = sorted({s for c in present for s in f[c]["rounds_by_status"]})
    rows = [[s, *(f[c]["rounds_by_status"].get(s, 0) for c in present)] for s in statuses]
    rows += [["Tổng vòng gọi LLM", *(f[c]["llm_rounds"] for c in present)],
             ["Vòng bị chặn", *(f[c]["rejected_rounds"] for c in present)],
             ["Luật sửa được sau khi bị chặn", *(f[c]["rules_fixed_after_rejection"] for c in present)]]
    if all("false_rules_on_traps" in f[c] for c in present):
        rows.append(["Luật sai lọt qua (bẫy vẫn ra luật)",
                     *(f"{len(f[c]['false_rules_on_traps'])}/{f[c]['gold_traps']}" for c in present)])
    return ('<div class="card"><h3>Phễu kiểm chứng — mỗi lớp kiểm chặn bao nhiêu vòng sinh</h3>'
            + table(["Trạng thái vòng", *(label.get(c, c) for c in present)], rows, True) + "</div>")


def _review(d: Path, cfgs: Sequence[str], label: Mapping[str, str], table: Callable, esc: Callable) -> str:
    parts = []
    for c in cfgs:
        r = _load(d / f"review_flags_{c}.json")
        if not r:
            continue
        s = r["summary"]
        curve = r["risk_coverage"]
        gold = bool(curve) and "false_on_trap" in curve[0]
        head = ["Giữ luật có mức < k", "Giữ lại"] + (["Sai trên bẫy", "Đúng trên positive", "Sai trên positive"]
                                                    if gold else [])
        rows = [[x["keep_if_level_below"], f"{x['kept']}/{x['total']}"]
                + ([x["false_on_trap"], x["correct_on_positive"], x["wrong_on_positive"]] if gold else [])
                for x in curve]
        sig = ", ".join(f"{k.split('_', 1)[0]} {v}" for k, v in s["by_signal"].items())
        parts.append(f'<div class="card"><h3>Nhãn REVIEW — {esc(label.get(c, c))}</h3>'
                     f'<p class="sub">{s["review"]}/{s["rules"]} luật cần người xem · theo tín hiệu: {esc(sig)} · '
                     f'log {"có" if r.get("log_checked") else "KHÔNG"} được kiểm (S1).</p>'
                     + table(head, rows, True) + "</div>")
    return "".join(parts) or _missing(esc, "nhãn REVIEW", "python scripts/review_flags.py --pred-dir <dir>")


def _proof(d: Path, cfgs: Sequence[str], label: Mapping[str, str], table: Callable, esc: Callable) -> str:
    rows = []
    for c in cfgs:
        p = _load(d / f"proof_traces_{c}.json")
        if p:
            s = p["summary"]
            rows.append([label.get(c, c), s["rules"], s["evidence_verbatim"], s["evidence_near"],
                         s["evidence_unsupported"], ", ".join(f"{k} {v}" for k, v in s["set_kinds"].items()) or "—"])
    if not rows:
        return _missing(esc, "proof trace", "python scripts/build_proof_traces.py --pred-dir <dir> --config Y")
    return ('<div class="card"><h3>Dẫn chứng của LLM và kiểm tập ràng buộc (proof trace)</h3>'
            '<p class="sub">Chi tiết từng luật: proof_traces_&lt;cấu hình&gt;.html trong cùng thư mục.</p>'
            + table(["Cấu hình", "Luật", "Dẫn chứng nguyên văn", "Gần nguyên văn", "Không có căn cứ", "Kiểm tập"],
                    rows, True) + "</div>")


def _full_kg(d: Path, cfgs: Sequence[str], label: Mapping[str, str], table: Callable) -> str:
    rows = []
    for c in cfgs:
        k = _load(d / f"kg_full_{c}.json")
        if k:
            layers = k.get("meta", {}).get("layers", {})
            rows.append([label.get(c, c), len(k["nodes"]), len(k["edges"]),
                         ", ".join(f"{n} {v}" for n, v in layers.items())])
    if not rows:
        return ""
    return ('<div class="card"><h3>KG đầy đủ 5 tầng (tuân thủ metamodel)</h3>'
            + table(["Cấu hình", "Node", "Cạnh", "Node theo tầng"], rows) + "</div>")


def section_verification(d: Path, scores: Optional[Mapping[str, Any]], cfgs: Sequence[str],
                         label: Mapping[str, str], table: Callable, esc: Callable) -> str:
    parts = ["<h2>D. Kiểm chứng và giải thích</h2>"]
    if scores:
        parts.append(_components(scores, [c for c in cfgs if c in scores["configs"]], label, table))
    parts += [_funnel(d, cfgs, label, table, esc), _review(d, cfgs, label, table, esc),
              _proof(d, cfgs, label, table, esc), _full_kg(d, cfgs, label, table)]
    return "".join(parts)


def section_reliability(scores: Optional[Mapping[str, Any]], label: Mapping[str, str], table: Callable,
                        esc: Callable) -> str:
    if not scores:
        return ""
    parts = ["<h2>E. Độ tin cậy của số liệu</h2>"]
    chk = scores.get("inputs_check")
    if chk is not None:
        ok = not chk["within"] and not chk["across"]
        parts.append('<div class="card"><h3>Cổng dấu dữ liệu (A2)</h3><p class="sub">'
                     + ("Mọi khoản đã có dấu đều sinh từ cùng phiên bản dữ liệu." if ok else
                        "CÓ khoản sinh từ phiên bản dữ liệu khác — xem scores.json → inputs_check.")
                     + (f" Khoản chưa có dấu (sinh trước 2026-11-20): {esc(str(chk['unstamped']))}."
                        if chk["unstamped"] else "") + "</p></div>")
    sens = scores.get("sensitivity_temporal")
    if sens:
        rows = [[label.get(c, c), f"{r['correct']}/{r['n']}", _pct(r["rate"])] for c, r in sens["overall"].items()]
        prow = [[n, pc["n"], len(pc["only_a"]), len(pc["only_b"]), pc["p_value"]] for n, pc in sens["paired"].items()]
        parts.append(f'<div class="card"><h3>Độ nhạy theo hiệu lực thời gian (B5)</h3><p class="sub">Chấm lại sau khi '
                     f'bỏ {len(sens["excluded"])} khoản có sửa đổi 2015–2017 (còn {sens["n_scored"]} khoản). So với '
                     'phần B: kết luận có đổi không?</p>'
                     + table(["Cấu hình", "Đúng", "Tỉ lệ"], rows)
                     + table(["So sánh", "n", "Chỉ trái đúng", "Chỉ phải đúng", "p"], prow) + "</div>")
    return "".join(parts) if len(parts) > 1 else ""
