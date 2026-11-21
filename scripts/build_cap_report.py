"""
Báo cáo trực quan TN5–TN8 bộ CAP: một file HTML tự chứa (SVG dựng sẵn + tooltip), mở bằng trình duyệt.

  Phần A (luôn có)       kết quả SINH: RULE / BASELESS / FAILED theo cấu hình, số vòng tự sửa, ngữ cảnh đồ thị
  Phần B (cần scores)    TN5 độ chính xác ± KTC 95%, phân loại lỗi, TN6 X vs Y (McNemar), TN8 ablation
  Phần C (cần conform.)  TN7 phán quyết từng hồ sơ: số hồ sơ vi phạm theo gold, độ khớp X / Y
  Phần D, E (C8, 2026-11-20; scripts/cap_report_extras.py)  B1, phễu kiểm chứng, nhãn REVIEW, proof trace + kiểm
                         tập, KG 5 tầng; cổng dấu dữ liệu, độ nhạy B5 — đọc file do `run_pipeline.py post` tạo
Mọi biểu đồ kèm bảng số (mở "Bảng số liệu") — tooltip chỉ bổ sung, không phải nơi duy nhất có số.

Chạy:  python scripts/build_cap_report.py [--dir results/cap]
Đọc:   <dir>/predictions_*.json, <dir>/scores.json (nếu có), <dir>/conformance.json (nếu có)
Ghi:   <dir>/report.html
"""

import argparse
import html
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.cap_report_extras import section_reliability, section_verification  # noqa: E402
from src.evaluation.cap_scoring import paired_p  # noqa: E402

CONFIG_ORDER = ["X", "Y", "Y-noL12", "Y-noL3", "Y-retry1", "Y-noVac", "Y-noDomain", "Y-noDuty", "R", "N", "Z",
                "Z-noLegal", "Z-noProcess", "Z-noMass", "Z-noNotes", "Z-noHint"]
CONFIG_VI = {"X": "X · chỉ khoản luật", "Y": "Y · Graph-RAG", "Y-noL12": "Y − Tầng 1–2",
             "Y-noL3": "Y − Tầng 3", "Y-retry1": "Y − tự sửa (1 vòng)", "Y-noVac": "Y − kiểm rỗng (B)",
             "Y-noDomain": "Y − miền giá trị/năm (C,E)", "Y-noDuty": "Y − phân tích nghĩa vụ (D)",
             "R": "R · RAG BM25 (B4)", "N": "N · khung chuẩn tắc (B6)",
             "Z": "Z · v2 (KG giàu hơn)", "Z-noLegal": "Z − định nghĩa/phạm vi",
             "Z-noProcess": "Z − kiểm tầng Tiến trình", "Z-noMass": "Z − vi phạm hàng loạt",
             "Z-noNotes": "Z − ghi chú cho giám khảo", "Z-noHint": "Z − gợi ý loại giấy tờ"}
GEN_CATS = [("RULE", "Sinh ràng buộc", 1), ("BASELESS", "Kết luận BASELESS", 2), ("FAILED", "Hết vòng, không kết quả", 3)]
POS_GROUPS = [("Đúng (EQ)", ["EQ"], 1), ("Lệch một phần", ["STRENGTHENED", "WEAKENED", "COND_DIFF"], 2),
              ("Sai hướng / sai activity", ["REVERSED", "MISMATCH"], 3),
              ("Không ra ràng buộc", ["MISSED_AS_BASELESS", "FAILED"], 4)]
W, LABEL_W, ROW_H, BAR_H, GAP = 720, 170, 34, 20, 2
esc = html.escape

