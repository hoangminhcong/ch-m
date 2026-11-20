"""
Đối chiếu nhãn CAP của NHIỀU AI (HUONG_DAN_GAN_NHAN_CAP.md, mục 10.5) — người chỉ phải xem phần khác nhau.

So từng khoản giữa các AI:
  Quan sát được (Có / Không / Không chắc);  nếu mọi AI nói Có: Ràng buộc mới (so SAU khi chuyển thành AST — viết
  khác nhau mà cùng nghĩa vẫn là giống) và Cần điều tham chiếu (Tier 4: Có / Một phần vs Không).
Khoản ĐỒNG THUẬN = mọi trường trên giống nhau ở mọi AI. Còn lại = BẤT ĐỒNG (người quyết).
Mẫu kiểm ngẫu nhiên trong nhóm đồng thuận: max(--spot-min, --spot-frac × số khoản đồng thuận), seed cố định.

Chạy:  python scripts/compare_cap_labels.py --labels CAP_ITEM_CANDIDATES_claude.txt CAP_ITEM_CANDIDATES_gemini.txt
       tập Đức: thêm --candidates data/review/de_item_candidates.json --out-dir data/review/de_ai_compare
Đọc:   các file nhãn, data/review/cap_item_candidates.json, data/processed/gamma_bpic2018.json
Ghi:   <out-dir>/DOI_CHIEU.md (người đọc), doi_chieu.json (số liệu), CAP_ITEM_CANDIDATES_final_draft.txt (nháp nhãn
       cuối: khoản đồng thuận điền sẵn; khoản bất đồng để '___'; dòng '# …' phía trên đánh dấu khoản cần người xem)
"""

import argparse
import itertools
import json
import math
import random
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.cap_gold import needs_reference, parse_label_sheet  # noqa: E402
from src.evaluation.cap_notation import NotationError, notation_to_ast  # noqa: E402
from src.evaluation.cap_scoring import condition_set, time_exact  # noqa: E402

CANDIDATES = PROJECT_ROOT / "data" / "review" / "cap_item_candidates.json"
GAMMA = PROJECT_ROOT / "data" / "processed" / "gamma_bpic2018.json"
DEFAULT_OUT = PROJECT_ROOT / "data" / "review" / "ai_compare"
OBS_VI = {"yes": "Có", "no": "Không", "unsure": "Không chắc", "blank": "(chưa điền)"}
SEED = 2018


def ai_name(path: Path) -> str:
    return re.sub(r"^CAP_ITEM_CANDIDATES_", "", path.stem) or path.stem


def constraint_key(notation: str, gamma: Mapping[str, Any], nid: str) -> str:
    """Khoá so sánh theo NGHĨA: mẫu, activity, tập điều kiện, thời hạn. Không chuyển được → 'LỖI: …'."""
    try:
        a = notation_to_ast(notation, gamma, nid)
    except NotationError as exc:
        return f"LỖI: {notation} ({str(exc)[:80]})"
    conds = sorted(f"{x} {o} {v!r}" for x, o, v in condition_set(a))
    return f"{a['template_name']}[{a['activation_activity']}, {a['target_activity']}] {conds} {time_exact(a)}"


def summarize(label: Optional[Mapping[str, Any]], gamma: Mapping[str, Any], nid: str) -> Dict[str, Any]:
    if label is None:
        return {"observable": "missing", "constraints": [], "tier4": None, "raw": None}
    obs = label["observable"]
    yes = obs == "yes"
    return {"observable": obs, "tier4": needs_reference(label["needs_ref"]) if yes else None,
            "constraints": sorted({constraint_key(c, gamma, nid) for c in label["constraints"]}) if yes else [],
            "raw": dict(label)}


