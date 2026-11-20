"""
TN5–TN6, TN8 bộ CAP — bước CHẤM: so dự đoán (results/cap/predictions_<config>.json) với gold đã duyệt.

  TN5  độ chính xác từng cấu hình (khoản có ràng buộc: EQ; khoản bẫy: BASELESS), khoảng tin cậy Wilson 95%
  TN6  X (chỉ khoản luật) vs Y (Graph-RAG): so cặp McNemar chính xác — trên mọi khoản và riêng Tier 4
  TN8  ablation: Y vs Y-noL12 / Y-noL3 / Y-retry1 / X (= tắt graph)

Chạy:  python scripts/score_cap.py [--gold data/review/cap_gold_approved.json] [--pred-dir results/cap]
       --allow-candidate: chấm bằng gold CHƯA duyệt (kết quả gắn nhãn UNAPPROVED, chỉ để thử pipeline)
Ghi:   <pred-dir>/scores.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.cap_gold import scored_clauses  # noqa: E402
from src.evaluation.run_inputs import input_conflicts  # noqa: E402
from src.evaluation.cap_scoring import (  # noqa: E402
    always_baseless_predictions,
    paired_comparison,
    score_config,
    tier4_ids,
)

BASELINE = "always-BASELESS"

DEFAULT_GOLD = PROJECT_ROOT / "data" / "review" / "cap_gold_approved.json"
DEFAULT_PRED = PROJECT_ROOT / "results" / "cap"
Z_ABLATIONS = ["Z-noLegal", "Z-noProcess", "Z-noMass", "Z-noNotes", "Z-noHint"]  # mỗi cái so với Z
CONFIG_ORDER = ["X", "Y", "Y-noL12", "Y-noL3", "Y-retry1", "Y-noVac", "Y-noDomain", "Y-noDuty", "R", "N", "Z",
                *Z_ABLATIONS]
DE_CANDIDATES = PROJECT_ROOT / "data" / "review" / "de_item_candidates.json"
TEMPORAL = PROJECT_ROOT / "data" / "review" / "cap_temporal_versions.json"  # scripts/check_cap_versions.py


def eu_ref_subset(candidates_path: Path = DE_CANDIDATES) -> List[str]:
    """B4: khoản tập Đức có dẫn chiếu (trong phạm vi) tới 4 Quy định CAP — nơi duy nhất ngữ cảnh dẫn chiếu có thể
    tạo khác biệt; so R vs Y và X vs Y CHỈ trên các khoản này."""
    if not candidates_path.exists():
        return []
    items = json.loads(candidates_path.read_text(encoding="utf-8"))
    return sorted(c["node_id"] for c in items if any(r["kind"] == "eu" and r["in_scope"] for r in c.get("refs", [])))
ABLATIONS = ["Y-noL12", "Y-noL3", "Y-retry1", "Y-noVac", "Y-noDomain", "Y-noDuty"]  # "tắt graph" = X (TN6)
V2_CONFIGS = ["Z"]  # so với Y; docs/V2_DANG_KY_TRUOC.md — kết luận chỉ trên tập positive mới


def load_gold(path: Path, allow_candidate: bool) -> Dict[str, Any]:
    gold = json.loads(path.read_text(encoding="utf-8"))
    if gold.get("status") != "approved" and not allow_candidate:
        raise SystemExit(f"{path.name} chưa được duyệt (status={gold.get('status')}). Duyệt bằng "
                         "build_cap_gold.py --approve, hoặc thêm --allow-candidate để thử pipeline.")
    return gold


def load_predictions(pred_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Dự đoán từng cấu hình, BỎ khoản ERROR (lỗi hạ tầng). Dùng prediction_errors() để biết có khoản nào bị bỏ."""
    out = {}
    for cfg in CONFIG_ORDER:
        path = pred_dir / f"predictions_{cfg}.json"
        if path.exists():
            preds = json.loads(path.read_text(encoding="utf-8"))["predictions"]
            out[cfg] = {k: v for k, v in preds.items() if v["outcome"] != "ERROR"}
    return out


def prediction_errors(pred_dir: Path) -> Dict[str, List[str]]:
    """Khoản có outcome ERROR (mạng, hạn mức API, giám khảo trả sai định dạng) theo cấu hình."""
    out: Dict[str, List[str]] = {}
    for cfg in CONFIG_ORDER:
        path = pred_dir / f"predictions_{cfg}.json"
        if path.exists():
            bad = sorted(k for k, v in json.loads(path.read_text(encoding="utf-8"))["predictions"].items()
                         if v["outcome"] == "ERROR")
            if bad:
                out[cfg] = bad
    return out


