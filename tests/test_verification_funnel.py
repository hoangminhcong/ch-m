"""Phễu kiểm chứng (src/evaluation/verification_funnel.py): đếm vòng theo lớp kiểm, luật sửa được, luật sai lọt qua."""

import re
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.verification_funnel import LAYER_OF, funnel, markdown_table  # noqa: E402


def _p(outcome, *statuses):
    return {"outcome": outcome, "trajectory": [{"round": i + 1, "status": s} for i, s in enumerate(statuses)]}


PREDS = {"a": _p("RULE", "FAILED_L1_L2", "FAILED_L3_ROUNDTRIP", "PASSED"),
         "b": _p("BASELESS", "DECLINED_NO_OBLIGATION"),
         "c": _p("RULE", "PASSED"),
         "d": _p("FAILED", "FAILED_VACUITY", "FAILED_VACUITY")}
GOLD = {"a": {"kind": "positive"}, "b": {"kind": "trap"}, "c": {"kind": "trap"}, "d": {"kind": "trap"}}


class TestFunnel(unittest.TestCase):
    def test_counts_rounds_rejections_and_fixes(self) -> None:
        f = funnel(PREDS)
        self.assertEqual(f["llm_rounds"], 7)
        self.assertEqual(f["rejected_rounds"], 4)
        self.assertEqual(f["rules_fixed_after_rejection"], 1)
        self.assertEqual(f["first_round_by_status"]["FAILED_L1_L2"], 1)
        self.assertEqual(f["final_rules_not_passed"], 0)

    def test_false_rules_on_traps_need_gold(self) -> None:
        self.assertNotIn("false_rules_on_traps", funnel(PREDS))
        f = funnel(PREDS, GOLD)
        self.assertEqual((f["false_rules_on_traps"], f["gold_traps"]), (["c"], 3))

    def test_table_has_one_column_per_config(self) -> None:
        table = markdown_table({"X": funnel(PREDS, GOLD), "Y": funnel(PREDS, GOLD)})
        self.assertIn("| Lớp kiểm (số vòng) | X | Y |", table)
        self.assertIn("1/3", table)

    def test_every_status_emitted_by_the_loop_is_mapped(self) -> None:
        src = (PROJECT_ROOT / "src" / "evaluation" / "real_llm_client.py").read_text(encoding="utf-8")
        emitted = set(re.findall(r'"((?:FAILED|DECLINED|DETECTED)_[A-Z0-9_]+)"', src))
        self.assertEqual(emitted - set(LAYER_OF), set())


if __name__ == "__main__":
    unittest.main()
