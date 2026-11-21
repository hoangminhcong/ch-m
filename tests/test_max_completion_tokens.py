"""
Giới hạn độ dài câu trả lời (2026-11-21). Đo trên Cerebras: cùng prompt ~9,7k token — KHÔNG gửi giới hạn → 429 "Tokens
per minute limit exceeded" (chờ bao lâu cũng vậy: nhà cung cấp tính độ dài trả lời mặc định vào hạn mức 30k token /
phút); gửi max_completion_tokens=8000 → 200. Hai khoản v1.2 Y-noDuty (vòng sửa thứ 4–5, prompt 55–60k ký tự) lỗi vì vậy.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import src.evaluation.real_llm_client as rlc  # noqa: E402

CEREBRAS = "https://api.cerebras.ai/v1"
MSGS = [{"role": "user", "content": "q"}]


def _client(max_tokens, finish_reason="stop"):
    with mock.patch.object(rlc, "_resolve_api_key", return_value="k"):
        c = rlc.RealLLMClient(base_url=CEREBRAS, model_name="gpt-oss-120b",
                              cache_file=Path(tempfile.mkdtemp()) / "c.json", max_completion_tokens=max_tokens)
    calls = []

    def create(**kw):
        calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish_reason,
                                                        message=SimpleNamespace(content='{"a": 1}'))])

    c.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    c.calls = calls
    return c


@mock.patch.object(rlc.time, "sleep", lambda s: None)
class TestMaxCompletionTokens(unittest.TestCase):
    def test_limit_sent_only_when_set(self) -> None:
        with_limit, without = _client(8000), _client(None)
        with_limit.chat_json(MSGS)
        without.chat_json(MSGS)
        self.assertEqual(with_limit.calls[0]["max_completion_tokens"], 8000)
        self.assertNotIn("max_completion_tokens", without.calls[0])  # mặc định: request như trước

    def test_cache_key_does_not_depend_on_limit(self) -> None:
        self.assertEqual(_client(8000)._make_key(MSGS, 0.0), _client(None)._make_key(MSGS, 0.0))

    def test_truncated_answer_is_infrastructure_error_not_cached_not_retried(self) -> None:
        c = _client(100, finish_reason="length")
        with self.assertRaises(rlc.TruncatedResponseError):
            c.chat_json(MSGS)
        self.assertEqual(len(c.calls), 1)  # thử lại cùng tham số sẽ bị cắt y vậy
        self.assertEqual(c.cache, {})
        self.assertTrue(issubclass(rlc.TruncatedResponseError, rlc.LLMCallError))  # → khoản ERROR, chạy lại được

    def test_invalid_limit_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _client(0)

    def test_cli_flag_reaches_meta(self) -> None:
        import scripts.run_cap_generation as gen
        with mock.patch.object(sys, "argv", ["x", "--config", "Y", "--provider", "cerebras", "--max-tokens", "8000"]):
            args = gen._parse_args()
        self.assertEqual(args.max_tokens, 8000)
        self.assertIn('"max_completion_tokens": args.max_tokens', Path(gen.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
