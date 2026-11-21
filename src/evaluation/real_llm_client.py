"""
Client Kết nối Model Thực tế (Groq / OpenAI / Gemini / Ollama) kèm Bộ nhớ đệm (Disk Cache)
và Bộ ghi nhận Nhật ký Tự sửa Thật (Trajectory Logging) cho 30 Quy tắc Chuẩn (R01–R30).

Thiết kế bám sát Mục 4.1.2 của bài OCL2026 (OVAS):
- Cố định temperature = 0.0 để đảm bảo tính tất định (determinism).
- Lưu phản hồi vào Disk Cache (`real_llm_cache.json`) theo mã băm SHA-256 của `(model, messages, temperature)`
  để tái lập thực nghiệm 100% và không tốn quota API khi chạy lại.
- Lưu toàn bộ lịch sử sai–sửa (`trajectory`) qua Tầng 1, Tầng 2 và Tầng 3 (Entity Matcher + Roundtrip) để đưa vào bài báo.
- Kiểm rỗng trên log (B) và phân tích nghĩa vụ (D) CHỈ chạy khi được bật (tham số `grounding`,
  `profile.abstain_enabled` — bộ CAP). Trước 2026-11-09 vòng lặp này KHÔNG có kiểm rỗng dù docstring cũ ghi
  'Tầng 3 (Roundtrip & Vacuity)'.
- TUYỆT ĐỐI KHÔNG chứa bất kỳ câu mớm bẫy viết cứng (`phi_auditor_claims`) hay gợi ý đáp án nào:
  Chỉ truyền duy nhất 2 thông tin nguyên bản là Văn bản luật thô (`retrieved_chunk['text']`) và Lược đồ quy trình (`process_schema`).
"""

import hashlib
import json
import os
import sys
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False

from src.mde.constraint_ast import BINARY_TEMPLATES, UNARY_TEMPLATES, DeclareConstraintAST, validate_layer1_ast
from src.mde.typing_environment import check_layer1_and_layer2  # Tầng 1–2 (MDE); không phụ thuộc experiment_runner
from src.symbolic.verbalizer_roundtrip import check_roundtrip_fidelity
from src.symbolic.domain_profiles import BPIC2017_PROFILE, DomainProfile, build_generation_messages
from src.symbolic.log_grounding import LogGroundingChecker, grounding_record, vacuity_feedback
from src.symbolic.obligation_gate import assess_obligation
from src.symbolic.norm_frame import (NormFrame, frame_error, kg_feedback, kg_support, missing_deadline,
                                     not_expressible, quote_error, template_error)
from src.symbolic.process_checks import ProcessV2, activity_notes, event_attribute_error, year_group_feedback

