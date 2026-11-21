"""
Công tắc tạm vô hiệu bộ BPIC2017 + Directive 2008/48/EC (src/datasets.py).

Mặc định TẮT: script riêng của BPIC2017 từ chối chạy (thoát mã 2, báo cách mở lại), test riêng của BPIC2017
được bỏ qua. 2026-11-21: script riêng của BPIC2017 đã gỡ (còn trong git, commit 57757a4) → chỉ còn kiểm công tắc.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.datasets import ENV_FLAG, bpic2017_enabled, require_bpic2017  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