CSS = """
.viz-root{color-scheme:light;--surface-1:#fcfcfb;--page:#f9f9f7;--text-primary:#0b0b0b;--text-secondary:#52514e;
--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.10);--de:#c3c2b7;
--series-1:#2a78d6;--series-2:#eb6834;--series-3:#1baf7a;--series-4:#eda100;--on-4:#0b0b0b}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;
--surface-1:#1a1a19;--page:#0d0d0d;--text-primary:#f0efec;--text-secondary:#c3c2b7;--grid:#2c2c2a;--axis:#383835;
--border:rgba(255,255,255,.10);--de:#5a5955;--series-1:#3987e5;--series-2:#d95926;--series-3:#199e70;
--series-4:#c98500;--on-4:#0b0b0b}}
:root[data-theme="dark"] .viz-root{color-scheme:dark;--surface-1:#1a1a19;--page:#0d0d0d;--text-primary:#f0efec;
--text-secondary:#c3c2b7;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--de:#5a5955;
--series-1:#3987e5;--series-2:#d95926;--series-3:#199e70;--series-4:#c98500;--on-4:#0b0b0b}
body{margin:0}
.viz-root{background:var(--page);color:var(--text-primary);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
min-height:100vh;padding:24px}
main{max-width:800px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 4px}h3{font-size:14px;margin:16px 0 4px}
p,.sub{color:var(--text-secondary);margin:4px 0 12px}
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:8px;padding:16px;margin:12px 0}
.banner{border-left:4px solid #d03b3b;padding:8px 12px;background:var(--surface-1);margin:12px 0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.tile .label{color:var(--text-secondary);font-size:13px}.tile .value{font-size:28px;font-weight:600}
.tile .note{color:var(--muted);font-size:12px}
svg text{fill:var(--text-secondary);font-size:12px}svg .val{fill:var(--text-primary);font-variant-numeric:tabular-nums}
svg .in{fill:#fff;font-size:11px}svg .in4{fill:var(--on-4);font-size:11px}
.grid{stroke:var(--grid);stroke-width:1}.axis{stroke:var(--axis);stroke-width:1}
.s1{fill:var(--series-1)}.s2{fill:var(--series-2)}.s3{fill:var(--series-3)}.s4{fill:var(--series-4)}
.de{fill:var(--de)}.ci{stroke:var(--text-primary);stroke-width:1.5}
.d1{fill:var(--series-1);stroke:var(--surface-1);stroke-width:2}.d2{fill:var(--series-2);stroke:var(--surface-1);stroke-width:2}
.d3{fill:var(--series-3);stroke:var(--surface-1);stroke-width:2}
.d4{fill:var(--series-4);stroke:var(--surface-1);stroke-width:2}
[data-tip]:hover,[data-tip]:focus{opacity:.8;outline:none}
.legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--text-secondary);font-size:13px;margin:4px 0 8px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.legend i.s1{background:var(--series-1)}.legend i.s2{background:var(--series-2)}.legend i.s3{background:var(--series-3)}.legend i.s4{background:var(--series-4)}
table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:4px 8px;border-bottom:1px solid var(--grid)}th{color:var(--text-secondary);font-weight:600}
details summary{cursor:pointer;color:var(--text-secondary);font-size:13px;margin-top:8px}
#tip{position:fixed;pointer-events:none;background:var(--surface-1);border:1px solid var(--border);border-radius:6px;
padding:6px 10px;box-shadow:0 2px 8px rgba(0,0,0,.15);display:none;font-size:13px;max-width:320px}
#tip b{display:block;font-size:14px}
code{font-size:12px}
"""
JS = """
const tip=document.getElementById('tip');
function show(e){const t=e.currentTarget.dataset.tip.split('\\n');tip.replaceChildren();
const b=document.createElement('b');b.textContent=t[0];tip.appendChild(b);
for(const line of t.slice(1)){const d=document.createElement('div');d.textContent=line;tip.appendChild(d);}
tip.style.display='block';const r=e.currentTarget.getBoundingClientRect();
const x=(e.clientX||r.right)+12,y=(e.clientY||r.top)+12;tip.style.left=Math.min(x,innerWidth-330)+'px';tip.style.top=y+'px';}
function hide(){tip.style.display='none';}
for(const el of document.querySelectorAll('[data-tip]')){el.setAttribute('tabindex','0');
el.addEventListener('pointermove',show);el.addEventListener('focus',show);
el.addEventListener('pointerleave',hide);el.addEventListener('blur',hide);}
"""


def _pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{100 * x:.1f}%"


def _bar_path(x0: float, y: float, w: float, h: float, r: float = 4) -> str:
    """Thanh ngang: góc vuông ở đường gốc (trái), bo 4px ở đầu dữ liệu (phải)."""
    if w <= 0:
        return ""
    r = min(r, w, h / 2)
    return (f"M{x0:.1f},{y:.1f}h{w - r:.1f}a{r},{r} 0 0 1 {r},{r}v{h - 2 * r:.1f}"
            f"a{r},{r} 0 0 1 -{r},{r}h-{w - r:.1f}z")