def refuse_on_errors(pred_dir: Path, allow_errors: bool) -> None:
    """Khoản ERROR mà vẫn chấm sẽ bị tính FAILED (lỗi hạ tầng thành lỗi hệ thống) → mặc định từ chối."""
    errors = prediction_errors(pred_dir)
    if errors and not allow_errors:
        lines = "\n".join(f"  {cfg}: {len(ids)} khoản, VD {ids[:5]}" for cfg, ids in errors.items())
        raise SystemExit("Còn khoản ERROR (lỗi gọi API / giám khảo) — chạy lại run_cap_generation.py cùng cấu hình "
                         f"để thử lại, hoặc thêm --allow-errors (khoản ERROR sẽ bị tính là FAILED):\n{lines}")


def score_all(gold: Mapping[str, Any], preds: Mapping[str, Mapping[str, Any]],
              eu_subset: Optional[List[str]] = None) -> Dict[str, Any]:
    clauses = scored_clauses(gold)
    scores = {cfg: score_config(clauses, p) for cfg, p in preds.items()}
    t4 = tier4_ids(clauses)
    paired: Dict[str, Any] = {}
    if eu_subset:  # B4 — tập Đức
        subset = [n for n in eu_subset if n in clauses]
        for a in ("R", "X"):
            if a in scores and "Y" in scores:
                paired[f"B4 {a} vs Y (khoản Đức có dẫn chiếu EU, n={len(subset)})"] = paired_comparison(
                    scores[a], scores["Y"], subset)
    if "X" in scores and "Y" in scores:
        paired["TN6 X vs Y (mọi khoản)"] = paired_comparison(scores["X"], scores["Y"])
        paired["TN6 X vs Y (Tier 4)"] = paired_comparison(scores["X"], scores["Y"], t4)
    for abl in ABLATIONS:
        if "Y" in scores and abl in scores:
            paired[f"TN8 {abl} vs Y"] = paired_comparison(scores[abl], scores["Y"])
    for v2 in V2_CONFIGS:
        if "Y" in scores and v2 in scores:
            paired[f"v2 {v2} vs Y"] = paired_comparison(scores[v2], scores["Y"])
    for abl in Z_ABLATIONS:
        if "Z" in scores and abl in scores:
            paired[f"v2 {abl} vs Z"] = paired_comparison(scores[abl], scores["Z"])
    if "N" in scores and "Y" in scores:  # B6: tập Đức = đánh giá chính; CAP = tập phát triển (thiết kế sau khi xem CAP)
        label = "B6 N vs Y " + ("(tập Đức — chính)" if eu_subset is not None else "(CAP — tập phát triển)")
        paired[label] = paired_comparison(scores["N"], scores["Y"])
    baselines = {BASELINE: score_config(clauses, always_baseless_predictions(clauses))}
    if "Y" in scores:
        paired["Y vs luôn BASELESS"] = paired_comparison(scores["Y"], baselines[BASELINE])
    excluded: Dict[str, List[str]] = {}
    for nid, c in gold.get("clauses", {}).items():
        if nid not in clauses:
            excluded.setdefault(c.get("kind", "?"), []).append(nid)
    return {"gold_status": gold.get("status"), "gold_source": gold.get("source"),
            "n_scored": len(clauses), "n_tier4": len(t4), "configs": scores, "baselines": baselines,
            "paired": paired, "excluded": {k: sorted(v) for k, v in sorted(excluded.items())}}


def prediction_meta(pred_dir: Path) -> Dict[str, tuple]:
    """(bộ dữ liệu, model, nhà cung cấp) của từng file dự đoán."""
    out = {}
    for cfg in CONFIG_ORDER:
        path = pred_dir / f"predictions_{cfg}.json"
        if path.exists():
            d = json.loads(path.read_text(encoding="utf-8"))
            out[cfg] = (d.get("dataset", "cap"), d.get("model"), d.get("provider"))
    return out


