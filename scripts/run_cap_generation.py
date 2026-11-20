"""
TN5–TN6, TN8 bộ CAP — bước SINH: chạy vòng lặp NSAI (LLM → AST → Tầng 1–2 (Γ BPIC2018) → Tầng 3) cho mọi khoản
của phiếu CAP, theo một cấu hình. Script KHÔNG đọc gold / phiếu nhãn (chấm điểm ở scripts/score_cap.py), nên
không thể rò đáp án vào prompt và chạy được trước khi có nhãn.

Cấu hình (mọi cấu hình đều có Tầng 1–3 + C, E, B, D trừ phần ghi "tắt"):
  X           chỉ khoản luật                                (RAG phẳng — đường cơ sở; = "tắt graph" của TN8)
  Y           khoản luật + khoản được dẫn chiếu qua đồ thị  (Graph-RAG, cấu hình chính)
  Y-noL12     Y, tắt Tầng 1–2 tự sửa (lỗi cú pháp → dừng)   (TN8)
  Y-noL3      Y, tắt Tầng 3 (Entity Matcher + giám khảo)    (TN8)
  Y-retry1    Y, chỉ 1 vòng (không tự sửa)                  (TN8)
  Y-noVac     Y, tắt B  kiểm rỗng trên log                  (TN8)
  Y-noDomain  Y, tắt C  miền giá trị Γ và E  năm trong luật (TN8)
  Y-noDuty    Y, tắt D  phân tích nghĩa vụ (prompt CAP cũ)  (TN8)
  Z           v2: Y + định nghĩa/phạm vi quốc gia + kiểm tầng Tiến trình + ghi chú activity + gợi ý loại giấy tờ
              (docs/V2_DANG_KY_TRUOC.md; cần scripts/build_process_profile.py, build_cap_legal_v2.py; ontology
              data/review/bpic2018_ontology.json chỉ dùng khi đã duyệt)
Kiểm B cần nạp log BPIC2018 (~2,5 phút, một lần mỗi lần chạy).

Chạy:  python scripts/run_cap_generation.py --config Y [--limit 5] [--only R809:Art13(1)] [--cache-only]
Đọc:   data/review/cap_item_candidates.json (chỉ node_id/văn bản), data/processed/cap_legal_graph.json,
       data/processed/gamma_bpic2018.json, data/interim/bpic2018_{events,cases}.parquet (kiểm B),
       .env (GROQ_API_KEY hoặc CEREBRAS_API_KEY theo --provider — không in ra)
Ghi:   <out-dir>/predictions_<config>.json, cache LLM ở --cache-file (mặc định <out-dir>/llm_cache_<config>.json)
Cerebras:  python scripts/run_cap_generation.py --provider cerebras --out-dir results/cap_cerebras --config Y
           (mỗi cấu hình một cửa sổ terminal để chạy song song; thêm --min-interval 13 nếu hạn mức chỉ 5 request/phút;
            cửa sổ dùng key thứ hai: thêm --key-var CEREBRAS_API_KEY_2 — mỗi cấu hình chạy trọn trên MỘT key)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.atomic_json import write_json_atomic  # noqa: E402
from src.evaluation.cap_scoring import BASELESS, FAILED, RULE  # noqa: E402
from src.evaluation.run_inputs import changed_inputs, code_version, fingerprint, inputs_id  # noqa: E402
from src.evaluation.real_llm_client import RealLLMClient, run_single_rule_with_real_llm  # noqa: E402
from src.kg.mapping_graph_builder import load_bridge  # noqa: E402
from src.kg.ontology_mapping import hint_from_doctypes, load_ontology  # noqa: E402
from src.neural.graph_context import (  # noqa: E402
    BM25ClauseIndex,
    LegalGraphIndex,
    rag_context_chunk,
    clause_only_chunk,
    graph_context_chunk,
    graph_context_chunk_v2,
)
from src.symbolic.domain_profiles import (  # noqa: E402
    CAP_PROFILE, CAP_PROFILE_NO_DUTY, CAP_PROFILE_NORM, german_profile)
from src.symbolic.norm_frame import NormFrame  # noqa: E402
from src.symbolic.log_grounding import LogGroundingChecker  # noqa: E402
from src.symbolic.process_checks import MASS_VIOLATION_THRESHOLD, MassViolationChecker, ProcessV2  # noqa: E402

PROCESSED = PROJECT_ROOT / "data" / "processed"
INTERIM = PROJECT_ROOT / "data" / "interim"
CANDIDATES = PROJECT_ROOT / "data" / "review" / "cap_item_candidates.json"
DEFAULT_OUT = PROJECT_ROOT / "results" / "cap"
DEFAULT_MAX_RETRY = 5
TIMEZONE = "Europe/Berlin"  # như TN7 (run_cap_conformance.py)
# graph: ngữ cảnh đồ thị · vacuity: B · domain: C + E · duty: D · còn lại: tham số vòng lặp
_FULL = {"graph": True, "vacuity": True, "domain": True, "duty": True}
CONFIGS: Dict[str, Dict[str, Any]] = {
    "X": {**_FULL, "graph": False},
    "Y": dict(_FULL),
    "Y-noL12": {**_FULL, "enable_l1_l2": False},
    "Y-noL3": {**_FULL, "enable_l3_roundtrip": False},
    "Y-retry1": {**_FULL, "max_retry": 1},
    "Y-noVac": {**_FULL, "vacuity": False},
    "Y-noDomain": {**_FULL, "domain": False},
    "Y-noDuty": {**_FULL, "duty": False},
    # B4 (đăng ký bổ sung, đã duyệt 2026-11-19): RAG truyền thống — như Y nhưng ngữ cảnh = BM25 (ngân sách khớp Y)
    "R": {**_FULL, "rag": "bm25"},
    # B6 (đăng ký trước 2026-11-20): Y + khung chuẩn tắc có danh mục đóng (src/symbolic/norm_frame.py), cần ontology
    # đã duyệt (N4 = hỗ trợ từ KG qua MAPS_TO). CAP = tập phát triển, tập Đức = tập đánh giá chính.
    "N": {**_FULL, "norm": True},
    # v2 (docs/V2_DANG_KY_TRUOC.md): Y + định nghĩa / phạm vi quốc gia trong ngữ cảnh, kiểm tầng Tiến trình
    # (thuộc tính, năm, vi phạm hàng loạt), ghi chú activity cho giám khảo, gợi ý loại giấy tờ (ontology đã duyệt)
}
# Thành phần v2 (mỗi ablation tắt đúng một nhóm): legal = định nghĩa + phạm vi quốc gia trong ngữ cảnh;
# process = kiểm thuộc tính / năm / vi phạm hàng loạt; mass = riêng vi phạm hàng loạt; notes = ghi chú activity cho
# giám khảo; hint = dòng gợi ý loại giấy tờ (MAPS_TO, cần ontology đã duyệt).
V2_PARTS = ("v2_legal", "v2_process", "v2_mass", "v2_notes", "v2_hint")
_Z = {**_FULL, "v2": True, **{part: True for part in V2_PARTS}}
CONFIGS["Z"] = _Z
for _name, _part in (("Z-noLegal", "v2_legal"), ("Z-noProcess", "v2_process"), ("Z-noMass", "v2_mass"),
                     ("Z-noNotes", "v2_notes"), ("Z-noHint", "v2_hint")):
    CONFIGS[_name] = {**_Z, _part: False}
FEATURE_KEYS = ("graph", "vacuity", "domain", "duty", "v2", "rag", "norm", *V2_PARTS)
PROFILE_V2 = PROCESSED / "bpic2018_process_profile.json"
LEGAL_V2 = PROCESSED / "cap_legal_graph_v2.json"
ONTOLOGY = PROJECT_ROOT / "data" / "review" / "bpic2018_ontology.json"
GAMMA = PROCESSED / "gamma_bpic2018.json"
# tầng Cầu nối của KG (scripts/build_mapping_graph.py) — NGUỒN DUY NHẤT của MAPS_TO lúc sinh (gợi ý Z, kiểm N4)
MAPPING_GRAPHS = {"cap": PROCESSED / "cap_mapping_graph.json", "de": PROCESSED / "de_mapping_graph.json"}
LOG_EVENTS = INTERIM / "bpic2018_events.parquet"
LOG_CASES = INTERIM / "bpic2018_cases.parquet"
# Bộ khoản: cap = 4 Quy định EU (v1); de = tập Đức InVeKoSV + DirektZahlDurchfV (docs/V2_DANG_KY_TRUOC.md mục 5.1).
# (phiếu khoản, đồ thị cho Y, đồ thị cho Z). Tập Đức: Z dùng cùng đồ thị Đức (định nghĩa/phạm vi chỉ có cho CAP).
DATASETS = {"cap": (CANDIDATES, PROCESSED / "cap_legal_graph.json", LEGAL_V2),
            "de": (PROJECT_ROOT / "data" / "review" / "de_item_candidates.json", PROCESSED / "de_legal_graph.json",
                   PROCESSED / "de_legal_graph.json")}
# Cùng mô hình gpt-oss-120b, khác nơi chạy. Kết quả hai nhà cung cấp KHÔNG trộn: dùng --out-dir riêng.
PROVIDERS: Dict[str, tuple] = {
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b"),
    "cerebras": ("https://api.cerebras.ai/v1", "gpt-oss-120b"),
}


class CacheOnlyClient(RealLLMClient):
    """Chỉ phát lại cache (không gọi API, không ngủ chờ); thiếu cache → lỗi ngay."""

    def chat_json(self, messages: Any, temperature: float = 0.0, **kwargs: Any) -> str:
        msg_list = messages if not isinstance(messages, str) else [
            {"role": "system", "content": "You are a formal compliance semantic verifier. "
                                          "Always respond with a valid JSON object."},
            {"role": "user", "content": messages}]
        key = self._make_key(msg_list, temperature)
        if key not in self.cache:
            raise LookupError("cache miss")
        return self.cache[key]


def outcome_of(result: Mapping[str, Any]) -> str:
    """RULE / BASELESS / FAILED. BASELESS = giám khảo kết luận BASELESS, hoặc LLM tự kết luận không có nghĩa vụ (D)."""
    status = result["trajectory"][-1]["status"] if result.get("trajectory") else "PASSED"
    if status in ("DECLINED_NO_OBLIGATION", "DECLINED_NORM_TYPE"):
        return BASELESS
    if result.get("final_ast") is None:
        return FAILED
    return BASELESS if status == "DETECTED_BASELESS_TRAP" else RULE


def schema_for(gamma: Mapping[str, Any], config: str) -> Dict[str, Any]:
    """Γ cho cấu hình: tắt C (Y-noDomain) = bỏ khóa 'domain' khỏi mọi thuộc tính."""
    if CONFIGS[config]["domain"]:
        return dict(gamma)
    strip = lambda attrs: {k: {f: v for f, v in m.items() if f != "domain"} for k, m in attrs.items()}  # noqa: E731
    return {**gamma, "case_attributes": strip(gamma["case_attributes"]),
            "event_attributes": strip(gamma["event_attributes"])}


def load_grounding() -> LogGroundingChecker:
    """Engine trên toàn log BPIC2018 (tên activity ghép, giờ Đức) cho kiểm B."""
    import pandas as pd

    from src.kg.process_graph_builder import with_composite_activity
    from src.symbolic.declare4py_verifier import Declare4Py

    events = with_composite_activity(pd.read_parquet(LOG_EVENTS))
    cases = pd.read_parquet(LOG_CASES)
    return LogGroundingChecker(Declare4Py(events, cases=cases, timezone=TIMEZONE, calendar_periods=True))


def context_builder(config: str, dataset: str = "cap") -> Callable[[Mapping[str, Any]], Dict[str, Any]]:
    if not CONFIGS[config]["graph"]:
        return clause_only_chunk
    _, graph_path, graph_v2_path = DATASETS[dataset]
    if CONFIGS[config].get("v2") and CONFIGS[config].get("v2_legal"):
        legal_v2 = json.loads(graph_v2_path.read_text(encoding="utf-8"))
        index_v2 = LegalGraphIndex(legal_v2)
        return lambda chunk: graph_context_chunk_v2(chunk, index_v2, legal_v2)
    index = LegalGraphIndex(json.loads(graph_path.read_text(encoding="utf-8")))
    if CONFIGS[config].get("rag") == "bm25":
        bm25 = BM25ClauseIndex(index)
        return lambda chunk: rag_context_chunk(chunk, index, bm25)
    return lambda chunk: graph_context_chunk(chunk, index)


def input_paths(config: str, dataset: str = "cap") -> Dict[str, Path]:
    """Mọi file DỮ LIỆU mà cấu hình đọc (để ghi dấu, src/evaluation/run_inputs.py). Cùng file → cùng tên ở mọi
    cấu hình, để so được giữa các cấu hình (VD Y và R cùng 'legal_graph')."""
    cfg = CONFIGS[config]
    items, graph, graph_v2 = DATASETS[dataset]
    paths = {"clauses": items, "gamma": GAMMA}
    if cfg["graph"]:
        if cfg.get("v2") and cfg.get("v2_legal"):
            paths["legal_graph_v2"] = graph_v2
        else:
            paths["legal_graph"] = graph
    if cfg["vacuity"]:
        paths.update(log_events=LOG_EVENTS, log_cases=LOG_CASES)
    if cfg.get("v2"):
        paths.update(process_profile=PROFILE_V2, ontology=ONTOLOGY, mapping_graph=MAPPING_GRAPHS[dataset])
    if cfg.get("norm"):
        paths["mapping_graph"] = MAPPING_GRAPHS[dataset]
    return paths


def load_process_v2(grounding: Any, config: str = "Z") -> ProcessV2:
    """Hồ sơ tầng Tiến trình + kiểm vi phạm hàng loạt (dùng chung engine với B) + ontology (None nếu chưa duyệt).
    Công tắc theo cấu hình (ablation của Z)."""
    cfg = CONFIGS[config]
    profile = json.loads(PROFILE_V2.read_text(encoding="utf-8"))
    mass = MassViolationChecker(grounding.engine) if grounding is not None else None
    return ProcessV2(profile=profile, mass=mass, ontology=load_ontology(ONTOLOGY),
                     check_attribute=cfg["v2_process"], check_year=cfg["v2_process"],
                     check_mass=cfg["v2_process"] and cfg["v2_mass"], judge_notes=cfg["v2_notes"])


def profile_for(config: str, dataset: str = "cap") -> Any:
    """Hồ sơ prompt: CAP (có / không D); tập Đức → cùng hồ sơ, chỉ đổi mô tả nguồn văn bản (german_profile)."""
    base = (CAP_PROFILE_NORM if CONFIGS[config].get("norm")
            else CAP_PROFILE if CONFIGS[config]["duty"] else CAP_PROFILE_NO_DUTY)
    return german_profile(base) if dataset == "de" else base


def run_clause(chunk: Mapping[str, Any], context: Dict[str, Any], gamma: Mapping[str, Any],
               llm: Any, config: str, grounding: Any = None, process: Any = None,
               dataset: str = "cap", bridge: Any = None, judge_llm: Any = None) -> Dict[str, Any]:
    """Một khoản theo một cấu hình. `gamma` = Γ ĐẦY ĐỦ (schema_for tự bỏ 'domain' khi tắt C).
    `process` (ProcessV2) chỉ dùng với cấu hình v2; khóa kết quả v2 chỉ có ở cấu hình đó."""
    cfg = CONFIGS[config]
    opts = {k: v for k, v in cfg.items() if k not in FEATURE_KEYS}
    opts.setdefault("max_retry", DEFAULT_MAX_RETRY)
    v2 = bool(cfg.get("v2")) and process is not None
    # MAPS_TO đọc từ KG cầu nối (bridge) — cùng một nguồn cho gợi ý Z và kiểm N4 (trước 2026-11-20: tính lại từ ontology)
    hint = (hint_from_doctypes(bridge.doctypes(chunk["node_id"]), bridge.meanings)
            if v2 and cfg.get("v2_hint", True) and bridge is not None else "")
    norm = NormFrame(bridge.doctypes(chunk["node_id"])) if cfg.get("norm") else None
    start = time.perf_counter()
    result = run_single_rule_with_real_llm(
        {"rule_id": chunk["node_id"]}, context, schema_for(gamma, config), llm,
        profile=profile_for(config, dataset),
        grounding=grounding if cfg["vacuity"] else None, check_year_values=cfg["domain"],
        **({"process": process, "generation_hint": hint} if v2 else {}),
        **({"norm": norm} if norm is not None else {}),
        **({"judge_llm": judge_llm} if judge_llm is not None else {}), **opts)
    outcome = outcome_of(result)
    row = {"node_id": chunk["node_id"], "round": chunk.get("round"), "outcome": outcome,
           "ast": result["final_ast"] if outcome == RULE else None,
           "rounds_needed": result["rounds_needed"], "roundtrip_msg": result.get("roundtrip_msg"),
           "grounding": result.get("grounding"), "obligation_analysis": result.get("obligation_analysis"),
           "trajectory": result["trajectory"], "context_refs": context["context_refs"],
           "skipped_refs": context["skipped_refs"], "truncated_chars": context["truncated_chars"],
           "context_chars": len(context["text"]), "seconds": round(time.perf_counter() - start, 1)}
    if norm is not None:
        row["norm_checks"] = result.get("norm_checks")
    if v2:
        row.update({"process_checks": result.get("process_checks"), "definitions": context.get("definitions", []),
                    "scope_note": context.get("scope_note", False), "doctype_hint": bool(hint)})
    return row


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--config", choices=sorted(CONFIGS), required=True)
    p.add_argument("--limit", type=int, default=None, help="chỉ chạy N khoản đầu (thử nhanh)")
    p.add_argument("--only", nargs="*", default=None, help="chỉ chạy các node_id này")
    p.add_argument("--out-dir", default=str(DEFAULT_OUT))
    p.add_argument("--dataset", choices=sorted(DATASETS), default="cap",
                   help="cap = 4 Quy định EU (mặc định); de = tập Đức (dùng --out-dir riêng, VD results/de_cerebras)")
    p.add_argument("--cache-file", default=None,
                   help="mặc định <out-dir>/llm_cache_<config>.json — mỗi cấu hình một file, chạy song song an toàn")
    p.add_argument("--cache-only", action="store_true", help="chỉ phát lại cache, không gọi API")
    p.add_argument("--force", action="store_true", help="chạy lại cả khoản đã có kết quả")
    p.add_argument("--provider", choices=sorted(PROVIDERS), default=os.environ.get("LLM_PROVIDER", "groq"),
                   help="đặt sẵn base-url + tên model gpt-oss-120b của nhà cung cấp (key: GROQ_API_KEY / CEREBRAS_API_KEY)")
    p.add_argument("--model", default=None, help="ghi đè tên model của --provider")
    p.add_argument("--base-url", default=None, help="ghi đè base-url của --provider")
    p.add_argument("--min-interval", type=float, default=float(os.environ.get("LLM_MIN_INTERVAL", "0")),
                   help="giây tối thiểu giữa hai lần gọi API (VD 13 nếu hạn mức chỉ 5 request/phút)")
    p.add_argument("--key-var", default=None,
                   help="tên biến key trong .env cho cửa sổ này (VD CEREBRAS_API_KEY_2); mặc định biến chuẩn")
    p.add_argument("--judge-provider", choices=sorted(PROVIDERS), default=None,
                   help="giám khảo Tầng 3 dùng nhà cung cấp / model KHÁC bộ sinh (tránh tự chấm); mặc định: cùng client")
    p.add_argument("--judge-model", default=None, help="tên model giám khảo (mặc định model của --judge-provider)")
    p.add_argument("--judge-key-var", default=None, help="tên biến key trong .env cho giám khảo")
    return resolve_endpoint(p.parse_args())


def resolve_endpoint(args: argparse.Namespace) -> argparse.Namespace:
    """Điền base-url / model / cache-file mặc định theo --provider và --config (không đổi tham số đã ghi rõ)."""
    base_url, model = PROVIDERS[args.provider]
    if args.provider == "groq":  # LLM_MODEL_NAME / LLM_BASE_URL trong .env là cấu hình cũ cho Groq — không lấn nhà cung cấp khác
        base_url = os.environ.get("LLM_BASE_URL") or base_url
        model = os.environ.get("LLM_MODEL_NAME") or model
    args.base_url = args.base_url or base_url
    args.model = args.model or model
    args.cache_file = args.cache_file or str(Path(args.out_dir) / f"llm_cache_{args.config}.json")
    if getattr(args, "judge_provider", None):  # giám khảo riêng: cache riêng, không lẫn câu trả lời của bộ sinh
        judge_url, judge_model = PROVIDERS[args.judge_provider]
        args.judge_base_url = judge_url
        args.judge_model = args.judge_model or judge_model
        args.judge_cache_file = str(Path(args.out_dir) / f"llm_cache_{args.config}_judge.json")
    return args


def _select(chunks: List[Dict[str, Any]], args: argparse.Namespace) -> List[Dict[str, Any]]:
    if args.only:
        unknown = set(args.only) - {c["node_id"] for c in chunks}
        if unknown:
            raise SystemExit(f"node_id không có trong phiếu: {sorted(unknown)}")
        chunks = [c for c in chunks if c["node_id"] in args.only]
    return chunks[: args.limit] if args.limit else chunks


def check_resume(doc: Mapping[str, Any], args: argparse.Namespace,
                 current: Optional[Mapping[str, str]] = None) -> None:
    """Chạy tiếp vào file đã có: phải cùng bộ dữ liệu, model, nhà cung cấp (trừ khi --force chạy lại từ đầu).
    Không kiểm thì khoản tiếng Đức lẫn vào file CAP, hoặc kết quả hai nhà cung cấp trộn nhau (rà soát MEDIUM-2).
    `current` = dấu dữ liệu đầu vào hiện tại (A2): file đã ghi dấu mà dữ liệu đổi → dừng (sự cố v1.2)."""
    if not doc.get("predictions") or args.force:
        return
    found = {"dataset": doc.get("dataset", "cap"), "model": doc.get("model"), "provider": doc.get("provider"),
             "judge_model": doc.get("judge_model")}
    wanted = {"dataset": args.dataset, "model": args.model, "provider": args.provider,
              "judge_model": getattr(args, "judge_model", None) if getattr(args, "judge_provider", None) else None}
    diff = {k: (found[k], wanted[k]) for k in found if found[k] is not None and found[k] != wanted[k]}
    if diff:
        raise SystemExit(f"File kết quả đã có thuộc lần chạy khác {diff} (đã có → lệnh này). Dùng --out-dir khác, "
                         "hoặc --force để chạy lại mọi khoản.")
    changed = changed_inputs(doc.get("inputs") or {}, current or {})
    if changed:
        raise SystemExit(f"Dữ liệu đầu vào đã ĐỔI so với lúc sinh file này: {changed}. Chạy tiếp sẽ trộn kết quả của "
                         "hai phiên bản dữ liệu. Dùng --force (khoản có prompt không đổi lấy lại từ cache, không tốn "
                         "API), hoặc --out-dir mới.")


def _summary(preds: Mapping[str, Mapping[str, Any]]) -> Dict[str, int]:
    out = {RULE: 0, BASELESS: 0, FAILED: 0, "ERROR": 0}
    for p in preds.values():
        out[p["outcome"]] = out.get(p["outcome"], 0) + 1
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = _parse_args()
    out_path = Path(args.out_dir) / f"predictions_{args.config}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    current = fingerprint(input_paths(args.config, args.dataset))
    run_id = inputs_id(current)
    check_resume(doc, args, current)
    other_dataset = doc.get("dataset", "cap") != args.dataset
    preds: Dict[str, Any] = {} if args.force and other_dataset else doc.get("predictions", {})
    gamma = json.loads(GAMMA.read_text(encoding="utf-8"))
    chunks = _select(json.loads(DATASETS[args.dataset][0].read_text(encoding="utf-8")), args)
    client_cls = CacheOnlyClient if args.cache_only else RealLLMClient
    llm = client_cls(base_url=args.base_url, model_name=args.model, cache_file=args.cache_file,
                     min_interval=args.min_interval, key_var=args.key_var)
    judge_llm = (client_cls(base_url=args.judge_base_url, model_name=args.judge_model, cache_file=args.judge_cache_file,
                            min_interval=args.min_interval, key_var=args.judge_key_var)
                 if args.judge_provider else None)
    build = context_builder(args.config, args.dataset)
    cfg = CONFIGS[args.config]
    todo = [c for c in chunks if args.force or preds.get(c["node_id"], {}).get("outcome") in (None, "ERROR")]
    grounding = None
    if cfg["vacuity"] and todo:
        start = time.perf_counter()
        sys.stdout.write("Nạp log BPIC2018 cho kiểm rỗng (B)...\n")
        sys.stdout.flush()
        grounding = load_grounding()
        sys.stdout.write(f"  {grounding.num_cases} hồ sơ, {time.perf_counter() - start:.0f}s\n")
    process = load_process_v2(grounding, args.config) if cfg.get("v2") else None
    bridge_path = MAPPING_GRAPHS[args.dataset]
    bridge = (load_bridge(json.loads(bridge_path.read_text(encoding="utf-8")))
              if (cfg.get("norm") or cfg.get("v2")) and bridge_path.exists() else None)
    if cfg.get("norm") and (bridge is None or load_ontology(ONTOLOGY) is None):
        raise SystemExit(f"Cấu hình N cần ontology ĐÃ DUYỆT và tầng Cầu nối {bridge_path.name} "
                         "(python scripts/build_mapping_graph.py) — đăng ký trước B6.")
    meta = {"config": args.config, "options": cfg, "model": args.model, "provider": args.provider,
            "base_url": args.base_url, "key_var": args.key_var or "default", "cache_file": str(args.cache_file),
            "profile": profile_for(args.config, args.dataset).name, "timezone": TIMEZONE,
            **({"judge_model": args.judge_model, "judge_provider": args.judge_provider} if judge_llm else {}),
            "inputs": current, "inputs_id": run_id, "code": code_version(PROJECT_ROOT)}
    if args.dataset != "cap":
        meta["dataset"] = args.dataset
    if cfg.get("norm"):
        meta["norm"] = {"preregistration": "docs/V2_DANG_KY_TRUOC.md B6", "ontology_approved_at": bridge.approved_at,
                        "maps_to_source": bridge_path.name}
    if process is not None:
        onto_ok = process.ontology is not None
        if not onto_ok:
            sys.stdout.write("!!! Ontology CHƯA DUYỆT (data/review/bpic2018_ontology.json) — v2 chạy KHÔNG có nghĩa "
                             "loại giấy tờ và gợi ý MAPS_TO. Duyệt trước khi chạy thật "
                             "(docs/ONTOLOGY_BPIC2018_DUYET.md).\n")
        meta["v2"] = {"ontology_approved": onto_ok, "mass_threshold": MASS_VIOLATION_THRESHOLD,
                      "mass_check": process.mass is not None, "preregistration": "docs/V2_DANG_KY_TRUOC.md"}
    unsaved = False
    for i, chunk in enumerate(chunks, start=1):
        nid = chunk["node_id"]
        if chunk not in todo:
            continue
        try:
            preds[nid] = {**run_clause(chunk, build(chunk), gamma, llm, args.config, grounding, process,
                                       args.dataset, bridge, judge_llm), "inputs_id": run_id}
        except Exception as exc:  # ghi lỗi từng khoản (VD hết quota, cache miss), không dừng cả đợt
            preds[nid] = {"node_id": nid, "round": chunk.get("round"), "outcome": "ERROR",
                          "error": f"{type(exc).__name__}: {str(exc)[:300]}", "inputs_id": run_id}
        p = preds[nid]
        sys.stdout.write(f"[{i}/{len(chunks)}] {nid:<18} {p['outcome']:<8} "
                         f"vòng={p.get('rounds_needed', '-')} {p.get('seconds', '')}s\n")
        sys.stdout.flush()  # log ra file vẫn thấy tiến độ ngay
        unsaved = not write_json_atomic(out_path, {**meta, "predictions": preds, "summary": _summary(preds)})
        if unsaved:
            sys.stderr.write(f"CẢNH BÁO: {out_path.name} đang bị khoá (VD OneDrive) — kết quả giữ trong bộ nhớ, "
                             "lần ghi sau ghi đủ.\n")
    # lần ghi cuối thất bại: thử lại; vẫn khoá thì báo lỗi rõ (exit 2) thay vì để file thiếu khoản cuối mà không ai biết
    if unsaved and not write_json_atomic(out_path, {**meta, "predictions": preds, "summary": _summary(preds)}):
        sys.stderr.write(f"LỖI: không ghi được {out_path} (file bị khoá). Câu trả lời LLM đã nằm trong cache — "
                         "chạy lại cùng lệnh với --cache-only để ghi lại kết quả.\n")
        return 2
    sys.stdout.write(f"\nTổng hợp {args.config}: {_summary(preds)}\nĐã ghi {out_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