def _tip(text: str) -> str:
    return f' data-tip="{esc(text, quote=True)}"'


def svg_rate_bars(rows: Sequence[Mapping[str, Any]], emphasis: str = "Y") -> str:
    """Tỉ lệ đúng từng cấu hình, râu = KTC Wilson 95%. Cấu hình chính tô màu, còn lại xám (nhấn một)."""
    plot = W - LABEL_W - 120  # chừa chỗ cho nhãn giá trị ở 100%
    h = len(rows) * ROW_H + 26
    out = [f'<svg viewBox="0 0 {W} {h}" width="100%" role="img">']
    for t in (0, .25, .5, .75, 1):
        x = LABEL_W + t * plot
        out.append(f'<line class="grid" x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{h - 22}"/>'
                   f'<text x="{x:.1f}" y="{h - 6}" text-anchor="middle">{int(t * 100)}%</text>')
    for i, r in enumerate(rows):
        y = i * ROW_H + (ROW_H - BAR_H) / 2
        out.append(f'<text x="{LABEL_W - 8}" y="{y + BAR_H / 2 + 4}" text-anchor="end">{esc(r["label"])}</text>')
        if not r["n"]:
            out.append(f'<text x="{LABEL_W + 4}" y="{y + BAR_H / 2 + 4}">không có khoản</text>')
            continue
        cls = "s1" if r["key"] == emphasis else "de"
        lo, hi = r["ci95"]
        tip = f"{_pct(r['rate'])}\n{r['label']}: {r['correct']}/{r['n']} đúng\nKTC 95%: {_pct(lo)} – {_pct(hi)}"
        out.append(f'<path class="{cls}" d="{_bar_path(LABEL_W, y, r["rate"] * plot, BAR_H)}"{_tip(tip)}/>')
        cy = y + BAR_H / 2
        out.append(f'<line class="ci" x1="{LABEL_W + lo * plot:.1f}" y1="{cy}" x2="{LABEL_W + hi * plot:.1f}" y2="{cy}"/>'
                   f'<line class="ci" x1="{LABEL_W + lo * plot:.1f}" y1="{cy - 5}" x2="{LABEL_W + lo * plot:.1f}" y2="{cy + 5}"/>'
                   f'<line class="ci" x1="{LABEL_W + hi * plot:.1f}" y1="{cy - 5}" x2="{LABEL_W + hi * plot:.1f}" y2="{cy + 5}"/>')
        out.append(f'<text class="val" x="{LABEL_W + max(r["rate"], hi) * plot + 8:.1f}" y="{cy + 4}">'
                   f'{_pct(r["rate"])} ({r["correct"]}/{r["n"]})</text>')
    out.append(f'<line class="axis" x1="{LABEL_W}" y1="0" x2="{LABEL_W}" y2="{h - 22}"/></svg>')
    return "".join(out)


def svg_segmented(rows: Sequence[Tuple[str, Mapping[str, int]]], cats: Sequence[Tuple[str, str, int]]) -> str:
    """Mỗi hàng một tổng chia phần (thanh phân đoạn): khối bo 4px, khe 2px, nhãn trong khối nếu đủ chỗ."""
    plot = W - LABEL_W - 10
    out = [f'<svg viewBox="0 0 {W} {len(rows) * ROW_H}" width="100%" role="img">']
    for i, (label, counts) in enumerate(rows):
        total = sum(counts.values())
        y = i * ROW_H + (ROW_H - BAR_H) / 2
        out.append(f'<text x="{LABEL_W - 8}" y="{y + BAR_H / 2 + 4}" text-anchor="end">{esc(label)}</text>')
        x, parts = LABEL_W, [(c, n, s) for c, n, s in ((c, counts.get(c, 0), s) for c, _, s in cats) if n]
        for j, (cat, n, slot) in enumerate(parts):
            w = n / total * plot - (GAP if j < len(parts) - 1 else 0)
            name = next(v for k, v, _ in cats if k == cat)
            tip = f"{n} khoản · {100 * n / total:.0f}%\n{label} — {name}"
            out.append(f'<rect class="s{slot}" x="{x:.1f}" y="{y}" width="{max(w, 1):.1f}" height="{BAR_H}" rx="4"{_tip(tip)}/>')
            txt = str(n)
            if w > 8 * len(txt) + 12:
                out.append(f'<text class="{"in4" if slot == 4 else "in"}" x="{x + 6:.1f}" y="{y + BAR_H / 2 + 4}">{txt}</text>')
            x += w + GAP
    return "".join(out) + "</svg>"