def check_predictions(result: Mapping[str, Any], meta: Mapping[str, tuple], allow_missing: bool,
                      allow_mixed: bool) -> None:
    """Rà soát 2026-11-18 E-H1: cấu hình thiếu dự đoán (bị tính FAILED) hoặc các file thuộc lần chạy khác nhau
    (bộ dữ liệu / model / nhà cung cấp) → dừng, trừ khi cho phép rõ ràng."""
    missing = {c: s["missing_predictions"] for c, s in result["configs"].items() if s["missing_predictions"]}
    if missing and not allow_missing:
        lines = "\n".join(f"  {c}: thiếu {len(ids)} khoản, VD {ids[:5]}" for c, ids in missing.items())
        raise SystemExit("Có cấu hình thiếu dự đoán cho khoản của gold (sẽ bị tính FAILED) — chạy đủ khoản, kiểm "
                         f"--gold / --pred-dir, hoặc thêm --allow-missing:\n{lines}")
    if len(set(meta.values())) > 1 and not allow_mixed:
        raise SystemExit(f"Các file dự đoán thuộc lần chạy khác nhau (bộ dữ liệu, model, nhà cung cấp): {meta}. "
                         "Tách thư mục, hoặc thêm --allow-mixed.")


def check_inputs(pred_dir: Path, allow_mixed: bool) -> Dict[str, Any]:
    """A2: các khoản / cấu hình sinh từ các phiên bản DỮ LIỆU khác nhau (dấu SHA-256, src/evaluation/run_inputs.py)
    → dừng, trừ khi --allow-mixed. Khoản sinh trước khi có dấu: chỉ báo số lượng (không kết luận được)."""
    docs = {cfg: json.loads((pred_dir / f"predictions_{cfg}.json").read_text(encoding="utf-8"))
            for cfg in CONFIG_ORDER if (pred_dir / f"predictions_{cfg}.json").exists()}
    found = input_conflicts(docs)
    found["code_versions"] = {cfg: (d.get("code") or {}).get("sha256") for cfg, d in docs.items()}
    if len({v for v in found["code_versions"].values() if v}) > 1:
        sys.stdout.write(f"Chú ý: các cấu hình sinh bằng PHIÊN BẢN CODE khác nhau: {found['code_versions']}\n")
    if found["unstamped"]:
        sys.stdout.write(f"Chú ý: khoản chưa có dấu dữ liệu (sinh trước 2026-11-20): {found['unstamped']}\n")
    if (found["within"] or found["across"]) and not allow_mixed:
        raise SystemExit("Dự đoán sinh từ các phiên bản dữ liệu KHÁC nhau — số liệu không so được:\n"
                         f"  trong cùng file (số khoản khác bộ dữ liệu của file): {found['within'] or '—'}\n"
                         f"  giữa các cấu hình (đầu vào: cấu hình → sha256): {found['across'] or '—'}\n"
                         "Chạy lại các cấu hình đó với --force (cache giữ câu trả lời không đổi), "
                         "hoặc thêm --allow-mixed.")
    return found


def _fmt(r: Mapping[str, Any]) -> str:
    if not r["n"]:
        return "   —        "
    return f"{r['correct']:>3}/{r['n']:<3} {100 * r['rate']:5.1f}% [{100 * r['ci95'][0]:.0f}–{100 * r['ci95'][1]:.0f}]"


def temporal_sensitivity(gold: Mapping[str, Any], preds: Mapping[str, Mapping[str, Any]],
                         amended: Sequence[str]) -> Dict[str, Any]:
    """B5 (độ nhạy, mô tả): chấm lại CAP sau khi BỎ các khoản có sửa đổi nội dung trong 2015–2017 (hệ thống và gold
    đều dùng bản gốc). Kết luận không đổi → hiệu lực thời gian không chi phối kết quả."""
    kept = {k: v for k, v in gold["clauses"].items() if k not in set(amended)}
    res = score_all({**gold, "clauses": kept}, preds)
    return {"excluded": sorted(set(amended) & set(gold["clauses"])), "n_scored": res["n_scored"],
            "overall": {c: s["overall"] for c, s in {**res["configs"], **res["baselines"]}.items()},
            "paired": res["paired"]}


def print_temporal(sens: Mapping[str, Any]) -> None:
    w = sys.stdout.write
    w(f"\nB5 — độ nhạy theo hiệu lực thời gian: bỏ {len(sens['excluded'])} khoản có sửa đổi 2015–2017 "
      f"(còn {sens['n_scored']} khoản chấm):\n")
    for cfg, r in sens["overall"].items():
        w(f"  {cfg:<16}{_fmt(r)}\n")
    for name, pc in sens["paired"].items():
        w(f"  {name:<28} n={pc['n']:<4} chỉ trái={len(pc['only_a']):<3} chỉ phải={len(pc['only_b']):<3} "
          f"p={pc['p_value']}\n")