def agree(per_ai: Mapping[str, Mapping[str, Any]]) -> bool:
    vals = list(per_ai.values())
    keys = ("observable", "tier4", "constraints")
    return all(v["observable"] not in ("missing", "blank") for v in vals) and \
        all(v[k] == vals[0][k] for v in vals for k in keys) and \
        not any(c.startswith("LỖI") for v in vals for c in v["constraints"])


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> Optional[float]:
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return round((po - pe) / (1 - pe), 4) if pe < 1 else 1.0


def compare(labels: Mapping[str, Mapping[str, Any]], order: Sequence[str], gamma: Mapping[str, Any],
            spot_min: int = 20, spot_frac: float = 0.1, seed: int = SEED) -> Dict[str, Any]:
    clauses = {nid: {ai: summarize(lab.get(nid), gamma, nid) for ai, lab in labels.items()} for nid in order}
    agreed = [nid for nid in order if agree(clauses[nid])]
    disagreed = [nid for nid in order if nid not in agreed]
    k = min(len(agreed), max(spot_min, math.ceil(spot_frac * len(agreed))))
    spot = sorted(random.Random(seed).sample(agreed, k), key=order.index)
    names = list(labels)
    kappas = {f"{x} vs {y}": cohen_kappa([clauses[n][x]["observable"] for n in order],
                                         [clauses[n][y]["observable"] for n in order])
              for x, y in itertools.combinations(names, 2)}
    obs_same = sum(len({clauses[n][a]["observable"] for a in names}) == 1 for n in order)
    return {"ais": names, "n": len(order), "agreed": agreed, "disagreed": disagreed, "spot_check": spot,
            "observable_agreement": round(obs_same / len(order), 4) if order else None,
            "full_agreement": round(len(agreed) / len(order), 4) if order else None,
            "kappa_observable": kappas, "clauses": clauses, "seed": seed}


def _line(nid: str, raw: Optional[Mapping[str, Any]]) -> str:
    if raw is None:
        return (f"{nid}: **Quan sát được:** ___ · **Ràng buộc mới:** ___ · **Cần điều tham chiếu:** ___ · "
                f"**Độ chắc chắn:** ___ · **Lý do:** ___")
    cons = "; ".join(raw["constraints"]) or "—"
    return (f"{nid}: **Quan sát được:** {OBS_VI.get(raw['observable'], raw['observable'])} · **Ràng buộc mới:** {cons}"
            f" · **Cần điều tham chiếu:** {raw['needs_ref'] or '—'} · **Độ chắc chắn:** {raw['confidence'] or '—'}"
            f" · **Lý do:** {raw['reason'] or '—'}")


def render_draft(result: Mapping[str, Any], order: Sequence[str]) -> str:
    first = result["ais"][0]
    out = ["# Nháp nhãn cuối — sinh bởi scripts/compare_cap_labels.py. Dòng bắt đầu bằng '#' bị bỏ qua khi đọc.",
           "# Khoản BẤT ĐỒNG: điền thay '___'. Khoản KIỂM NGẪU NHIÊN: đọc lại, sửa nếu sai; ghi lại số khoản đã sửa."]
    for nid in order:
        if nid in result["disagreed"]:
            out += [f"# CẦN NGƯỜI QUYẾT ({nid}) — xem DOI_CHIEU.md", _line(nid, None)]
        else:
            if nid in result["spot_check"]:
                out.append(f"# KIỂM NGẪU NHIÊN ({nid}) — các AI đồng thuận; xác nhận hoặc sửa")
            out.append(_line(nid, result["clauses"][nid][first]["raw"]))
    return "\n".join(out) + "\n"