def svg_dots(rows: Sequence[Tuple[str, Mapping[str, Optional[float]]]], series: Sequence[Tuple[str, str, int]],
             lo: float = -0.2) -> str:
    """Dot plot: mỗi khoản một hàng, mỗi cấu hình một chấm (kappa). Hai chuỗi → có chú giải."""
    plot = W - LABEL_W - 20
    h = len(rows) * 26 + 26
    sx = lambda v: LABEL_W + (v - lo) / (1 - lo) * plot  # noqa: E731
    out = [f'<svg viewBox="0 0 {W} {h}" width="100%" role="img">']
    for t in (0, .2, .4, .6, .8, 1):
        out.append(f'<line class="grid" x1="{sx(t):.1f}" y1="0" x2="{sx(t):.1f}" y2="{h - 22}"/>'
                   f'<text x="{sx(t):.1f}" y="{h - 6}" text-anchor="middle">{t:.1f}</text>')
    for i, (label, vals) in enumerate(rows):
        cy = i * 26 + 13
        out.append(f'<text x="{LABEL_W - 8}" y="{cy + 4}" text-anchor="end">{esc(label)}</text>')
        for key, name, slot in series:
            v = vals.get(key)
            if v is None:
                continue
            out.append(f'<circle class="d{slot}" cx="{sx(max(v, lo)):.1f}" cy="{cy}" r="5"{_tip(f"kappa {v:.2f}" + chr(10) + f"{label} — {name}")}/>')
    return "".join(out) + "</svg>"


def legend(items: Sequence[Tuple[str, int]]) -> str:
    return '<div class="legend">' + "".join(f'<span><i class="s{s}"></i>{esc(n)}</span>' for n, s in items) + "</div>"


