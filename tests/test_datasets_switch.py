"""
Công tắc tạm vô hiệu bộ BPIC2017 + Directive 2008/48/EC (src/datasets.py).

Mặc định TẮT: script riêng của BPIC2017 từ chối chạy (thoát mã 2, báo cách mở lại), test riêng của BPIC2017
được bỏ qua. Mở lại bằng biến môi trường NSAI_ENABLE_BPIC2017=1. Không file dữ liệu nào bị xoá hay di chuyển.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.datasets import ENV_FLAG, bpic2017_enabled, require_bpic2017  # noqa: E402

BPIC2017_SCRIPTS = [
    "adjudicate_gold", "build_benchmark", "build_legal_graph", "build_process_graph", "export_gold_review",
    "export_item_candidates", "run_benchmark_evaluation", "run_phase1a", "run_phase1b", "run_phase2",
    "run_phase3", "run_phase4", "run_real_llm_experiment",
]


class TestSwitch(unittest.TestCase):
    def test_disabled_by_default(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != ENV_FLAG}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(bpic2017_enabled())

    def test_enabled_only_with_1(self) -> None:
        for value, expected in (("1", True), ("0", False), ("yes", False), ("", False)):
            with mock.patch.dict(os.environ, {ENV_FLAG: value}):
                self.assertEqual(bpic2017_enabled(), expected, value)

    def test_require_exits_with_code_2_when_disabled(self) -> None:
        with mock.patch.dict(os.environ, {ENV_FLAG: "0"}):
            with self.assertRaises(SystemExit) as ctx:
                require_bpic2017("run_phase2.py")
        self.assertEqual(ctx.exception.code, 2)

    def test_require_passes_when_enabled(self) -> None:
        with mock.patch.dict(os.environ, {ENV_FLAG: "1"}):
            require_bpic2017("run_phase2.py")


class TestScriptsGuarded(unittest.TestCase):
    def test_every_bpic2017_script_calls_guard_in_main_block(self) -> None:
        for name in BPIC2017_SCRIPTS:
            text = (PROJECT_ROOT / "scripts" / f"{name}.py").read_text(encoding="utf-8")
            main_block = text.split('if __name__ == "__main__":', 1)[-1]
            with self.subTest(script=name):
                self.assertIn("require_bpic2017(", main_block)

    def test_disabled_script_refuses_and_explains(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != ENV_FLAG}
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "export_gold_review.py")],
                              capture_output=True, text=True, encoding="utf-8", env=env, cwd=PROJECT_ROOT)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn(ENV_FLAG, proc.stderr)


if __name__ == "__main__":
    unittest.main()
