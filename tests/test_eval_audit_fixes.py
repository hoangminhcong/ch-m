"""
Rà soát 2026-11-18 (agent rà chuỗi đánh giá): lỗi ở phần CHẤM — sửa không đổi luật hệ thống sinh, chỉ đổi thước đo.
  E-H2  template đối xứng (Choice, Exclusive Choice, Not Co-Existence) đổi chỗ activity ≠ REVERSED
  E-H3  time_min phải có trong phép so EQ
  E-M3  cùng thời hạn quy đổi nhưng khác đơn vị (5 wd ~ 7 d) → UNIT_DIFF, không phải STRENGTHENED
  E-M1  kappa không xác định (không có vi phạm ở cả hai phía) → None, không phải 1.0
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.cap_scoring import compare_ast  # noqa: E402

A, B = "Payment application / Application / mail income", "Payment application / Application / begin payment"


def _ast(template="Response", a=A, b=B, **kw):
    base = {"template_name": template, "activation_activity": a, "target_activity": b, "activation_attr": None,
            "activation_op": None, "activation_val": None, "extra_conditions": [], "time_min": None,
            "time_max": None, "time_unit": None}
    return {**base, **kw}


class TestCompareAst(unittest.TestCase):
    def test_symmetric_templates_ignore_order(self) -> None:
        for t in ("Choice", "Exclusive Choice", "Not Co-Existence"):
            with self.subTest(t=t):
                self.assertEqual(compare_ast(_ast(t, B, A), _ast(t, A, B)), "EQ")
        self.assertEqual(compare_ast(_ast("Response", B, A), _ast("Response", A, B)), "REVERSED")

    def test_time_min_compared(self) -> None:
        self.assertNotEqual(compare_ast(_ast(time_min=2, time_max=5, time_unit="d"),
                                        _ast(time_max=5, time_unit="d")), "EQ")
        self.assertEqual(compare_ast(_ast(time_min=0, time_max=5, time_unit="d"),
                                     _ast(time_min=None, time_max=5, time_unit="d")), "EQ")

    def test_same_duration_other_unit_is_unit_diff(self) -> None:
        self.assertEqual(compare_ast(_ast(time_max=5, time_unit="wd"), _ast(time_max=7, time_unit="d")), "UNIT_DIFF")
        self.assertEqual(compare_ast(_ast(time_max=14, time_unit="d"), _ast(time_max=2, time_unit="w")), "EQ")


class TestKappaDegenerate(unittest.TestCase):
    def test_no_violation_anywhere_kappa_undefined(self) -> None:
        from src.evaluation.cap_conformance import compare_verdicts
        r = compare_verdicts(["Satisfied", "Vacuously Satisfied"], ["Satisfied", "Satisfied"])
        self.assertIsNone(r["kappa"])
        self.assertEqual(r["agreement"], 1.0)


class TestNotationStrictLess(unittest.TestCase):
    def test_strict_less_than_duration_rejected(self) -> None:
        """Rà soát E-M6: '< 5 ngày' từng được lưu thành time_max = 5 (tức ≤ 5) — lệch một đơn vị, nay báo lỗi."""
        from src.evaluation.cap_notation import NotationError, notation_to_ast
        gamma = {"valid_activities": [A, B], "activities_by_origin": {},
                 "case_attributes": {"case:year": {"type": "String", "samples": []}},
                 "event_attributes": {"time:timestamp": {"type": "Timestamp", "samples": []}}}
        with self.assertRaises(NotationError):
            notation_to_ast(f"Response({A} → {B}) < 5 ngày", gamma, "R1:Art1")
        self.assertEqual(notation_to_ast(f"Response({A} → {B}) <= 5 ngày", gamma, "R1:Art1")["time_max"], 5)


class TestScoreGuards(unittest.TestCase):
    """E-H1: thiếu dự đoán / file trộn nhiều lần chạy → dừng; E-H4: khoản bị loại khỏi phép chấm được liệt kê."""

    GOLD = {"status": "approved", "clauses": {
        "T1": {"kind": "trap", "tier4": False, "gold": []}, "T2": {"kind": "trap", "tier4": False, "gold": []},
        "U1": {"kind": "uncertain", "tier4": False, "gold": []}}}

    def test_excluded_listed(self) -> None:
        import scripts.score_cap as s
        res = s.score_all(self.GOLD, {"Y": {"T1": {"outcome": "BASELESS"}, "T2": {"outcome": "BASELESS"}}})
        self.assertEqual(res["excluded"], {"uncertain": ["U1"]})

    def test_missing_predictions_refused_unless_allowed(self) -> None:
        import scripts.score_cap as s
        res = s.score_all(self.GOLD, {"Y": {"T1": {"outcome": "BASELESS"}}})
        meta = {"Y": ("cap", "gpt-oss-120b", "cerebras")}
        with self.assertRaises(SystemExit):
            s.check_predictions(res, meta, allow_missing=False, allow_mixed=False)
        s.check_predictions(res, meta, allow_missing=True, allow_mixed=False)

    def test_mixed_runs_refused_unless_allowed(self) -> None:
        import scripts.score_cap as s
        preds = {"T1": {"outcome": "BASELESS"}, "T2": {"outcome": "BASELESS"}}
        res = s.score_all(self.GOLD, {"X": preds, "Y": preds})
        meta = {"X": ("cap", "gpt-oss-120b", "groq"), "Y": ("cap", "gpt-oss-120b", "cerebras")}
        with self.assertRaises(SystemExit):
            s.check_predictions(res, meta, allow_missing=False, allow_mixed=False)
        s.check_predictions(res, meta, allow_missing=False, allow_mixed=True)


class TestGoldBuilder(unittest.TestCase):
    """E-H4 / E-H5: năm của khoản vào gold; cảnh báo nhãn thiếu / mâu thuẫn; khoản chưa gán nhãn chặn duyệt."""

    GAMMA = {"valid_activities": [A, B], "activities_by_origin": {},
             "case_attributes": {"case:year": {"type": "String", "samples": []}},
             "event_attributes": {"time:timestamp": {"type": "Timestamp", "samples": []}}}

    def _label(self, observable, constraints=(), needs_ref="Không"):
        return {"observable": observable, "constraints": list(constraints), "needs_ref": needs_ref,
                "confidence": "Cao", "reason": "x"}

    def test_years_carried_into_gold(self) -> None:
        from src.evaluation.cap_gold import classify_clause
        c = classify_clause("DE-X:§1@2016", self._label("no"), {"node_id": "DE-X:§1@2016", "text": "t",
                                                                 "years": [2016]}, self.GAMMA)
        self.assertEqual(c["years"], [2016])
        self.assertNotIn("years", classify_clause("R1:Art1", self._label("no"), {"node_id": "R1:Art1", "text": "t"},
                                                  self.GAMMA))

    def test_warnings_for_blank_needs_ref_and_ignored_constraints(self) -> None:
        from src.evaluation.cap_gold import classify_clause
        chunk = {"node_id": "R1:Art1", "text": "t"}
        c = classify_clause("R1:Art1", self._label("yes", [f"Existence({A})"], needs_ref="___"), chunk, self.GAMMA)
        self.assertTrue(any("Cần điều tham chiếu" in w for w in c["warnings"]))
        t = classify_clause("R1:Art1", self._label("no", [f"Existence({A})"]), chunk, self.GAMMA)
        self.assertTrue(any("bỏ qua" in w for w in t["warnings"]))

    def test_unlabeled_blocks_approval(self) -> None:
        from src.evaluation.cap_gold import approval_blockers
        gold = {"clauses": {"R1:Art1": {"kind": "unlabeled", "errors": []}}}
        self.assertTrue(approval_blockers(gold))


if __name__ == "__main__":
    unittest.main()
