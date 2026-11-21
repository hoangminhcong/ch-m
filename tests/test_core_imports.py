"""A6 — lõi CAP (sinh luật + chấm) không kéo theo mã cũ (grounded_auditor chỉ nạp khi cần; sklearn không nạp).
2026-11-21: phần lớn mã BPIC2017 đã gỡ; test 'tên cũ vẫn import được' bỏ theo."""

import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY = ("src.evaluation.grounded_auditor", "sklearn")


def _loaded_after(statement: str) -> set:
    code = (f"import sys; sys.path.insert(0, {str(PROJECT_ROOT)!r}); {statement}; "
            f"print('|'.join(m for m in {LEGACY!r} if m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True)
    return set(filter(None, out.stdout.strip().split("|")))


class TestCoreImports(unittest.TestCase):
    def test_generation_and_scoring_do_not_load_legacy_modules(self) -> None:
        self.assertEqual(_loaded_after("import scripts.run_cap_generation, scripts.score_cap"), set())

    def test_remaining_legacy_name_still_lazy_importable(self) -> None:
        loaded = _loaded_after("from src.evaluation import DeterministicAuditNarratorClient")
        self.assertIn("src.evaluation.grounded_auditor", loaded)


if __name__ == "__main__":
    unittest.main()
