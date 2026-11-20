"""
Chạy CAP trên nhà cung cấp khác (Cerebras) — chỉ phần hạ tầng gọi API, không đổi prompt hay cách kiểm:
- key chọn theo máy chủ: gọi Cerebras KHÔNG BAO GIỜ gửi GROQ_API_KEY (và ngược lại không đổi hành vi cũ);
- giãn cách tối thiểu giữa hai lần gọi (hạn mức request/phút);
- thời gian chờ sau 429: Retry-After → 'try again in Xs' → tăng dần;
- run_cap_generation: --provider điền base-url/model, cache mặc định riêng từng cấu hình.
Không gọi mạng, không đọc .env thật.
"""

import argparse
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
from scripts.run_cap_generation import PROVIDERS, resolve_endpoint  # noqa: E402

CEREBRAS = "https://api.cerebras.ai/v1"
GROQ = "https://api.groq.com/openai/v1"
ALL_KEY_VARS = ("GROQ_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "API_KEY", "CEREBRAS_API_KEY")


def _resolve(env_text: str, base_url: str, key_var=None):
    tmp = Path(tempfile.mkdtemp())
    (tmp / ".env").write_text(env_text, encoding="utf-8")
    clean = {k: v for k, v in os.environ.items() if not k.endswith(ALL_KEY_VARS) and "API_KEY" not in k}
    with mock.patch.object(rlc, "PROJECT_ROOT", tmp), mock.patch.object(Path, "home", return_value=tmp), \
            mock.patch.dict(os.environ, clean, clear=True), mock.patch.object(rlc, "load_dotenv", lambda **_: False):
        return rlc._resolve_api_key(base_url=base_url, key_var=key_var)


class TestSecondKeyPerWindow(unittest.TestCase):
    TWO = "CEREBRAS_API_KEY=csk-one\nCEREBRAS_API_KEY_2=csk-two\nGROQ_API_KEY=gsk_groq\n"

    def test_window_picks_its_own_key(self) -> None:
        self.assertEqual(_resolve(self.TWO, CEREBRAS), "csk-one")
        self.assertEqual(_resolve(self.TWO, CEREBRAS, "CEREBRAS_API_KEY_2"), "csk-two")

    def test_selected_key_missing_does_not_fall_back(self) -> None:
        """Cửa sổ 2 thiếu key 2 → báo lỗi, KHÔNG lặng lẽ dùng key 1 (hai cửa sổ sẽ tranh một hạn mức)."""
        self.assertIsNone(_resolve("CEREBRAS_API_KEY=csk-one\n", CEREBRAS, "CEREBRAS_API_KEY_2"))

    def test_cannot_point_cerebras_at_other_provider_key(self) -> None:
        for bad in ("GROQ_API_KEY", "NEO4J_PASSWORD", "cerebras_api_key_2", "CEREBRAS_API_KEY-2"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                rlc.key_vars_for(CEREBRAS, bad)


class TestKeyPerProvider(unittest.TestCase):
    BOTH = "GROQ_API_KEY=gsk_groq\nCEREBRAS_API_KEY=csk-cere\n"

    def test_cerebras_uses_only_its_own_key(self) -> None:
        self.assertEqual(_resolve(self.BOTH, CEREBRAS), "csk-cere")

    def test_cerebras_never_receives_groq_key(self) -> None:
        self.assertIsNone(_resolve("GROQ_API_KEY=gsk_groq\n", CEREBRAS))
        self.assertIsNone(_resolve("gsk_plainline\n", CEREBRAS))

    def test_groq_behaviour_unchanged(self) -> None:
        self.assertEqual(_resolve(self.BOTH, GROQ), "gsk_groq")
        self.assertEqual(_resolve("GROQ_API_KEY=gsk_groq\n", None), "gsk_groq")

    def test_missing_key_message_names_provider_variable(self) -> None:
        with mock.patch.object(rlc, "_resolve_api_key", return_value=None), \
                self.assertRaisesRegex(ValueError, "CEREBRAS_API_KEY"):
            rlc.RealLLMClient(base_url=CEREBRAS, cache_file=Path(tempfile.mkdtemp()) / "c.json")


class FakeClock:
    def __init__(self) -> None:
        self.now, self.sleeps = 100.0, []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s


def _client(min_interval: float, replies) -> "rlc.RealLLMClient":
    with mock.patch.object(rlc, "_resolve_api_key", return_value="k"):
        c = rlc.RealLLMClient(base_url=CEREBRAS, model_name="gpt-oss-120b",
                              cache_file=Path(tempfile.mkdtemp()) / "c.json", min_interval=min_interval)
    calls = []

    def create(**kw):
        calls.append(kw)
        r = replies.pop(0) if len(replies) > 1 else replies[0]
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=r))])

    c.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    c.calls = calls
    return c


