"""
Kiểm toán bước 3–4: các phát hiện trên đường đi tạo số liệu CAP (chi tiết, mức độ: docs/AUDIT_CAP_PIPELINE.md).

- Hành vi ĐÚNG hiện có → test thường (nâng độ phủ RealLLMClient, phần trước đây chỉ chạy khi gọi API thật).
- Lỗi đã tìm thấy và ĐÃ SỬA (2026-11-09) → test hồi quy mang mã phát hiện. Trước khi sửa, các test này mang
  @unittest.expectedFailure và đã được xác nhận thất bại đúng vì lỗi mô tả.
Không gọi mạng, không đọc .env thật (client OpenAI giả; thư mục tạm cho bài kiểm key).
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import src.evaluation.real_llm_client as rlc  # noqa: E402
from src.evaluation.cap_notation import NotationError, notation_to_ast  # noqa: E402
from src.symbolic.domain_profiles import CAP_PROFILE  # noqa: E402
from src.symbolic.verbalizer_roundtrip import (  # noqa: E402
    JudgeOutputError,
    check_roundtrip_fidelity,
    extract_clause_numeric_entities,
)

MAIL = "Payment application / Application / mail income"
PAY = "Payment application / Application / begin payment"
GAMMA = {"valid_activities": [MAIL, PAY], "activities_by_origin": {},
         "case_attributes": {"case:year": {"type": "String", "samples": []}},
         "event_attributes": {"time:timestamp": {"type": "Timestamp", "samples": []}}}


class FakeCompletions:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def create(self, **kw):
        self.calls.append(kw)
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=r))])


def _client(tmp: Path, replies) -> "rlc.RealLLMClient":
    with mock.patch.object(rlc, "_resolve_api_key", return_value="test-key"):
        c = rlc.RealLLMClient(api_key="test-key", cache_file=tmp / "cache.json")
    c.client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(replies)))
    return c


class TestRealLLMClientCache(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.sleep = mock.patch.object(rlc.time, "sleep", lambda *_: None)
        self.sleep.start()

    def tearDown(self) -> None:
        self.sleep.stop()

    def test_cache_hit_avoids_second_call_and_survives_reload(self) -> None:
        c = _client(self.tmp, ['{"a": 1}'])
        msgs = [{"role": "user", "content": "x"}]
        self.assertEqual(c.chat_json(msgs), '{"a": 1}')
        self.assertEqual(c.chat_json(msgs), '{"a": 1}')
        self.assertEqual(len(c.client.chat.completions.calls), 1)
        again = _client(self.tmp, ['{"b": 2}'])
        self.assertEqual(again.chat_json(msgs), '{"a": 1}')  # đọc lại từ file cache

    def test_cache_key_depends_on_model_messages_temperature(self) -> None:
        c = _client(self.tmp, ["{}"])
        m = [{"role": "user", "content": "x"}]
        keys = {c._make_key(m, 0.0), c._make_key(m, 0.5), c._make_key([{"role": "user", "content": "y"}], 0.0)}
        self.assertEqual(len(keys), 3)

    def test_string_prompt_wrapped_with_system_message(self) -> None:
        c = _client(self.tmp, ['{"verdict": "EQUIVALENT"}'])
        c.chat_json("judge me")
        sent = c.client.chat.completions.calls[0]["messages"]
        self.assertEqual([m["role"] for m in sent], ["system", "user"])

    def test_json_validate_failed_falls_back_to_regex(self) -> None:
        c = _client(self.tmp, [Exception("json_validate_failed"), 'text {"ok": true} tail'])
        self.assertEqual(c.chat_json([{"role": "user", "content": "z"}]), '{"ok": true}')

    def test_api_failure_is_not_cached_and_is_reported(self) -> None:
        """
        AUDIT F-CACHE (nghiêm trọng): hết 6 lần thử (mất mạng, hết hạn mức ngày) → trả '{}' VÀ GHI VÀO CACHE.
        Chạy lại không bao giờ gọi API nữa; lỗi hạ tầng bị tính thành 'hệ thống sai' (FAILED) thay vì ERROR.
        Đúng: ném lỗi (run_cap_generation ghi ERROR, chạy lại sẽ thử lại) và không ghi cache.
        """
        c = _client(self.tmp, [Exception("Connection error")])
        with self.assertRaises(rlc.LLMCallError):
            c.chat_json([{"role": "user", "content": "q"}])
        self.assertEqual(c.cache, {})
        self.assertFalse((self.tmp / "cache.json").exists())

    def test_error_becomes_error_outcome_in_generation(self) -> None:
        """Lỗi hạ tầng → khoản ghi ERROR (score_cap từ chối chấm), không thành FAILED của hệ thống."""
        from scripts.run_cap_generation import run_clause
        from src.neural.graph_context import clause_only_chunk
        chunk = {"node_id": "X", "round": 1, "text": "Applications shall be lodged."}
        c = _client(self.tmp, [Exception("Rate limit reached for tokens per day")])
        with self.assertRaises(rlc.LLMCallError):
            run_clause(chunk, clause_only_chunk(chunk), GAMMA, c, "Y-noDuty")


class TestJudgeFailureHandling(unittest.TestCase):
    AST = {"article_id": "X", "template_name": "Existence", "activation_activity": MAIL}
    CHUNK = {"article_id": "X", "text": "Applications shall be lodged."}

    def test_judge_without_verdict_does_not_pass(self) -> None:
        """
        AUDIT F-JUDGE (nghiêm trọng): giám khảo trả JSON không có 'verdict' (VD '{}' khi API lỗi) → trước đây mặc
        định EQUIVALENT → ràng buộc QUA Tầng 3. Giờ: JudgeOutputError (khoản ghi ERROR), không bao giờ cho qua.
        """
        for reply in ("{}", '{"verdict": "OK"}', '{"diagnostic_feedback": "x"}'):
            with self.subTest(reply=reply), self.assertRaises(JudgeOutputError):
                check_roundtrip_fidelity(self.AST, self.CHUNK, SimpleNamespace(chat_json=lambda *a, r=reply, **k: r),
                                         profile=CAP_PROFILE)

    def test_valid_verdicts_still_work(self) -> None:
        ok, _ = check_roundtrip_fidelity(self.AST, self.CHUNK, SimpleNamespace(
            chat_json=lambda *a, **k: '{"verdict": "EQUIVALENT"}'), profile=CAP_PROFILE)
        self.assertTrue(ok)
        ok, msg = check_roundtrip_fidelity(self.AST, self.CHUNK, SimpleNamespace(
            chat_json=lambda *a, **k: {"verdict": "BASELESS", "diagnostic_feedback": "d"}), profile=CAP_PROFILE)
        self.assertFalse(ok)
        self.assertIn("BASELESS", msg)


class TestEntityMatcherWords(unittest.TestCase):
    def test_digit_numbers_found(self) -> None:
        self.assertIn((20.0, "days"), extract_clause_numeric_entities("within 20 days of the decision"))

    def test_numbers_written_in_words(self) -> None:
        """
        AUDIT F-WORDS (cao): văn bản CAP có ~62 chỗ số viết bằng chữ ('two working days', 'six months',
        'eight weeks') mà Entity Matcher không nhận → ràng buộc đúng với time_max=2 bị báo 'không có trong luật'
        (THRESHOLD_MISMATCH, hoặc BASELESS nếu khoản không có con số nào khác).
        """
        ents = extract_clause_numeric_entities("Notification shall be made within two working days.")
        self.assertIn(2.0, {v for v, _ in ents})


class TestPrecedenceConditionSide(unittest.TestCase):
    def test_notation_accepts_condition_on_precedence_activation(self) -> None:
        """
        AUDIT F-PREC (lan sang phiếu nhãn): với Precedence(A → B), sự kiện KÍCH HOẠT theo Declare4Py là B,
        nhưng cap_notation chỉ chấp nhận ngày(A). Người gán viết 'ngày(B)' (đúng chuẩn) bị báo LỖI.
        """
        try:
            notation_to_ast(f"Precedence({MAIL} → {PAY}) với ngày({PAY}) <= 15/05/năm", GAMMA, "X")
        except NotationError as exc:
            self.fail(str(exc))


class TestApiKeyResolution(unittest.TestCase):
    def _resolve(self, env_text: str):
        tmp = Path(tempfile.mkdtemp())
        (tmp / ".env").write_text(env_text, encoding="utf-8")
        clean = {k: v for k, v in os.environ.items()
                 if k not in ("GROQ_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "API_KEY")}
        with mock.patch.object(rlc, "PROJECT_ROOT", tmp), mock.patch.object(Path, "home", return_value=tmp), \
                mock.patch.dict(os.environ, clean, clear=True), mock.patch.object(rlc, "load_dotenv", lambda **_: False):
            return rlc._resolve_api_key()

    def test_explicit_key_wins(self) -> None:
        self.assertEqual(rlc._resolve_api_key("abc"), "abc")

    def test_groq_key_from_env_file(self) -> None:
        self.assertEqual(self._resolve("GROQ_API_KEY=gsk_test\n"), "gsk_test")

    def test_unrelated_secret_never_used_as_api_key(self) -> None:
        """
        AUDIT F-KEY (bảo mật, trung bình): thiếu GROQ/OPENAI key thì hàm lấy GIÁ TRỊ ĐẦU TIÊN có dạng X=Y trong
        .env — VD NEO4J_PASSWORD — và gửi nó làm API key tới máy chủ LLM bên ngoài.
        """
        self.assertIsNone(self._resolve("NEO4J_PASSWORD=super-secret\n"))


if __name__ == "__main__":
    unittest.main()