def render_report(result: Mapping[str, Any], texts: Mapping[str, str]) -> str:
    ais = result["ais"]
    lines = [f"# Đối chiếu nhãn CAP giữa {len(ais)} AI: {', '.join(ais)}", "",
             f"- Số khoản: **{result['n']}** · đồng thuận hoàn toàn: **{len(result['agreed'])}** "
             f"({100 * (result['full_agreement'] or 0):.1f}%) · bất đồng (người quyết): **{len(result['disagreed'])}**",
             f"- Đồng thuận riêng câu (1) Quan sát được: {100 * (result['observable_agreement'] or 0):.1f}% · Cohen's kappa: "
             + ", ".join(f"{k} = {v}" for k, v in result["kappa_observable"].items()),
             f"- Kiểm ngẫu nhiên trong nhóm đồng thuận: **{len(result['spot_check'])}** khoản (seed {result['seed']}) — "
             f"tỉ lệ sai trong mẫu này phải báo cáo (hướng dẫn mục 10.6).", "", "## Khoản bất đồng", ""]
    for nid in result["disagreed"]:
        lines += [f"### {nid}", "", "> " + texts.get(nid, "")[:600] + ("…" if len(texts.get(nid, "")) > 600 else ""), ""]
        for ai in ais:
            s = result["clauses"][nid][ai]
            if s["raw"] is None:
                lines.append(f"- **{ai}**: (không có dòng cho khoản này)")
                continue
            r = s["raw"]
            lines.append(f"- **{ai}**: {OBS_VI.get(r['observable'], r['observable'])} · "
                         f"{'; '.join(r['constraints']) or '—'} · tham chiếu: {r['needs_ref'] or '—'} · "
                         f"{r['confidence'] or '—'} · *{r['reason']}*")
            errors = [c for c in s["constraints"] if c.startswith("LỖI")]
            lines += [f"  - ⚠ {e}" for e in errors]
        lines.append("")
    lines += ["## Kiểm ngẫu nhiên (đồng thuận)", "", ", ".join(result["spot_check"]) or "—", ""]
    return "\n".join(lines)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--labels", nargs="+", required=True)
    p.add_argument("--out-dir", default=str(DEFAULT_OUT))
    p.add_argument("--spot-min", type=int, default=20)
    p.add_argument("--spot-frac", type=float, default=0.1)
    p.add_argument("--candidates", default=str(CANDIDATES),
                   help="phiếu khoản (mặc định CAP); tập Đức: data/review/de_item_candidates.json + --out-dir riêng")
    args = p.parse_args()
    if Path(args.candidates).resolve() != CANDIDATES.resolve() and Path(args.out_dir).resolve() == DEFAULT_OUT.resolve():
        raise SystemExit("Phiếu khác CAP: cần --out-dir riêng (VD data/review/de_ai_compare) để không ghi đè đối chiếu CAP.")
    if len(args.labels) < 2:
        raise SystemExit("Cần ít nhất 2 file nhãn (2 AI).")
    labels: Dict[str, Dict[str, Any]] = {}
    for f in map(Path, args.labels):
        try:
            labels[ai_name(f)] = parse_label_sheet(f.read_bytes().decode("utf-8-sig"))
        except ValueError as exc:
            raise SystemExit(f"{f.name}: {exc}\nSửa định dạng (không đổi ý của AI) rồi chạy lại.") from exc
    cands = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    order = [c["node_id"] for c in cands]
    unknown = {ai: sorted(set(lab) - set(order)) for ai, lab in labels.items() if set(lab) - set(order)}
    if unknown:
        raise SystemExit(f"Có mã khoản không thuộc phiếu: {unknown}")
    result = compare(labels, order, json.loads(GAMMA.read_text(encoding="utf-8")), args.spot_min, args.spot_frac)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "doi_chieu.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "DOI_CHIEU.md").write_text(render_report(result, {c["node_id"]: c["text"] for c in cands}),
                                      encoding="utf-8")
    (out / "CAP_ITEM_CANDIDATES_final_draft.txt").write_text(render_draft(result, order), encoding="utf-8")
    sys.stdout.write(f"{result['n']} khoản · đồng thuận {len(result['agreed'])} · bất đồng {len(result['disagreed'])} · "
                     f"kiểm ngẫu nhiên {len(result['spot_check'])} · kappa {result['kappa_observable']}\nĐã ghi {out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