class TestThrottle(unittest.TestCase):
    def test_consecutive_calls_spaced_by_min_interval(self) -> None:
        clock = FakeClock()
        with mock.patch.object(rlc, "time", clock):
            c = _client(13.0, ['{"a": 1}'])
            c.chat_json([{"role": "user", "content": "1"}])
            c.chat_json([{"role": "user", "content": "2"}])
        self.assertEqual(len(c.calls), 2)
        # sau lần 1 client tự nghỉ 1,2 s (như cũ) → lần 2 chờ thêm 11,8 s; cộng 1,2 s sau lần 2
        self.assertAlmostEqual(sum(clock.sleeps), 1.2 + 11.8 + 1.2, places=6)

    def test_cache_hit_does_not_wait(self) -> None:
        clock = FakeClock()
        with mock.patch.object(rlc, "time", clock):
            c = _client(13.0, ['{"a": 1}'])
            msgs = [{"role": "user", "content": "same"}]
            c.chat_json(msgs)
            before = list(clock.sleeps)
            c.chat_json(msgs)
        self.assertEqual(clock.sleeps, before)

    def test_zero_interval_keeps_old_behaviour(self) -> None:
        clock = FakeClock()
        with mock.patch.object(rlc, "time", clock):
            c = _client(0.0, ['{"a": 1}'])
            c.chat_json([{"role": "user", "content": "1"}])
            c.chat_json([{"role": "user", "content": "2"}])
        self.assertEqual(clock.sleeps, [1.2, 1.2])

    def test_negative_interval_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _client(-1.0, ["{}"])


class TestRateLimitWait(unittest.TestCase):
    def _err(self, msg: str, headers=None) -> Exception:
        e = Exception(msg)
        e.response = SimpleNamespace(headers=headers or {})
        return e

    def test_retry_after_header_wins_and_is_capped(self) -> None:
        self.assertEqual(rlc.rate_limit_wait(self._err("429", {"retry-after": "7"}), 0), 8.0)
        self.assertEqual(rlc.rate_limit_wait(self._err("429", {"retry-after": "9999"}), 0),
                         rlc.RETRY_AFTER_CAP_S + 1.0)

    def test_groq_message_still_parsed(self) -> None:
        self.assertAlmostEqual(rlc.rate_limit_wait(self._err("Rate limit. Please try again in 2.5s."), 0), 4.0)

    def test_cerebras_style_message_backs_off_progressively(self) -> None:
        err = self._err("429 Too Many Requests: uncached token limit exceeded")
        self.assertEqual([rlc.rate_limit_wait(err, i) for i in range(6)], [10.0, 20.0, 30.0, 40.0, 50.0, 60.0])

    def test_rate_limited_call_recovers(self) -> None:
        clock = FakeClock()
        with mock.patch.object(rlc, "time", clock):
            c = _client(0.0, [Exception("429 Too Many Requests"), '{"ok": 1}'])
            self.assertEqual(c.chat_json([{"role": "user", "content": "x"}]), '{"ok": 1}')
        self.assertIn(10.0, clock.sleeps)


class TestGenerationEndpoint(unittest.TestCase):
    def _args(self, **kw) -> argparse.Namespace:
        base = {"provider": "groq", "model": None, "base_url": None, "cache_file": None,
                "out_dir": "results/cap_x", "config": "Y"}
        return resolve_endpoint(argparse.Namespace(**{**base, **kw}))

    def test_provider_presets(self) -> None:
        a = self._args(provider="cerebras")
        self.assertEqual((a.base_url, a.model), PROVIDERS["cerebras"])
        self.assertEqual(a.model, "gpt-oss-120b")
        self.assertEqual(self._args().model, "openai/gpt-oss-120b")

    def test_groq_env_settings_never_hijack_cerebras(self) -> None:
        env = {"LLM_MODEL_NAME": "openai/gpt-oss-120b", "LLM_BASE_URL": GROQ}
        with mock.patch.dict(os.environ, env):
            self.assertEqual((self._args(provider="cerebras").base_url, self._args(provider="cerebras").model),
                             PROVIDERS["cerebras"])
            self.assertEqual(self._args().base_url, GROQ)

    def test_explicit_values_not_overridden(self) -> None:
        a = self._args(provider="cerebras", model="qwen-3.8-27b", cache_file="c.json")
        self.assertEqual((a.model, a.cache_file), ("qwen-3.8-27b", "c.json"))

    def test_default_cache_is_per_config(self) -> None:
        self.assertNotEqual(self._args(config="Y").cache_file, self._args(config="X").cache_file)
        self.assertEqual(Path(self._args(config="X").cache_file), Path("results/cap_x") / "llm_cache_X.json")