def table(headers: Sequence[str], rows: Sequence[Sequence[Any]], open_: bool = False) -> str:
    body = "".join("<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    return (f'<details{" open" if open_ else ""}><summary>Bảng số liệu</summary>'
            f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></details>")


def tile(label: str, value: str, note: str = "") -> str:
    return (f'<div class="card tile"><div class="label">{esc(label)}</div><div class="value">{esc(value)}</div>'
            f'<div class="note">{esc(note)}</div></div>')


def section_generation(preds: Mapping[str, Mapping[str, Any]]) -> str:
    rows, trows = [], []
    for cfg in (c for c in CONFIG_ORDER if c in preds):
        ps = [p for p in preds[cfg]["predictions"].values() if p["outcome"] != "ERROR"]
        counts = {k: sum(p["outcome"] == k for p in ps) for k, _, _ in GEN_CATS}
        rows.append((CONFIG_VI[cfg], counts))
        rounds = [p["rounds_needed"] for p in ps if p["outcome"] != "FAILED"]
        errors = sum(p["outcome"] == "ERROR" for p in preds[cfg]["predictions"].values())
        trows.append([CONFIG_VI[cfg], len(ps), *counts.values(), errors,
                      f"{statistics.mean(rounds):.2f}" if rounds else "—"])
    parts = ['<h2>A. Kết quả sinh (chưa cần gold)</h2>',
             '<p>Mỗi khoản của phiếu CAP chạy qua vòng LLM → AST → Tầng 1–2 (Γ BPIC2018) → Tầng 3. '
             'Phần này không đọc gold nên có trước khi có nhãn.</p>',
             '<div class="card"><h3>Kết quả mỗi khoản theo cấu hình</h3>',
             legend([(n, s) for _, n, s in GEN_CATS]), svg_segmented(rows, GEN_CATS),
             table(["Cấu hình", "Số khoản", "RULE", "BASELESS", "FAILED", "Lỗi API", "Vòng tự sửa TB"], trows), "</div>"]
    parts.append(_checks_card(preds))
    if "Y" in preds:
        parts.append(_context_card(preds["Y"]["predictions"]))
    return "".join(parts)


CHECK_STATUSES = [("FAILED_L1_L2", "Tầng 1–2 (gồm C miền giá trị)"), ("FAILED_VACUITY", "B kiểm rỗng"),
                  ("FAILED_OBLIGATION_ANALYSIS", "D thiếu/sai phân tích"),
                  ("FAILED_OBLIGATION_CONSISTENCY", "D không nhất quán"),
                  ("FAILED_L3_ROUNDTRIP", "Tầng 3 (gồm E năm)")]


def _checks_card(preds: Mapping[str, Mapping[str, Any]]) -> str:
    """Số vòng bị từng kiểm trả lại, số khoản LLM tự kết luận không có nghĩa vụ (D), số ràng buộc rỗng vẫn giữ."""
    rows = []
    for cfg in (c for c in CONFIG_ORDER if c in preds):
        ps = [p for p in preds[cfg]["predictions"].values() if p["outcome"] != "ERROR"]
        statuses = [t["status"] for p in ps for t in p.get("trajectory", [])]
        declined = sum(bool(p.get("trajectory")) and p["trajectory"][-1]["status"] == "DECLINED_NO_OBLIGATION"
                       for p in ps)
        kept_vacuous = sum(bool((p.get("grounding") or {}).get("vacuous")) for p in ps if p["outcome"] == "RULE")
        rows.append([CONFIG_VI[cfg], *(statuses.count(s) for s, _ in CHECK_STATUSES), declined, kept_vacuous])
    return ('<div class="card"><h3>Các kiểm đã can thiệp bao nhiêu lần</h3><p class="sub">Số VÒNG bị trả lại kèm '
            'phản hồi (một khoản có thể bị trả nhiều vòng). "Rỗng vẫn giữ" = LLM giữ ràng buộc sau phản hồi kiểm '
            'rỗng — chấp nhận kèm cờ, vì ràng buộc đúng vẫn có thể rỗng.</p>'
            + table(["Cấu hình", *(n for _, n in CHECK_STATUSES), "D: tự kết luận không nghĩa vụ",
                     "Rỗng vẫn giữ"], rows, True) + "</div>")


def _context_card(ps: Mapping[str, Mapping[str, Any]]) -> str:
    rows = []
    for rnd in (1, 2):
        sub = [p for p in ps.values() if p.get("round") == rnd and p["outcome"] != "ERROR"]
        if sub:
            rows.append([f"Đợt {rnd}", len(sub), sum(bool(p["context_refs"]) for p in sub),
                         sum(p["truncated_chars"] > 0 for p in sub),
                         int(statistics.median(p["context_chars"] for p in sub))])
    return ('<div class="card"><h3>Ngữ cảnh đồ thị của cấu hình Y</h3><p class="sub">Khoản luật + khoản được dẫn '
            'chiếu (REFERS_TO, 1 bước). Văn bản dài bị cắt theo ngân sách ký tự (src/neural/graph_context.py).</p>'
            + table(["Đợt", "Số khoản", "Có dẫn chiếu", "Có cắt bớt", "Ký tự ngữ cảnh (trung vị)"], rows, True)
            + "</div>")


BASELINE_VI = {"always-BASELESS": "Mức chuẩn: luôn BASELESS"}


def _rate_rows(scores: Mapping[str, Any], part: str) -> List[Dict[str, Any]]:
    rows = [{"key": c, "label": CONFIG_VI[c], **scores["configs"][c][part]}
            for c in CONFIG_ORDER if c in scores["configs"]]
    return rows + [{"key": b, "label": BASELINE_VI.get(b, b), **s[part]}
                   for b, s in scores.get("baselines", {}).items()]


def _balanced_card(scores: Mapping[str, Any]) -> str:
    entries = [(CONFIG_VI[c], scores["configs"][c]) for c in CONFIG_ORDER if c in scores["configs"]]
    entries += [(BASELINE_VI.get(b, b), s) for b, s in scores.get("baselines", {}).items()]
    rows = [[label, _pct(s["positive"]["rate"]), _pct(s["trap"]["rate"]), _pct(s.get("balanced"))]
            for label, s in entries]
    return ('<div class="card"><h3>Tỉ lệ cân bằng</h3><p class="sub">Gần như mọi khoản là bẫy, nên "Mọi khoản" bị '
            'mức chuẩn luôn BASELESS (không đọc gì) thắng. Tỉ lệ cân bằng = trung bình của tỉ lệ đúng khoản có ràng '
            'buộc và tỉ lệ đúng khoản bẫy; mức chuẩn đạt 50%.</p>'
            + table(["Cấu hình", "Đúng — có ràng buộc", "Đúng — bẫy", "Cân bằng"], rows) + "</div>")


def section_scores(scores: Mapping[str, Any]) -> str:
    cfgs = [c for c in CONFIG_ORDER if c in scores["configs"]]
    parts = ['<h2>B. Độ chính xác so với gold (TN5, TN6, TN8)</h2>',
             f'<p>{scores["n_scored"]} khoản được chấm ({scores["n_tier4"]} khoản Tier 4). Đúng = khớp gold (EQ) với '
             'khoản có ràng buộc, và kết luận BASELESS với khoản bẫy. Râu = khoảng tin cậy Wilson 95%.</p>']
    for part, title in (("overall", "Mọi khoản"), ("positive", "Khoản có ràng buộc"),
                        ("tier4", "Tier 4 (cần khoản được dẫn chiếu)"), ("trap", "Khoản bẫy (đáp án BASELESS)")):
        rows = _rate_rows(scores, part)
        parts.append(f'<div class="card"><h3>{esc(title)}</h3>{svg_rate_bars(rows)}'
                     + table(["Cấu hình", "Đúng", "n", "Tỉ lệ", "KTC 95%"],
                             [[r["label"], r["correct"], r["n"], _pct(r["rate"]),
                               f"{_pct(r['ci95'][0])} – {_pct(r['ci95'][1])}"] for r in rows]) + "</div>")
    parts.append(_balanced_card(scores))
    grouped =[(CONFIG_VI[c], {g: sum(scores["configs"][c]["positive"]["classes"][k] for k in ks)
                               for g, ks, _ in POS_GROUPS}) for c in cfgs]
    cats = [(g, g, s) for g, _, s in POS_GROUPS]
    parts.append('<div class="card"><h3>Khoản có ràng buộc: hệ thống sai ở đâu</h3>' + legend([(g, s) for g, _, s in POS_GROUPS])
                 + svg_segmented(grouped, cats)
                 + table(["Cấu hình", *scores["configs"][cfgs[0]]["positive"]["classes"]],
                         [[CONFIG_VI[c], *scores["configs"][c]["positive"]["classes"].values()] for c in cfgs]) + "</div>")
    prows = [[name, pc["n"], pc["both"], len(pc["only_a"]), len(pc["only_b"]), paired_p(pc),
              ", ".join(pc["only_a"] + pc["only_b"])[:120]] for name, pc in scores["paired"].items()]
    parts.append('<div class="card"><h3>So cặp trên cùng các khoản (McNemar chính xác)</h3>'
                 '<p class="sub">"Chỉ trái đúng" = cấu hình bên trái đúng mà bên phải sai. p &lt; 0,05 mới coi là khác biệt.</p>'
                 + table(["So sánh", "n", "Cả hai đúng", "Chỉ trái đúng", "Chỉ phải đúng", "p", "Các khoản khác nhau"],
                         prows, True) + "</div>")
    return "".join(parts)


def _agree_cell(r: Optional[Mapping[str, Any]]) -> str:
    """'khớp / kappa'; None (không xác định, VD 0 hồ sơ trong phạm vi năm) → '—' (rà soát 2026-11-18 E-H6)."""
    if not r:
        return "—"
    agree = "—" if r.get("agreement") is None else f"{r['agreement']:.4f}"
    return f"{agree} / {'—' if r.get('kappa') is None else r['kappa']}"


def section_conformance(conf: Mapping[str, Any]) -> str:
    clauses = conf["clauses"]
    # mọi cấu hình có trong conformance.json (trước đây chỉ X, Y — Z bị ẩn), tối đa 4 chuỗi màu cho biểu đồ
    present = [c for c in ("Y", "Z", "X", *CONFIG_ORDER) if any(c in cl["pred"] for cl in clauses.values())]
    present = list(dict.fromkeys(present))
    series = [(c, CONFIG_VI.get(c, c), i + 1) for i, c in enumerate(present[:4])]
    rows = [(nid, {cfg: r["kappa"] for cfg, r in c["pred"].items()}) for nid, c in clauses.items()]
    trows = []
    for nid, c in clauses.items():
        g = c["gold"][0]
        cells = [nid, "Có" if c["tier4"] else "", g["violated"], g["activated"]]
        cells += [_agree_cell(c["pred"].get(cfg)) for cfg in present]
        trows.append(cells)
    return ('<h2>C. Phán quyết từng hồ sơ trên toàn log (TN7)</h2>'
            f'<p>{conf["cases"]} hồ sơ BPIC2018, giờ {esc(conf["timezone"])}. Mỗi chấm = Cohen\'s kappa giữa phán quyết '
            '"vi phạm / không" của ràng buộc hệ thống sinh và của gold (1 = trùng hoàn toàn; 0 = như ngẫu nhiên).</p>'
            '<div class="card"><h3>Độ khớp với gold theo khoản</h3>' + legend([(n, s) for _, n, s in series])
            + svg_dots(rows, series)
            + table(["Khoản", "Tier 4", "Gold: hồ sơ vi phạm", "Gold: hồ sơ kích hoạt",
                     *[f"{c}: khớp / kappa" for c in present]], trows, True) + "</div>")


def _load(path: Path) -> Optional[Dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def build(result_dir: Path) -> str:
    preds = {c: d for c in CONFIG_ORDER if (d := _load(result_dir / f"predictions_{c}.json"))}
    scores, conf = _load(result_dir / "scores.json"), _load(result_dir / "conformance.json")
    if not preds:
        raise SystemExit(f"Chưa có predictions_*.json trong {result_dir}")
    status = (scores or {}).get("gold_status")
    banner = ("" if status == "approved" else
              '<div class="banner"><b>Chưa có gold đã duyệt.</b> ' + (
                  "Số ở phần B/C dùng gold CHƯA duyệt — chỉ để thử pipeline, không dùng cho bài."
                  if scores else "Phần B/C (độ chính xác, TN7) sẽ hiện sau khi có gold và chạy score_cap.py.") + "</div>")
    model = next(iter(preds.values())).get("model", "?")
    tiles = [tile("Khoản đã sinh (Y)", str(len(preds.get("Y", {}).get("predictions", {}))), f"model {model}")]
    if scores and "Y" in scores["configs"]:
        tiles.append(tile("Đúng — cấu hình Y", _pct(scores["configs"]["Y"]["overall"]["rate"]),
                          f"n = {scores['configs']['Y']['overall']['n']}"))
        if "X" in scores["configs"]:
            tiles.append(tile("Đúng — cấu hình X", _pct(scores["configs"]["X"]["overall"]["rate"]),
                              "chỉ khoản luật"))
    body = ["<h1>Kết quả thực nghiệm NSAI + Graph-RAG — BPIC2018 + 4 Quy định CAP</h1>",
            f'<p class="sub">Thư mục {esc(str(result_dir.name))} · tạo lúc {datetime.now():%Y-%m-%d %H:%M}</p>', banner,
            f'<div class="tiles">{"".join(tiles)}</div>', section_generation(preds)]
    if scores:
        body.append(section_scores(scores))
    if conf:
        body.append(section_conformance(conf))
    present = [c for c in CONFIG_ORDER if c in preds]
    body.append(section_verification(result_dir, scores, present, CONFIG_VI, table, esc))
    body.append(section_reliability(scores, CONFIG_VI, table, esc))
    return (f'<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8"><title>Kết quả CAP</title>'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head>'
            f'<body><div class="viz-root"><main>{"".join(body)}</main><div id="tip" role="tooltip"></div></div>'
            f"<script>{JS}</script></body></html>")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--dir", default=str(PROJECT_ROOT / "results" / "cap"))
    args = p.parse_args()
    out = Path(args.dir) / "report.html"
    out.write_text(build(Path(args.dir)), encoding="utf-8")
    sys.stdout.write(f"Đã ghi {out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