ALLOWED_DECLARE_TEMPLATES = UNARY_TEMPLATES | BINARY_TEMPLATES
KNOWN_KEY_VARS = ("GROQ_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "API_KEY")
# Máy chủ có key riêng: CHỈ nhận biến của chính nó, để không bao giờ gửi key nhà cung cấp khác ra ngoài.
PROVIDER_KEY_VARS = {"api.cerebras.ai": ("CEREBRAS_API_KEY",)}
RATE_LIMIT_FALLBACK_STEP_S = 10.0  # 429 không kèm thời gian chờ: 10, 20, ..., 60 s (token bucket hồi dần)
RETRY_AFTER_CAP_S = 120.0
CACHE_REPLACE_RETRIES = 8  # file cache bị khoá tạm (OneDrive / phần mềm diệt virus): chờ 0,25 → 2 s, tổng ~9 s
CACHE_REPLACE_WAIT_S = 0.25


def rate_limit_wait(exc: Exception, retry_i: int) -> float:
    """
    Số giây chờ sau lỗi 429: header Retry-After (chuẩn HTTP) → câu 'try again in Xs' (kiểu Groq) →
    tăng dần 10, 20, ..., 60 s (kiểu Cerebras: hạn mức hồi liên tục, thông báo không ghi thời gian chờ).
    """
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        retry_after = float(headers.get("retry-after", ""))
        if retry_after > 0:
            return min(retry_after, RETRY_AFTER_CAP_S) + 1.0
    except (TypeError, ValueError):
        pass
    wait_match = re.search(r"try again in ([\d\.]+)s", str(exc).lower())
    if wait_match:
        return float(wait_match.group(1)) + 1.5
    return RATE_LIMIT_FALLBACK_STEP_S * (retry_i + 1)


class LLMCallError(RuntimeError):
    """Lỗi hạ tầng khi gọi LLM (mạng, hạn mức, máy chủ) — không phải câu trả lời sai của mô hình. Không cache."""


class TruncatedResponseError(LLMCallError):
    """Câu trả lời bị cắt vì chạm max_completion_tokens (finish_reason = 'length') — lỗi NGÂN SÁCH của lần gọi, không
    phải câu trả lời của mô hình: không cache, không thử lại cùng tham số (sẽ bị cắt y như vậy)."""

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def key_vars_for(base_url: Optional[str], key_var: Optional[str] = None) -> tuple:
    """
    Tên biến key được phép dùng cho máy chủ `base_url` (mặc định: các biến cũ, kiểu Groq/OpenAI).
    `key_var` chọn MỘT key cụ thể (VD CEREBRAS_API_KEY_2 cho cửa sổ chạy thứ hai); tên phải bắt đầu bằng
    biến của chính máy chủ đó, nên không thể trỏ nhầm sang key nhà cung cấp khác.
    """
    allowed = KNOWN_KEY_VARS
    for host, names in PROVIDER_KEY_VARS.items():
        if base_url and host in base_url:
            allowed = names
            break
    if key_var is None:
        return allowed
    if not re.fullmatch(r"[A-Z0-9_]+", key_var) or not key_var.startswith(allowed):
        raise ValueError(f"key_var {key_var!r} không dùng được cho {base_url}; tên phải bắt đầu bằng "
                         f"{' / '.join(allowed)} (VD {allowed[0]}_2).")
    return (key_var,)


def _resolve_api_key(explicit_key: Optional[str] = None, base_url: Optional[str] = None,
                     key_var: Optional[str] = None) -> Optional[str]:
    """Tự động nạp biến môi trường từ .env ở thư mục gốc dự án hoặc ~/.env (không in giá trị khóa)."""
    if explicit_key:
        return explicit_key
    key_vars = key_vars_for(base_url, key_var)
    plain_line_ok = key_vars == KNOWN_KEY_VARS  # dòng trơn 'gsk_...' chỉ hợp lệ cho máy chủ mặc định
    project_env = PROJECT_ROOT / ".env"
    home_env = Path.home() / ".env"
    if project_env.exists():
        load_dotenv(dotenv_path=project_env, override=True)
    if home_env.exists():
        load_dotenv(dotenv_path=home_env, override=False)

    for var_name in key_vars:
        val = os.environ.get(var_name)
        if val and val.strip():
            return val.strip().strip('"').strip("'")

    # F-KEY (kiểm toán 2026-11-09): trước đây lấy GIÁ TRỊ ĐẦU TIÊN dạng X=Y bất kỳ (VD NEO4J_PASSWORD) làm API key
    # và gửi ra máy chủ LLM. Giờ chỉ nhận tên biến key đã biết, hoặc một dòng trơn trông như key Groq/OpenAI.
    for env_file in (project_env, home_env):
        if not env_file.exists():
            continue
        try:
            lines = env_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" in s:
                name, v = s.split("=", 1)
                v = v.strip().strip('"').strip("'")
                if name.strip().removeprefix("export ").strip() in key_vars and v:
                    return v
            elif plain_line_ok and s.strip('"').strip("'").startswith(("gsk_", "sk-")):
                return s.strip('"').strip("'")
    return None


class RealLLMClient:
    """
    Client kết nối LLM thực tế (Groq `openai/gpt-oss-120b`, OpenAI, Gemini OpenAI-compatible, hoặc Ollama)
    với cơ chế lưu Disk Cache (`real_llm_cache.json`) ở `temperature = 0.0`.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.groq.com/openai/v1",
        model_name: str = "openai/gpt-oss-120b",
        cache_file: Union[str, Path] = "real_llm_cache.json",
        min_interval: float = 0.0,
        key_var: Optional[str] = None,
        max_completion_tokens: Optional[int] = None,
    ) -> None:
        resolved_key = _resolve_api_key(api_key, base_url, key_var)
        if not resolved_key:
            raise ValueError(f"Missing API key for {base_url}! "
                             f"Please set {' / '.join(key_vars_for(base_url, key_var))} in .env.")
        self.key_var = key_var  # chỉ TÊN biến (ghi vào kết quả để biết cấu hình chạy bằng key nào), không bao giờ giá trị
        if min_interval < 0:
            raise ValueError("min_interval must be >= 0")
        self.min_interval = float(min_interval)  # giây tối thiểu giữa hai lần gọi API (VD 13 cho hạn 5 request/phút)
        self._last_request_at: Optional[float] = None
        # Giới hạn độ dài câu trả lời gửi kèm request (2026-11-21). Cerebras tính độ dài trả lời MẶC ĐỊNH (~20k token)
        # vào hạn mức token / phút → prompt ~10k token (vòng sửa thứ 4–5) luôn bị 429 dù chờ bao lâu. None = không
        # gửi (như trước). Không vào khoá cache: câu trả lời đã cache không đổi.
        if max_completion_tokens is not None and max_completion_tokens <= 0:
            raise ValueError("max_completion_tokens must be > 0")
        self.max_completion_tokens = max_completion_tokens

        from openai import OpenAI

        self.client = OpenAI(api_key=resolved_key, base_url=base_url)
        self.model_name = model_name
        self.base_url = base_url
        self.cache_path = Path(cache_file)
        if not self.cache_path.is_absolute():
            self.cache_path = PROJECT_ROOT / self.cache_path
        self.cache: Dict[str, str] = self._load_cache()

    def _read_disk_cache(self) -> Dict[str, str]:
        with open(self.cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_cache(self) -> Dict[str, str]:
        """File hỏng (VD ghi dở) → đổi tên giữ lại + cảnh báo, rồi bắt đầu rỗng — trước đây im lặng trả {} và lần
        ghi sau xoá trắng cache (rà soát lõi 2026-11-18 H3)."""
        if not self.cache_path.exists():
            return {}
        try:
            return self._read_disk_cache()
        except (json.JSONDecodeError, UnicodeDecodeError):
            backup = self.cache_path.with_name(f"{self.cache_path.stem}.corrupt-{int(time.time())}.json")
            os.replace(self.cache_path, backup)
            sys.stderr.write(f"CẢNH BÁO: cache LLM hỏng, đã giữ lại ở {backup}; bắt đầu cache rỗng.\n")
            return {}

    def _save_cache(self) -> None:
        """Gộp với cache trên đĩa (tiến trình khác có thể vừa ghi) rồi ghi nguyên tử (file tạm + os.replace)."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        if self.cache_path.exists():
            try:
                self.cache = {**self._read_disk_cache(), **self.cache}
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass  # file trên đĩa hỏng: ghi đè bằng bản trong bộ nhớ (bản hỏng đã được giữ lúc nạp nếu có)
        tmp = self.cache_path.with_name(f"{self.cache_path.name}.{os.getpid()}.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, indent=2, ensure_ascii=False)
        # Windows + OneDrive (2026-11-20): trình đồng bộ giữ khoá file vài trăm ms → os.replace báo 'Access is denied'
        # và khoản đang chạy bị đánh ERROR dù LLM đã trả lời. Thử lại; vẫn khoá thì CẢNH BÁO, giữ cache trong bộ nhớ
        # (lần lưu sau ghi đủ) thay vì làm hỏng khoản — kết quả sinh luật không phụ thuộc việc ghi cache thành công.
        for attempt in range(CACHE_REPLACE_RETRIES):
            try:
                os.replace(tmp, self.cache_path)
                return
            except PermissionError:
                time.sleep(CACHE_REPLACE_WAIT_S * (attempt + 1))
        sys.stderr.write(f"CẢNH BÁO: không ghi được {self.cache_path.name} (file đang bị khoá, VD OneDrive đồng bộ); "
                         "cache giữ trong bộ nhớ và sẽ được ghi ở lần lưu sau.\n")

    def _throttle(self) -> None:
        """Đảm bảo hai lần gọi API cách nhau ít nhất `min_interval` giây (hạn mức request/phút)."""
        if self.min_interval and self._last_request_at is not None:
            wait = self.min_interval - (time.monotonic() - self._last_request_at)
            if wait > 0:
                time.sleep(wait)
        self._last_request_at = time.monotonic()

    def _create(self, **kwargs: Any) -> Any:
        self._throttle()
        if self.max_completion_tokens:
            kwargs.setdefault("max_completion_tokens", self.max_completion_tokens)
        response = self.client.chat.completions.create(**kwargs)
        if self.max_completion_tokens and getattr(response.choices[0], "finish_reason", None) == "length":
            raise TruncatedResponseError(f"Câu trả lời bị cắt ở max_completion_tokens={self.max_completion_tokens} — "
                                         "tăng --max-tokens (prompt + giới hạn phải dưới hạn mức token / phút).")
        return response

    def _make_key(self, messages: List[Dict[str, str]], temperature: float) -> str:
        payload = json.dumps(
            {"model": self.model_name, "messages": messages, "temp": temperature},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def chat_json(
        self,
        messages: Union[List[Dict[str, str]], str],
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> str:
        """
        Gọi LLM thật với temperature = 0.0 (theo chuẩn Mục 4.1.2 bài OCL2026)
        và tự động lưu cache để tái lập thực nghiệm 100%.
        """
        if isinstance(messages, str):
            msg_list: List[Dict[str, str]] = [
                {
                    "role": "system",
                    "content": (
                        "You are a formal compliance semantic verifier. "
                        "Always respond with a valid JSON object."
                    ),
                },
                {"role": "user", "content": messages},
            ]
        else:
            msg_list = messages

        cache_key = self._make_key(msg_list, temperature)
        if cache_key in self.cache:
            return self.cache[cache_key]

        fallback_models = [self.model_name]

        last_err: Optional[Exception] = None
        content = "{}"
        for candidate_model in fallback_models:
            for retry_i in range(6):
                try:
                    response = self._create(
                        model=candidate_model,
                        messages=msg_list,  # type: ignore[arg-type]
                        temperature=temperature,
                        response_format={"type": "json_object"},
                    )
                    content = (response.choices[0].message.content or "{}").strip()
                    last_err = None
                    break
                except TruncatedResponseError:
                    raise  # bị cắt do ngân sách: thử lại cùng tham số cho kết quả y hệt → báo ngay, không cache
                except Exception as exc:
                    last_err = exc
                    err_str = str(exc).lower()
                    if "json_validate_failed" in err_str or "failed to generate json" in err_str:
                        # Thử lại không dùng response_format json_object và bóc tách bằng regex
                        try:
                            resp_fb = self._create(
                                model=candidate_model,
                                messages=msg_list,  # type: ignore[arg-type]
                                temperature=temperature,
                            )
                            raw_txt = (resp_fb.choices[0].message.content or "{}").strip()
                            json_m = re.search(r"\{.*\}", raw_txt, re.DOTALL)
                            if json_m:
                                content = json_m.group(0)
                            else:
                                content = "{}"
                            last_err = None
                            break
                        except Exception as fb_exc:
                            last_err = fb_exc
                            break
                    if "rate limit" in err_str or "429" in err_str or "tpm" in err_str:
                        time.sleep(rate_limit_wait(exc, retry_i))
                    else:
                        time.sleep(1.0)
            if last_err is None:
                # Tránh gọi dồn dập vượt TPM (Tokens Per Minute)
                time.sleep(1.2)
                break
        if last_err is not None:
            # F-CACHE (kiểm toán 2026-11-09): trước đây trả '{}' VÀ ghi vào cache → lỗi mạng / hết hạn mức bị tính
            # thành 'LLM trả JSON sai' và không bao giờ thử lại. Giờ: báo lỗi, KHÔNG ghi cache.
            raise LLMCallError(f"Gọi LLM thất bại sau nhiều lần thử: {type(last_err).__name__}: {last_err}") \
                from last_err

        if content.strip() not in ("", "{}"):  # v1.2 (rà soát lõi C9): phản hồi rỗng không được lưu vĩnh viễn
            self.cache[cache_key] = content
            self._save_cache()
        return content

    def chat(self, prompt_or_messages: Any, temperature: float = 0.0) -> str:
        """
        Phương thức phục vụ Bước 4.3 (diễn đạt Báo cáo Giải trình từ Justification Tree).
        """
        from src.evaluation.grounded_auditor import DeterministicAuditNarratorClient  # mã BPIC2017: nạp khi cần

        return DeterministicAuditNarratorClient().chat(prompt_or_messages, temperature=temperature)


def _retry(messages: List[Dict[str, str]], trajectory: List[Dict[str, Any]], attempt: int, raw_output: Any,
           status: str, error: str, feedback: str) -> None:
    """Ghi một vòng thất bại vào trajectory và trả phản hồi cho LLM (định dạng như bản cũ)."""
    trajectory.append({"round": attempt, "output": raw_output, "status": status, "error": error})
    messages.append({"role": "assistant", "content": raw_output})
    messages.append({"role": "user", "content": feedback})


def _result(final_ast: Optional[Dict[str, Any]], rounds: int, trajectory: List[Dict[str, Any]], ok: bool, msg: str,
            grounding: Optional[Dict[str, Any]] = None, analysis: Optional[Dict[str, Any]] = None,
            process_record: Optional[Dict[str, Any]] = None,
            norm_record: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out = {"final_ast": final_ast, "rounds_needed": rounds, "trajectory": trajectory, "roundtrip_ok": ok,
           "roundtrip_msg": msg, "grounding": grounding, "obligation_analysis": analysis}
    if process_record is not None:  # v2: chỉ có khi bật, kết quả v1 giữ nguyên các khóa cũ
        out["process_checks"] = process_record
    if norm_record is not None:  # cấu hình N (B6): chỉ có khi bật
        out["norm_checks"] = norm_record
    return out


def is_baseless_message(rt_msg: str) -> bool:
    """Kết luận BASELESS chỉ khi Entity Matcher / giám khảo thật sự trả BASELESS. v1.2 (rà soát lõi C2): trước đây dò
    chuỗi con 'BASELESS' trong cả lời giám khảo — 'not BASELESS, but order reversed' bị coi là trap."""
    return str(rt_msg).startswith("[Layer 3 Semantic BASELESS]")


def constraint_key(ast_dict: Mapping[str, Any]) -> str:
    """Khoá 'phản hồi một lần' = dòng .decl (ràng buộc thật). v1.2 (rà soát lõi C7): trước đây cả AST, nên LLM
    đổi câu chữ 'decomposition' mà giữ nguyên ràng buộc lại nhận cùng phản hồi lần nữa."""
    try:
        return DeclareConstraintAST.model_validate(dict(ast_dict)).to_declare4py_line().strip()
    except Exception:  # AST không dựng được dòng .decl (đã qua Tầng 1 nên hiếm) → khoá cũ
        return json.dumps(ast_dict, sort_keys=True, default=str)


def _process_checks(ast_dict: Dict[str, Any], process: ProcessV2, warned: Dict[str, set],
                    record: Dict[str, Any], years: Optional[List[int]] = None) -> Optional[Tuple[str, str]]:
    """Kiểm v2 sau B, trước Tầng 3 → (status, phản hồi) nếu cần một vòng nữa, None nếu qua.
    Thuộc tính sai chỗ: phản hồi mọi lần. Năm, vi phạm hàng loạt: một lần cho mỗi ràng buộc
    (giữ nguyên → chấp nhận, gắn cờ)."""
    record.clear()  # chỉ giữ kết quả của vòng hiện tại (rà soát 2026-11-18, MEDIUM-3)
    err = event_attribute_error(ast_dict, process.profile) if process.check_attribute else None
    if err:
        return "FAILED_ATTRIBUTE_PLACEMENT", err
    key = constraint_key(ast_dict)
    year_fb = year_group_feedback(ast_dict, process.profile, years) if process.check_year else None
    record["year_coverage_hint"] = year_fb is not None
    if year_fb and key not in warned["year"]:
        warned["year"].add(key)
        return "FAILED_YEAR_COVERAGE", year_fb
    if process.mass is not None and process.check_mass:
        rec = process.mass.assess(ast_dict, years=years) if years else process.mass.assess(ast_dict)
        record["mass_violation"] = {k: rec[k] for k in ("activated", "violated", "ratio", "mass_violation")}
        if rec["mass_violation"] and key not in warned["mass"]:
            warned["mass"].add(key)
            return "FAILED_MASS_VIOLATION", process.mass.feedback(ast_dict, rec)
    return None


def _layers_1_2(raw_output: Any, process_schema: Dict[str, Any], chunk: Dict[str, Any],
                enable_l1_l2: bool) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    """→ (ast_dict, status lỗi, thông báo lỗi). Tắt Tầng 1–2: chỉ kiểm cú pháp Tầng 1, sai thì dừng (như bản cũ)."""
    if enable_l1_l2:
        ok, res = check_layer1_and_layer2(raw_output, process_schema, chunk)
        return (res.model_dump(), None, None) if ok else (None, "FAILED_L1_L2", str(res))
    ok, res = validate_layer1_ast(raw_output)
    return (res.model_dump(), None, None) if ok else (None, "FAILED_L1_SYNTAX", str(res))


def run_single_rule_with_real_llm(
    rule_item: Dict[str, Any],
    retrieved_chunk: Dict[str, Any],
    process_schema: Dict[str, Any],
    llm: RealLLMClient,
    max_retry: int = 5,
    enable_l1_l2: bool = True,
    enable_l3_roundtrip: bool = True,
    profile: DomainProfile = BPIC2017_PROFILE,
    grounding: Optional[LogGroundingChecker] = None,
    check_year_values: bool = False,
    process: Optional[ProcessV2] = None,
    generation_hint: str = "",
    norm: Optional[NormFrame] = None,
    judge_llm: Any = None,
) -> Dict[str, Any]:
    """
    Vòng lặp tổng hợp và tự sửa với RealLLMClient. Prompt chỉ chứa văn bản luật (`retrieved_chunk['text']`)
    và Γ (`process_schema`); `rule_item` chỉ để ghi nhật ký — mô tả gold KHÔNG vào prompt
    (tests/test_no_gold_in_prompts.py). Ví dụ few-shot là miền giả định.

    Thứ tự kiểm mỗi vòng (lỗi → phản hồi cho LLM, sang vòng sau):
      D   profile.abstain_enabled: obligation_analysis hợp lệ; no_constraint → kết thúc, DECLINED_NO_OBLIGATION
      1–2 Tầng 1 (metamodel) + Tầng 2 (Γ; với Γ dựng từ KG có kiểm miền giá trị C)
      D   nhất quán phân tích ↔ ràng buộc (phản hồi tối đa một lần)
      B   grounding: kiểm rỗng trên log — 0 hồ sơ kích hoạt → phản hồi MỘT lần cho mỗi ràng buộc; giữ nguyên thì
          chấp nhận với cờ grounding.vacuous = True
      v2  process (docs/V2_DANG_KY_TRUOC.md): thuộc tính event sai chỗ, gợi ý nhóm theo năm, vi phạm hàng loạt
          trên log (phản hồi kèm phản ví dụ); ghi chú activity cho giám khảo
      3   Entity Matcher (số, ngày; năm nếu check_year_values = kiểm E) rồi LLM giám khảo dịch ngược
    Mặc định (BPIC2017): D, B, E, v2 tắt → message và trajectory y như trước khi có các kiểm này.
    generation_hint (v2): dòng nêu loại giấy tờ liên quan, thêm vào câu hỏi cuối (không vào văn bản luật).
    norm (cấu hình N, đăng ký trước B6): khung chuẩn tắc — N1 định dạng, N2 loại không diễn đạt được → kết thúc
      DECLINED_NORM_TYPE (sau D), N3 thời hạn đã trích phải có trong ràng buộc, N4 hỗ trợ từ KG (MAPS_TO; phản hồi
      MỘT lần, giữ nguyên → chấp nhận với cờ) — N3, N4 sau nhất quán D, trước B. None → như trước.
    judge_llm: client cho giám khảo Tầng 3 (VD model khác bộ sinh, tránh tự chấm). None → dùng chính `llm` (như trước).
    """
    allowed_templates = sorted(list(ALLOWED_DECLARE_TEMPLATES))
    messages: List[Dict[str, str]] = build_generation_messages(
        profile, retrieved_chunk, process_schema, allowed_templates, json.dumps
    )
    if generation_hint:
        messages[-1] = {**messages[-1], "content": messages[-1]["content"] + "\n" + generation_hint}
    trajectory: List[Dict[str, Any]] = []
    duty_warned, vacuity_warned, analysis = False, set(), None
    process_warned: Dict[str, set] = {"year": set(), "mass": set()}
    process_record: Optional[Dict[str, Any]] = {} if process is not None else None
    norm_record: Optional[Dict[str, Any]] = {} if norm is not None else None
    kg_warned: set = set()

    for attempt in range(1, max_retry + 1):
        raw_output = llm.chat_json(messages, temperature=0.0)
        decision = assess_obligation(raw_output) if profile.abstain_enabled else None
        if decision is not None:
            if decision.error:
                _retry(messages, trajectory, attempt, raw_output, "FAILED_OBLIGATION_ANALYSIS", decision.error,
                       f"Validation failed: {decision.error} Please fix the JSON.")
                continue
            analysis = decision.analysis or analysis
            if decision.no_constraint:
                trajectory.append({"round": attempt, "output": raw_output, "status": "DECLINED_NO_OBLIGATION",
                                   "error": None})
                return _result(None, attempt - 1, trajectory, False,
                               "No obligation observable in individual cases (obligation_analysis).", None, analysis,
                               process_record, norm_record)
            if norm is not None and decision.analysis is not None:
                frame_err = (frame_error(decision.analysis)
                             or quote_error(decision.analysis, [str(retrieved_chunk.get("text", ""))]))
                if frame_err:
                    _retry(messages, trajectory, attempt, raw_output, "FAILED_NORM_FRAME", frame_err,
                           f"Validation failed: {frame_err} Please fix the JSON.")
                    continue
                if not_expressible(decision.analysis):  # N2: kết thúc theo code, không để LLM quyết
                    trajectory.append({"round": attempt, "output": raw_output, "status": "DECLINED_NORM_TYPE",
                                       "error": None})
                    return _result(None, attempt - 1, trajectory, False,
                                   f"Norm type '{decision.analysis['norm_type']}' cannot be expressed as a DECLARE "
                                   "constraint (norm frame).", None, analysis, process_record, norm_record)

        ast_dict, status, err = _layers_1_2(raw_output, process_schema, retrieved_chunk, enable_l1_l2)
        if ast_dict is None:
            if not enable_l1_l2:
                trajectory.append({"round": attempt, "output": raw_output, "status": status, "error": err})
                break
            _retry(messages, trajectory, attempt, raw_output, status, err,
                   f"Validation failed: {err}. Please fix the JSON.")
            continue

        if decision is not None and decision.inconsistent and not duty_warned:
            duty_warned = True
            _retry(messages, trajectory, attempt, raw_output, "FAILED_OBLIGATION_CONSISTENCY",
                   decision.inconsistent, decision.inconsistent)
            continue

        if norm is not None:
            deadline_fb = missing_deadline(analysis, ast_dict)
            if deadline_fb:
                _retry(messages, trajectory, attempt, raw_output, "FAILED_NORM_DEADLINE", deadline_fb, deadline_fb)
                continue
            template_fb = template_error(analysis, ast_dict)
            if template_fb:
                _retry(messages, trajectory, attempt, raw_output, "FAILED_NORM_TEMPLATE", template_fb, template_fb)
                continue
            support = kg_support(ast_dict, norm.clause_doctypes)
            norm_record.clear()
            norm_record["kg_support"] = support
            key = constraint_key(ast_dict)
            if not support["supported"] and key not in kg_warned:
                kg_warned.add(key)
                feedback = kg_feedback(support)
                _retry(messages, trajectory, attempt, raw_output, "FAILED_KG_SUPPORT", feedback, feedback)
                continue

        ground = None
        if grounding is not None:
            # Tập Đức: khoản có 'years' → chỉ hồ sơ của các năm đó (bộ CAP: không có 'years', như cũ)
            years = retrieved_chunk.get("years")
            n_cases = grounding.cases_in(years) if years else grounding.num_cases
            ground = grounding_record(grounding.witness_cases(ast_dict, years=years) if years
                                      else grounding.witness_cases(ast_dict), n_cases)
            key = constraint_key(ast_dict)
            if ground["vacuous"] and key not in vacuity_warned:
                vacuity_warned.add(key)
                feedback = vacuity_feedback(ast_dict, n_cases, profile.abstain_enabled)
                _retry(messages, trajectory, attempt, raw_output, "FAILED_VACUITY", feedback, feedback)
                continue

        notes = ""
        if process is not None:
            failed = _process_checks(ast_dict, process, process_warned, process_record,
                                     retrieved_chunk.get("years"))
            if failed:
                _retry(messages, trajectory, attempt, raw_output, failed[0], failed[1], failed[1])
                continue
            notes = (activity_notes(ast_dict, process.profile, process.ontology, retrieved_chunk.get("years"))
                     if process.judge_notes else "")

        if enable_l3_roundtrip:
            ok_rt, rt_msg = check_roundtrip_fidelity(ast_dict, retrieved_chunk, judge_llm or llm, profile=profile,
                                                     check_year_values=check_year_values, judge_notes=notes)
            if not ok_rt and not is_baseless_message(rt_msg):
                _retry(messages, trajectory, attempt, raw_output, "FAILED_L3_ROUNDTRIP", rt_msg,
                       f"Semantic verification failed: {rt_msg}. Please revise.")
                continue
        else:
            ok_rt, rt_msg = True, "Roundtrip check disabled."

        # Thành công hoặc phát hiện đúng bẫy BASELESS
        trajectory.append({"round": attempt, "output": raw_output,
                           "status": "PASSED" if ok_rt else "DETECTED_BASELESS_TRAP",
                           "error": None if ok_rt else rt_msg})
        return _result(ast_dict, attempt - 1, trajectory, ok_rt, rt_msg, ground, analysis, process_record,
                       norm_record)

    # v1.2 (rà soát lõi, LOW): số vòng thật (tắt Tầng 1–2 thì dừng sớm sau lỗi cú pháp, không phải max_retry)
    return _result(None, len(trajectory) or max_retry, trajectory, False, "Exceeded max retries.", None, analysis,
                   process_record, norm_record)
