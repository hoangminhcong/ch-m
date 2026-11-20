"""
Kiểm tập ràng buộc (src/symbolic/constraint_set_checks.py): mâu thuẫn, mâu thuẫn khi kích hoạt, kéo theo, trùng lặp;
và tính AN TOÀN — không bao giờ báo mâu thuẫn cho cặp thoả được (điều kiện khác nhau, thời hạn phủ định).
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.symbolic.constraint_set_checks import (  # noqa: E402
    _alphabet, _holds, check_constraint_set, check_pair, make_spec)


def _ast(template, a, b=None, cond=None, time_max=None):
    ast = {"article_id": "x", "template_name": template, "activation_activity": a, "target_activity": b}
    if cond:
        ast.update(activation_attr=cond[0], activation_op=cond[1], activation_val=cond[2])
    if time_max is not None:
        ast.update(time_min=0, time_max=time_max, time_unit="d")
    return ast


def _kind(x, y):
    found = check_pair(make_spec("c1", x), make_spec("c2", y))
    return found["kind"] if found else None


class TestSemantics(unittest.TestCase):
    """Ngữ nghĩa từng mẫu trên vết nhỏ (đối chiếu định nghĩa DECLARE / LTLf)."""

    def _holds(self, ast, trace):
        s = make_spec("c", ast)
        _, ci = _alphabet([s])
        return _holds(s, tuple((a, ()) for a in trace), ci)

    def test_unary_and_response_family(self) -> None:
        self.assertTrue(self._holds(_ast("Existence", "A"), ["B", "A"]))
        self.assertFalse(self._holds(_ast("Init", "A"), ["B", "A"]))
        self.assertTrue(self._holds(_ast("Response", "A", "B"), ["A", "C", "B"]))
        self.assertFalse(self._holds(_ast("Response", "A", "B"), ["B", "A"]))
        self.assertFalse(self._holds(_ast("Alternate Response", "A", "B"), ["A", "A", "B"]))
        self.assertFalse(self._holds(_ast("Chain Response", "A", "B"), ["A", "C", "B"]))
        self.assertTrue(self._holds(_ast("Not Response", "A", "B"), ["B", "A"]))

    def test_precedence_family(self) -> None:
        self.assertTrue(self._holds(_ast("Precedence", "A", "B"), ["A", "B", "B"]))
        self.assertFalse(self._holds(_ast("Precedence", "A", "B"), ["B", "A"]))
        self.assertFalse(self._holds(_ast("Alternate Precedence", "A", "B"), ["A", "B", "B"]))
        self.assertFalse(self._holds(_ast("Chain Precedence", "A", "B"), ["A", "C", "B"]))
        self.assertFalse(self._holds(_ast("Not Precedence", "A", "B"), ["A", "B"]))

    def test_activity_group_matches_any_member(self) -> None:
        self.assertTrue(self._holds(_ast("Existence", "{A | B}"), ["B"]))


class TestFindings(unittest.TestCase):
    def test_existence_vs_absence_is_conflict(self) -> None:
        self.assertEqual(_kind(_ast("Existence", "A"), _ast("Absence", "A")), "CONFLICT")

    def test_two_different_inits_conflict(self) -> None:
        self.assertEqual(_kind(_ast("Init", "A"), _ast("Init", "B")), "CONFLICT")

    def test_response_vs_not_response_conflicts_when_activated(self) -> None:
        self.assertEqual(_kind(_ast("Response", "A", "B"), _ast("Not Response", "A", "B")), "CONFLICT_IF_ACTIVATED")

    def test_existence_forces_violation_of_not_coexistence_when_activated(self) -> None:
        # trường hợp thật của Y: Existence[C] (R1306:Art7(6)) và Not Co-Existence[X, C] (R809:Art34(1))
        self.assertEqual(_kind(_ast("Existence", "C"), _ast("Not Co-Existence", "X", "C")), "CONFLICT_IF_ACTIVATED")

    def test_conditioned_existence_implies_unconditioned(self) -> None:
        f = check_pair(make_spec("narrow", _ast("Existence", "A", cond=("case:year", "==", 2015))),
                       make_spec("broad", _ast("Existence", "A")))
        self.assertEqual((f["kind"], f["a"], f["b"]), ("IMPLIES", "narrow", "broad"))

    def test_duplicate_line(self) -> None:
        self.assertEqual(_kind(_ast("Response", "A", "B"), _ast("Response", "A", "B")), "DUPLICATE")

    def test_unrelated_and_compatible_pairs_report_nothing(self) -> None:
        self.assertIsNone(_kind(_ast("Existence", "A"), _ast("Absence", "B")))
        self.assertIsNone(_kind(_ast("Response", "A", "B"), _ast("Precedence", "A", "B")))


class TestSoundness(unittest.TestCase):
    """Không bịa mâu thuẫn."""

    def test_existence_and_absence_under_different_conditions_not_conflict(self) -> None:
        # A với year==2015 và A với year==2016 có thể cùng xuất hiện / không — không được báo mâu thuẫn
        x = _ast("Existence", "A", cond=("case:year", "==", 2015))
        y = _ast("Absence", "A", cond=("case:year", "==", 2016))
        self.assertIsNone(_kind(x, y))

    def test_timed_negative_template_is_skipped(self) -> None:
        # Not Response trong 10 ngày + Response trong 30 ngày thoả được (B ở ngày 20) — phải bỏ qua, không báo
        self.assertIsNone(_kind(_ast("Response", "A", "B", time_max=30), _ast("Not Response", "A", "B", time_max=10)))

    def test_timed_positive_is_weakened_conflict_still_real(self) -> None:
        self.assertEqual(_kind(_ast("Response", "A", "B", time_max=30), _ast("Not Response", "A", "B")),
                         "CONFLICT_IF_ACTIVATED")

    def test_no_implication_claimed_for_timed_pairs(self) -> None:
        self.assertIsNone(_kind(_ast("Response", "A", "B", time_max=30), _ast("Response", "A", "B", time_max=60)))

    def test_set_checks_all_pairs_in_stable_order(self) -> None:
        rules = {"k2": _ast("Absence", "A"), "k1": _ast("Existence", "A"), "k3": _ast("Existence", "Z")}
        found = check_constraint_set(rules)
        self.assertEqual([(f["a"], f["b"], f["kind"]) for f in found], [("k1", "k2", "CONFLICT")])


class TestExactAutomata(unittest.TestCase):
    """2026-11-20: kiểm cặp dùng DFA (chính xác mọi độ dài). DFA của từng mẫu phải khớp ngữ nghĩa LTLf `_holds`
    trên MỌI vết ngắn — kể cả khi A và B là cùng activity và khi có điều kiện dữ liệu."""

    def test_dfa_matches_definition_for_every_template(self) -> None:
        from src.mde.constraint_ast import BINARY_TEMPLATES, UNARY_TEMPLATES
        from src.symbolic.constraint_set_checks import _traces, accepts
        cases = [("A", "B", None), ("A", "A", None), ("A", "B", ("case:x", "==", True))]
        for tpl in sorted(UNARY_TEMPLATES | BINARY_TEMPLATES):
            for a, b, cond in cases:
                spec = make_spec("c", _ast(tpl, a, None if tpl in UNARY_TEMPLATES else b, cond=cond))
                symbols, ci = _alphabet([spec])
                for trace in _traces(symbols + [("B", ())] if "B" not in {s[0] for s in symbols} else symbols, 5):
                    with self.subTest(tpl=tpl, a=a, b=b, cond=bool(cond), trace=trace):
                        self.assertEqual(accepts(spec, trace, ci), _holds(spec, trace, ci))

    def test_timed_response_inside_longer_ban_is_conflict(self) -> None:
        self.assertEqual(_kind(_ast("Response", "A", "B", time_max=10), _ast("Not Response", "A", "B", time_max=30)),
                         "CONFLICT_IF_ACTIVATED")
        self.assertEqual(_kind(_ast("Response", "A", "B", time_max=30), _ast("Not Response", "A", "B", time_max=30)),
                         "CONFLICT_IF_ACTIVATED")

    def test_timed_window_needs_same_fixed_unit(self) -> None:
        x = {**_ast("Response", "A", "B", time_max=1), "time_unit": "mo"}
        y = {**_ast("Not Response", "A", "B", time_max=60), "time_unit": "mo"}
        self.assertIsNone(_kind(x, y))  # tháng: độ dài không cố định → không kết luận
        z = {**_ast("Not Response", "A", "B", time_max=60), "time_unit": "h"}
        self.assertIsNone(_kind(_ast("Response", "A", "B", time_max=1), z))  # khác đơn vị


if __name__ == "__main__":
    unittest.main()
