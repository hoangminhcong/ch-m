"""A6 — lõi CAP (sinh luật + chấm) không kéo theo mã BPIC2017 cũ; API cũ của gói src.evaluation vẫn dùng được."""

import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY = ("src.evaluation.experiment_runner", "src.evaluation.benchmark_builder",
          "src.evaluation.justification_tree", "src.evaluation.grounded_auditor", "sklearn")


def _loaded_after(statement: str) -> set:
    code = (f"import sys; sys.path.insert(0, {str(PROJECT_ROOT)!r}); {statement}; "
            f"print('|'.join(m for m in {LEGACY!r} if m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True)
    return set(filter(None, out.stdout.strip().split("|")))


class TestCoreImports(unittest.TestCase):
    def test_generation_and_scoring_do_not_load_legacy_modules(self) -> None:
        self.assertEqual(_loaded_after("import scripts.run_cap_generation, scripts.score_cap"), set())

    def test_legacy_names_still_importable_from_package(self) -> None:
        loaded = _loaded_after("from src.evaluation import run_ablation_experiment, check_layer1_and_layer2")
        self.assertIn("src.evaluation.experiment_runner", loaded)


if __name__ == "__main__":
    unittest.main()