def print_tables(result: Mapping[str, Any]) -> None:
    w = sys.stdout.write
    if result["gold_status"] != "approved":
        w("!!! GOLD CHƯA DUYỆT (UNAPPROVED) — số dưới đây chỉ để thử pipeline, KHÔNG dùng cho bài !!!\n")
    w(f"Khoản được chấm: {result['n_scored']} (Tier 4: {result['n_tier4']})\n")
    for kind, ids in result.get("excluded", {}).items():
        w(f"  KHÔNG chấm ({kind}): {len(ids)} khoản — {', '.join(ids[:8])}{' …' if len(ids) > 8 else ''}\n")
    w("\n")
    w(f"{'Cấu hình':<16}{'Tổng':<24}{'Có ràng buộc (EQ)':<24}{'Tier 4':<24}{'Bẫy (BASELESS)':<24}"
      f"{'Cân bằng':<10}\n")
    rows = {**result["configs"], **{f"[{k}]": v for k, v in result.get("baselines", {}).items()}}
    for cfg, s in rows.items():
        bal = "—" if s.get("balanced") is None else f"{100 * s['balanced']:.1f}%"
        w(f"{cfg:<16}{_fmt(s['overall']):<24}{_fmt(s['positive']):<24}{_fmt(s['tier4']):<24}{_fmt(s['trap']):<24}"
          f"{bal:<10}\n")
    w("Cân bằng = trung bình(tỉ lệ đúng có ràng buộc, tỉ lệ đúng bẫy). [always-BASELESS] = mức chuẩn tầm thường.\n")
    w("\nPhân loại khoản có ràng buộc:\n")
    for cfg, s in result["configs"].items():
        w(f"  {cfg:<10}{s['positive']['classes']}\n")
    w("\nB1 — chấm theo thành phần trên khoản có ràng buộc (lồng nhau: issue ⊇ rule ⊇ application ⊇ conclusion):\n")
    for cfg, s in result["configs"].items():
        comp = s.get("components") or {}
        w(f"  {cfg:<12}" + "  ".join(f"{lv} {_fmt(comp[lv])}" for lv in ("issue", "rule", "application", "conclusion")
                                      if lv in comp) + "\n")
    w("\nSo cặp (McNemar chính xác; only_a = chỉ cấu hình trái đúng):\n")
    for name, pc in result["paired"].items():
        w(f"  {name:<28} n={pc['n']:<4} cả hai đúng={pc['both']:<4} chỉ trái={len(pc['only_a']):<3} "
          f"chỉ phải={len(pc['only_b']):<3} p={pc['p_value']}\n")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--gold", default=str(DEFAULT_GOLD))
    p.add_argument("--pred-dir", default=str(DEFAULT_PRED))
    p.add_argument("--allow-candidate", action="store_true")
    p.add_argument("--allow-errors", action="store_true", help="vẫn chấm khi còn khoản ERROR (tính là FAILED)")
    p.add_argument("--allow-missing", action="store_true", help="vẫn chấm khi cấu hình thiếu khoản (tính FAILED)")
    p.add_argument("--allow-mixed", action="store_true", help="vẫn chấm khi file thuộc các lần chạy khác nhau")
    args = p.parse_args()
    gold = load_gold(Path(args.gold), args.allow_candidate)
    refuse_on_errors(Path(args.pred_dir), args.allow_errors)
    preds = load_predictions(Path(args.pred_dir))
    if not preds:
        raise SystemExit(f"Chưa có predictions_*.json trong {args.pred_dir} — chạy run_cap_generation.py trước.")
    meta = prediction_meta(Path(args.pred_dir))
    is_de = any(m[0] == "de" for m in meta.values())
    result = score_all(gold, preds, eu_ref_subset() if is_de else None)
    if not is_de and TEMPORAL.exists():
        amended = list(json.loads(TEMPORAL.read_text(encoding="utf-8"))["amended"])
        result["sensitivity_temporal"] = temporal_sensitivity(gold, preds, amended)
    check_predictions(result, meta, args.allow_missing, args.allow_mixed)
    result["inputs_check"] = check_inputs(Path(args.pred_dir), args.allow_mixed)
    out = Path(args.pred_dir) / "scores.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print_tables(result)
    if "sensitivity_temporal" in result:
        print_temporal(result["sensitivity_temporal"])
    sys.stdout.write(f"\nĐã ghi {out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
