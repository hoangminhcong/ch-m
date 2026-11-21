"""
T2 (kiểm thử 2026-11-20) — bất biến trên MỌI đầu ra của pipeline 'post' trong một thư mục kết quả.

Mỗi bất biến là điều PHẢI đúng nếu các bước nhất quán với nhau; vi phạm = lỗi code hoặc file lẫn lần chạy.
  dự đoán      summary = đếm lại; RULE có AST, vòng cuối PASSED, (cấu hình bật Tầng 1–2) AST còn qua Tầng 1–2 với Γ
               hiện tại; BASELESS không có AST, vòng cuối là kết luận BASELESS; FAILED vòng cuối FAILED_*; số vòng
               liên tục 1..n; llm_rounds = số vòng (khoản có trường này); khoản có trong phiếu
  chấm         per_clause = chấm lại; tổng lớp positive = số khoản positive; overall = positive + bẫy; mức chuẩn
               "luôn BASELESS" đúng định nghĩa; p-value = McNemar tính lại
  phễu         tổng vòng và outcome = đếm lại từ trajectory
  KG / xuất    số VerifiedConstraint = số RULE; KG đầy đủ không có cạnh treo, không trùng id
  proof trace  mọi RULE có trace; .decl của trace = AST
  REVIEW       đủ luật; bảng giữ lại cộng đúng; "sai trên bẫy" (giữ tất cả) = chấm
  TN7          tp + fp + fn + tn = số hồ sơ
Không gọi API, không nạp log; chỉ đọc file.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from ..mde.constraint_ast import DeclareConstraintAST
from ..mde.typing_environment import check_layer1_and_layer2
from .cap_scoring import mcnemar_exact, score_clause

BASELESS_ENDS = ("DECLINED_NO_OBLIGATION", "DETECTED_BASELESS_TRAP", "DECLINED_NORM_TYPE")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_one_prediction(where: str, p: Mapping[str, Any], gamma: Mapping[str, Any],
                          chunk: Optional[Mapping[str, Any]], l1_l2_enabled: bool) -> List[str]:
    bad: List[str] = []
    traj = p.get("trajectory") or []
    last = traj[-1]["status"] if traj else None
    if [t.get("round") for t in traj] != list(range(1, len(traj) + 1)):
        bad.append(f"{where}: số vòng không liên tục")
    if "llm_rounds" in p and p["llm_rounds"] != len(traj):
        bad.append(f"{where}: llm_rounds={p['llm_rounds']} ≠ {len(traj)} vòng")
    if p["outcome"] == "RULE":
        if not p.get("ast"):
            return bad + [f"{where}: RULE không có AST"]
        if last != "PASSED":
            bad.append(f"{where}: RULE nhưng vòng cuối {last}")
        if l1_l2_enabled:
            ok, res = check_layer1_and_layer2(json.dumps(p["ast"]), gamma, chunk)
            if not ok:
                bad.append(f"{where}: RULE không còn qua Tầng 1–2 với Γ hiện tại: {str(res)[:160]}")
    elif p["outcome"] == "BASELESS":
        if last not in BASELESS_ENDS:
            bad.append(f"{where}: BASELESS nhưng vòng cuối {last}")
        if p.get("ast") is not None:
            bad.append(f"{where}: BASELESS mà vẫn có AST")
    elif p["outcome"] == "FAILED" and last is not None and not last.startswith("FAILED"):
        bad.append(f"{where}: FAILED nhưng vòng cuối {last}")
    return bad


def check_prediction_file(cfg: str, doc: Mapping[str, Any], gamma: Mapping[str, Any],
                          candidates: Mapping[str, Mapping[str, Any]], l1_l2_enabled: bool = True) -> List[str]:
    bad: List[str] = []
    preds = doc["predictions"]
    counted = {k: v for k, v in Counter(p["outcome"] for p in preds.values()).items() if v}
    if {k: v for k, v in (doc.get("summary") or {}).items() if v} != counted:
        bad.append(f"{cfg}: summary {doc.get('summary')} ≠ đếm lại {counted}")
    for nid, p in preds.items():
        if nid not in candidates:
            bad.append(f"{cfg}/{nid}: khoản không có trong phiếu")
        if p["outcome"] != "ERROR":
            bad += _check_one_prediction(f"{cfg}/{nid}", p, gamma, candidates.get(nid), l1_l2_enabled)
    return bad


def check_scores(scores: Mapping[str, Any], preds_by_cfg: Mapping[str, Mapping[str, Any]],
                 gold: Mapping[str, Mapping[str, Any]]) -> List[str]:
    bad: List[str] = []
    pos = [n for n, g in gold.items() if g["kind"] == "positive"]
    for cfg, sc in scores["configs"].items():
        preds = {k: v for k, v in preds_by_cfg.get(cfg, {}).items() if v["outcome"] != "ERROR"}
        for nid, cls in sc["per_clause"].items():
            if nid in gold and cls != score_clause(gold[nid], preds.get(nid)):
                bad.append(f"{cfg}/{nid}: lớp chấm {cls} ≠ chấm lại {score_clause(gold[nid], preds.get(nid))}")
        if sum(sc["positive"]["classes"].values()) != len(pos):
            bad.append(f"{cfg}: tổng lớp positive ≠ {len(pos)} khoản positive")
        if sc["overall"]["correct"] != sc["positive"]["correct"] + sc["trap"]["correct"]:
            bad.append(f"{cfg}: overall ≠ positive + bẫy")
        if sc["overall"]["n"] != len(gold):
            bad.append(f"{cfg}: overall n={sc['overall']['n']} ≠ {len(gold)} khoản chấm")
    for name, pc in scores.get("paired", {}).items():
        p = mcnemar_exact(len(pc["only_a"]), len(pc["only_b"]))
        if abs(round(p, 4) - pc["p_value"]) > 1e-9:
            bad.append(f"{name}: p-value {pc['p_value']} ≠ tính lại {round(p, 4)}")
        if pc["both"] + len(pc["only_a"]) + len(pc["only_b"]) > pc["n"]:
            bad.append(f"{name}: cả hai + chỉ trái + chỉ phải > n")
    base = scores.get("baselines", {}).get("always-BASELESS")
    if base and ((base["trap"]["n"] and base["trap"]["rate"] != 1.0) or base["positive"]["correct"] != 0):
        bad.append("mức chuẩn 'luôn BASELESS' không đúng định nghĩa")
    return bad


def check_funnel(funnel: Mapping[str, Any], preds_by_cfg: Mapping[str, Mapping[str, Any]]) -> List[str]:
    bad = []
    for cfg, fu in funnel.items():
        preds = preds_by_cfg.get(cfg)
        if preds is None:
            continue
        if fu["llm_rounds"] != sum(len(p.get("trajectory") or []) for p in preds.values()):
            bad.append(f"{cfg}: phễu llm_rounds lệch với trajectory")
        if fu["outcomes"] != dict(Counter(p["outcome"] for p in preds.values())):
            bad.append(f"{cfg}: phễu outcomes lệch")
    return bad


def _check_kg(cfg: str, kg: Mapping[str, Any], n_rules: int) -> List[str]:
    bad = []
    ids = Counter(x["id"] for x in kg["nodes"])
    dangling = [e for e in kg["edges"] if e["source"] not in ids or e["target"] not in ids]
    if dangling:
        bad.append(f"{cfg}: KG đầy đủ có {len(dangling)} cạnh treo, VD {dangling[0]}")
    dup = [k for k, v in ids.items() if v > 1]
    if dup:
        bad.append(f"{cfg}: KG đầy đủ trùng id node {dup[:3]}")
    if kg["meta"]["layers"].get("constraint") != n_rules:
        bad.append(f"{cfg}: KG đầy đủ có {kg['meta']['layers'].get('constraint')} ràng buộc ≠ {n_rules} RULE")
    return bad


def _check_review(cfg: str, rf: Mapping[str, Any], rules: Mapping[str, Any],
                  scores: Optional[Mapping[str, Any]]) -> List[str]:
    bad = []
    if set(rf["rules"]) != set(rules):
        bad.append(f"{cfg}: nhãn REVIEW cho {len(rf['rules'])} luật ≠ {len(rules)} RULE")
    for row in rf["risk_coverage"]:
        if "false_on_trap" in row and (row["false_on_trap"] + row["correct_on_positive"]
                                       + row["wrong_on_positive"] + row["not_scored"] != row["kept"]):
            bad.append(f"{cfg}: bảng giữ lại k={row['keep_if_level_below']} cộng không ra số giữ lại")
    keep_all = max(rf["risk_coverage"], key=lambda r: r["keep_if_level_below"], default=None)
    if scores is not None and keep_all and "false_on_trap" in keep_all and cfg in scores["configs"]:
        expected = scores["configs"][cfg]["trap"]["classes"]["TRAP_FALSE_RULE"]
        if keep_all["false_on_trap"] != expected:
            bad.append(f"{cfg}: bảng giữ lại (giữ tất cả) sai trên bẫy {keep_all['false_on_trap']} ≠ chấm {expected}")
    return bad


def check_constraint_outputs(cfg: str, pred_dir: Path, rules: Mapping[str, Mapping[str, Any]],
                             scores: Optional[Mapping[str, Any]]) -> List[str]:
    """Các file của một cấu hình đã xuất ràng buộc (export, KG đầy đủ, proof trace, REVIEW). Thiếu file → bỏ qua."""
    bad: List[str] = []
    vc_path = pred_dir / f"verified_constraints_{cfg}.json"
    if vc_path.exists():
        n = sum(1 for x in _load(vc_path)["nodes"] if x["label"] == "VerifiedConstraint")
        if n != len(rules):
            bad.append(f"{cfg}: xuất {n} VerifiedConstraint ≠ {len(rules)} RULE")
    if (pred_dir / f"kg_full_{cfg}.json").exists():
        bad += _check_kg(cfg, _load(pred_dir / f"kg_full_{cfg}.json"), len(rules))
    pt_path = pred_dir / f"proof_traces_{cfg}.json"
    if pt_path.exists():
        traced = {t["clause"]: t for t in _load(pt_path)["traces"]}
        for nid, p in rules.items():
            if nid not in traced:
                bad.append(f"{cfg}/{nid}: luật không có proof trace")
            elif traced[nid]["decl"] != DeclareConstraintAST.model_validate(p["ast"]).to_declare4py_line().strip():
                bad.append(f"{cfg}/{nid}: .decl trong proof trace ≠ AST")
    if (pred_dir / f"review_flags_{cfg}.json").exists():
        bad += _check_review(cfg, _load(pred_dir / f"review_flags_{cfg}.json"), rules, scores)
    return bad


def check_conformance(conf: Mapping[str, Any]) -> List[str]:
    bad = []
    for nid, c in conf.get("clauses", {}).items():
        for cfg, r in (c.get("pred") or {}).items():
            if r["tp"] + r["fp"] + r["fn"] + r["tn"] != conf["cases"]:
                bad.append(f"TN7 {nid}/{cfg}: tp + fp + fn + tn ≠ {conf['cases']} hồ sơ")
    return bad


def check_outputs(pred_dir: Path, gold: Optional[Mapping[str, Mapping[str, Any]]], gamma: Mapping[str, Any],
                  candidates: Mapping[str, Mapping[str, Any]], configs: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """Mọi bất biến trên thư mục kết quả. configs = CONFIGS của run_cap_generation (biết cấu hình nào tắt Tầng 1–2)."""
    bad: List[str] = []
    docs = {f.stem.split("_", 1)[1]: _load(f) for f in sorted(pred_dir.glob("predictions_*.json"))}
    preds_by_cfg = {cfg: d["predictions"] for cfg, d in docs.items()}
    for cfg, doc in docs.items():
        enabled = (configs.get(cfg) or {}).get("enable_l1_l2", True)
        bad += check_prediction_file(cfg, doc, gamma, candidates, l1_l2_enabled=enabled)
    scores = _load(pred_dir / "scores.json") if (pred_dir / "scores.json").exists() else None
    if scores is not None and gold is not None:
        bad += check_scores(scores, preds_by_cfg, gold)
    if (pred_dir / "verification_funnel.json").exists():
        bad += check_funnel(_load(pred_dir / "verification_funnel.json"), preds_by_cfg)
    for cfg, preds in preds_by_cfg.items():
        rules = {n: p for n, p in preds.items() if p["outcome"] == "RULE"}
        bad += check_constraint_outputs(cfg, pred_dir, rules, scores if gold is not None else None)
    if (pred_dir / "conformance.json").exists():
        bad += check_conformance(_load(pred_dir / "conformance.json"))
    return {"configs": sorted(docs), "violations": bad}
