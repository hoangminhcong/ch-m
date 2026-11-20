"""M9 — nhãn REVIEW (đăng ký trước B7; src/evaluation/review_flags.py): 5 tín hiệu cố định, mức = số tín hiệu,
bảng giữ lại — rủi ro theo gold. Mô tả: không đổi đầu ra / điểm."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.review_flags import MAX_LEVEL, SIGNALS, markdown, risk_coverage, rule_signals, summary  # noqa: E402

PAY = "Payment application / Main / begin payment"
INSPECT = "Inspection / On-Site / performed"
AST = {"template_name": "Existence", "activation_activity": PAY, "target_activity": None}


def _trace(clause, findings=(), level="verbatim", vacuous=False):
    return {"clause": clause, "decl": f"Existence[{PAY}] | |", "set_findings": list(findings),
            "evidence": {"level": level}, "grounding": {"vacuous": vacuous}}


class TestSignals(unittest.TestCase):
    def test_clean_rule_has_no_flag(self) -> None:
        f = rule_signals(_trace("A"), AST, {"activated": 100, "violated": 20, "ratio": 0.2},
                         frozenset({"Payment application"}))
        self.assertEqual((f["level"], f["review"]), (0, False))  # đúng 0,20 chưa vượt ngưỡng

    def test_each_signal(self) -> None:
        conflict = {"a": "A", "b": "B", "kind": "CONFLICT_IF_ACTIVATED"}
        f = rule_signals(_trace("A", [conflict, {"a": "A", "b": "C", "kind": "IMPLIES"}], "unsupported", True),
                         {**AST, "activation_activity": INSPECT}, {"activated": 10, "violated": 9, "ratio": 0.9},
                         frozenset({"Payment application"}))
        self.assertEqual(f["level"], MAX_LEVEL)
        self.assertEqual(f["evidence"]["conflicts_with"], ["B"])  # IMPLIES không phải mâu thuẫn

    def test_missing_inputs_do_not_raise_signals(self) -> None:
        f = rule_signals(_trace("A"), AST, None, None)  # không log, chưa có ontology đã duyệt
        self.assertFalse(f["signals"]["S1_mass_violation"] or f["signals"]["S2_no_kg_support"])
        self.assertIsNone(f["evidence"]["kg_support"])


class TestRiskCoverage(unittest.TestCase):
    def setUp(self) -> None:
        self.flags = {"T1": {"level": 2}, "T2": {"level": 0}, "P1": {"level": 1}, "U1": {"level": 0}}
        rule = {"outcome": "RULE", "ast": {**AST, "activation_attr": None, "activation_op": None,
                                            "activation_val": None, "extra_conditions": [], "time_min": None,
                                            "time_max": None, "time_unit": None}}
        self.preds = {n: rule for n in self.flags}
        self.gold = {"T1": {"kind": "trap"}, "T2": {"kind": "trap"}, "P1": {"kind": "positive", "gold": [rule["ast"]]}}

    def test_rows_from_keep_all_to_keep_none(self) -> None:
        rows = risk_coverage(self.flags, self.preds, self.gold)
        self.assertEqual([r["keep_if_level_below"] for r in rows], list(range(MAX_LEVEL + 1, 0, -1)))
        keep_all, keep_below_1 = rows[0], rows[-1]
        self.assertEqual((keep_all["kept"], keep_all["false_on_trap"], keep_all["correct_on_positive"],
                          keep_all["not_scored"]), (4, 2, 1, 1))
        self.assertEqual((keep_below_1["kept"], keep_below_1["false_on_trap"], keep_below_1["correct_on_positive"]),
                         (2, 1, 0))

    def test_without_gold_only_counts(self) -> None:
        self.assertNotIn("false_on_trap", risk_coverage(self.flags, self.preds)[0])

    def test_summary_and_markdown(self) -> None:
        flags = {"A": rule_signals(_trace("A"), AST, {"activated": 10, "violated": 9, "ratio": 0.9}, None)}
        s = summary(flags)
        self.assertEqual((s["rules"], s["review"], s["by_signal"]["S1_mass_violation"]), (1, 1, 1))
        self.assertEqual(set(s["by_signal"]), set(SIGNALS))
        md = markdown("Y", flags, risk_coverage(flags, {"A": {"outcome": "RULE"}}))
        self.assertIn("không đổi điểm", md)
        self.assertNotIn("Sai trên bẫy", md)


if __name__ == "__main__":
    unittest.main()
