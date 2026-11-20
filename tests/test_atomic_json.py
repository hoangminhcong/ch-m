"""Ghi JSON nguyên tử + thử lại khi file bị khoá (src/evaluation/atomic_json.py) — vấn đề E1 (OneDrive)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation import atomic_json  # noqa: E402
from src.evaluation.atomic_json import write_json_atomic  # noqa: E402


class TestWriteJsonAtomic(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "sub" / "predictions_Y.json"

    def test_writes_utf8_and_leaves_no_temp_file(self) -> None:
        self.assertTrue(write_json_atomic(self.path, {"node": "Điều 33"}))
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"node": "Điều 33"})
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["predictions_Y.json"])

    def test_retries_while_locked_then_succeeds(self) -> None:
        real, calls = atomic_json.os.replace, []

        def flaky(src, dst):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError("[WinError 5] Access is denied")
            real(src, dst)

        with mock.patch.object(atomic_json.os, "replace", side_effect=flaky):
            self.assertTrue(write_json_atomic(self.path, {"a": 1}, sleep=lambda s: None))
        self.assertEqual(len(calls), 3)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"a": 1})

    def test_still_locked_keeps_old_file_intact_and_returns_false(self) -> None:
        write_json_atomic(self.path, {"old": True})
        with mock.patch.object(atomic_json.os, "replace", side_effect=PermissionError("locked")):
            self.assertFalse(write_json_atomic(self.path, {"new": True}, retries=3, sleep=lambda s: None))
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"old": True})
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["predictions_Y.json"])


class TestGenerationUsesAtomicWrite(unittest.TestCase):
    def test_no_direct_write_text_of_predictions(self) -> None:
        src = (PROJECT_ROOT / "scripts" / "run_cap_generation.py").read_text(encoding="utf-8")
        self.assertNotIn("out_path.write_text", src)
        self.assertIn("write_json_atomic(out_path", src)


if __name__ == "__main__":
    unittest.main()