class TestCacheSafety(unittest.TestCase):
    """Rà soát lõi 2026-11-18 H3: hai tiến trình chung một file cache không xoá mục của nhau; file hỏng được giữ lại."""

    def _client(self, path):
        with mock.patch.object(rlc, "_resolve_api_key", return_value="k"):
            return rlc.RealLLMClient(base_url=CEREBRAS, model_name="gpt-oss-120b", cache_file=path)

    def test_two_writers_merge(self) -> None:
        path = Path(tempfile.mkdtemp()) / "c.json"
        a, b = self._client(path), self._client(path)
        a.cache["k1"] = "v1"
        a._save_cache()
        b.cache["k2"] = "v2"
        b._save_cache()
        import json
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"k1": "v1", "k2": "v2"})

    def test_corrupt_cache_preserved_not_overwritten(self) -> None:
        path = Path(tempfile.mkdtemp()) / "c.json"
        path.write_text('{"k1": "v1", ', encoding="utf-8")
        c = self._client(path)
        self.assertEqual(c.cache, {})
        self.assertEqual(len(list(path.parent.glob("c.corrupt-*.json"))), 1)

    def test_locked_cache_file_retried_then_saved(self) -> None:
        """2026-11-20: OneDrive giữ khoá file → 'Access is denied' ở os.replace; thử lại thay vì làm hỏng khoản."""
        path = Path(tempfile.mkdtemp()) / "c.json"
        c = self._client(path)
        c.cache["k1"] = "v1"
        real_replace, calls = rlc.os.replace, []

        def flaky(src, dst):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError("[WinError 5] Access is denied")
            return real_replace(src, dst)

        with mock.patch.object(rlc.os, "replace", side_effect=flaky), mock.patch.object(rlc.time, "sleep"):
            c._save_cache()
        import json
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"k1": "v1"})
        self.assertEqual(len(calls), 3)

    def test_permanently_locked_cache_warns_without_raising(self) -> None:
        path = Path(tempfile.mkdtemp()) / "c.json"
        c = self._client(path)
        c.cache["k1"] = "v1"
        with mock.patch.object(rlc.os, "replace", side_effect=PermissionError("locked")), \
                mock.patch.object(rlc.time, "sleep"), mock.patch.object(rlc.sys, "stderr") as err:
            c._save_cache()  # không ném lỗi → khoản đang chạy không bị đánh ERROR
        self.assertIn("không ghi được", "".join(a[0][0] for a in err.write.call_args_list))
        self.assertEqual(c.cache, {"k1": "v1"})  # vẫn giữ trong bộ nhớ cho lần lưu sau


class TestResumeGuard(unittest.TestCase):
    """Rà soát 2026-11-18 MEDIUM-2: chạy tiếp vào file của bộ dữ liệu / model / nhà cung cấp khác → dừng."""

    def _args(self, **kw):
        base = {"dataset": "cap", "model": "gpt-oss-120b", "provider": "cerebras", "force": False}
        return argparse.Namespace(**{**base, **kw})

    def test_same_run_resumes(self) -> None:
        from scripts.run_cap_generation import check_resume
        check_resume({"model": "gpt-oss-120b", "provider": "cerebras", "predictions": {}}, self._args())
        check_resume({}, self._args())  # file mới

    def test_mismatch_refused_unless_force(self) -> None:
        from scripts.run_cap_generation import check_resume
        doc = {"model": "gpt-oss-120b", "provider": "cerebras", "predictions": {"R1:Art1": {}}}
        for bad in (self._args(dataset="de"), self._args(provider="groq"), self._args(model="qwen-3.8-27b")):
            with self.subTest(args=bad), self.assertRaises(SystemExit):
                check_resume(doc, bad)
        check_resume(doc, self._args(dataset="de", force=True))


if __name__ == "__main__":
    unittest.main()
