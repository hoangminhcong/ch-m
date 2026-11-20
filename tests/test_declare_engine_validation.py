"""
Test cho công cụ TN4 (src/evaluation/declare_engine_validation.py): đối chiếu engine DECLARE tự viết
của NSAI với thư viện chuẩn pm4py trên mọi hồ sơ ngắn (vét cạn).
"""

import sys
import unittest
from pathlib import Path
from typing import get_args

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.declare_engine_validation import (  # noqa: E402
    REFERENCE,
    compare_template,
    exhaustive_log,
    reference_verdicts,
)
from src.mde.constraint_ast import TemplateLiteral  # noqa: E402


class TestExhaustiveLog(unittest.TestCase):
    def test_all_sequences_up_to_length(self) -> None:
        df = exhaustive_log(["A", "B"], max_len=3)
        self.assertEqual(df["case:concept:name"].nunique(), 2 + 4 + 8)

    def test_events_ordered_in_time_within_case(self) -> None:
        df = exhaustive_log(["A", "B"], max_len=2)
        for _, grp in df.groupby("case:concept:name"):
            self.assertTrue(grp["time:timestamp"].is_monotonic_increasing)


class TestReference(unittest.TestCase):
    def test_every_engine_template_has_a_reference(self) -> None:
        self.assertEqual(set(get_args(TemplateLiteral)) - set(REFERENCE), set())

    def test_standard_precedence_semantics(self) -> None:
        df = exhaustive_log(["A", "B"], max_len=2)
        verdicts = reference_verdicts(df, "Precedence", ["A", "B"])
        self.assertTrue(verdicts["A|B"])
        self.assertFalse(verdicts["B|A"])
        self.assertTrue(verdicts["A"])  # không có B -> thoả (vacuous)

    def test_standard_not_precedence_semantics(self) -> None:
        df = exhaustive_log(["A", "B"], max_len=2)
        verdicts = reference_verdicts(df, "Not Precedence", ["A", "B"])
        self.assertFalse(verdicts["A|B"])
        self.assertTrue(verdicts["B|A"])

    def test_not_response_uses_ltlf_not_pm4py_nonsuccession(self) -> None:
        """pm4py nonsuccession chỉ báo vi phạm khi MỌI B đứng sau MỌI A; LTLf G(A -> ¬F B) thì B|A|B vi phạm."""
        df = exhaustive_log(["A", "B"], max_len=3)
        verdicts = reference_verdicts(df, "Not Response", ["A", "B"])
        self.assertFalse(verdicts["B|A|B"])
        self.assertFalse(verdicts["A|B|A"])
        self.assertTrue(verdicts["B|A"])

    def test_choice_semantics(self) -> None:
        df = exhaustive_log(["A", "B", "C"], max_len=2)
        choice = reference_verdicts(df, "Choice", ["A", "B"])
        exclusive = reference_verdicts(df, "Exclusive Choice", ["A", "B"])
        self.assertFalse(choice["C"])
        self.assertTrue(choice["A|B"])
        self.assertFalse(exclusive["A|B"])
        self.assertTrue(exclusive["A|C"])


class TestCompare(unittest.TestCase):
    def setUp(self) -> None:
        self.df = exhaustive_log(["A", "B", "C"], max_len=3)

    def test_reports_counts_and_examples(self) -> None:
        result = compare_template(self.df, "Response", ["A", "B"])
        self.assertEqual(result["n_traces"], 3 + 9 + 27)
        self.assertEqual(result["n_agree"] + result["n_disagree"], result["n_traces"])
        self.assertLessEqual(len(result["examples"]), 5)

    def test_detects_an_injected_fault(self) -> None:
        """Cài một engine sai cố ý (đảo mọi kết luận) -> công cụ phải báo lệch ở mọi hồ sơ."""
        from unittest import mock

        from src.evaluation import declare_engine_validation as module

        real = module.engine_verdicts
        flipped = lambda df, tpl, acts: {c: not v for c, v in real(df, tpl, acts).items()}  # noqa: E731
        with mock.patch.object(module, "engine_verdicts", flipped):
            result = compare_template(self.df, "Response", ["A", "B"])
        self.assertEqual(result["n_disagree"], result["n_traces"])
        self.assertTrue(all("engine" in e and "reference" in e for e in result["examples"]))


if __name__ == "__main__":
    unittest.main()
