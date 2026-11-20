"""
Tập Đức: khoản có `years` (VD chỉ 2015) chỉ áp cho hồ sơ của các năm đó — ở kiểm rỗng B, kiểm vi phạm hàng loạt
và bước phán quyết từng hồ sơ. Khoản không có `years` (bộ CAP) → mọi hồ sơ, như cũ.
"""

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.neural.graph_context import clause_only_chunk  # noqa: E402
from src.symbolic.declare4py_verifier import Declare4Py  # noqa: E402
from src.symbolic.log_grounding import LogGroundingChecker  # noqa: E402
from src.symbolic.process_checks import MassViolationChecker  # noqa: E402

PARCEL = "Parcel document / Main / initialize"
MAIL = "Payment application / Application / mail income"


def _engine() -> Declare4Py:
    rows = [("c15", MAIL), ("c15", PARCEL), ("c16", MAIL), ("c17", MAIL)]
    ev = pd.DataFrame([{"case:concept:name": c, "concept:name": a,
                        "time:timestamp": pd.Timestamp(f"2016-01-0{i + 1}", tz="UTC")}
                       for i, (c, a) in enumerate(rows)])
    cases = pd.DataFrame({"case:concept:name": ["c15", "c16", "c17"], "case:year": [2015, 2016, 2017]})
    return Declare4Py(ev, cases=cases, timezone="Europe/Berlin", calendar_periods=True)


def _ast(template, a, b=None):
    return {"article_id": "x", "template_name": template, "activation_activity": a, "target_activity": b,
            "activation_attr": None, "activation_op": None, "activation_val": None, "extra_conditions": [],
            "time_min": None, "time_max": None, "time_unit": None}


class TestYearScope(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = _engine()

    def test_mass_violation_only_on_clause_years(self) -> None:
        """Existence[Parcel document] cho khoản 2015: không vi phạm; trên mọi năm: 2/3 hồ sơ vi phạm."""
        m = MassViolationChecker(self.engine)
        all_years = m.assess(_ast("Existence", PARCEL))
        y2015 = m.assess(_ast("Existence", PARCEL), years=[2015])
        self.assertEqual((all_years["activated"], all_years["violated"]), (3, 2))
        self.assertEqual((y2015["activated"], y2015["violated"], y2015["mass_violation"]), (1, 0, False))

    def test_witness_and_case_count_scoped(self) -> None:
        g = LogGroundingChecker(self.engine)
        self.assertEqual(g.witness_cases(_ast("Existence", PARCEL)), 1)
        self.assertEqual(g.witness_cases(_ast("Existence", PARCEL), years=[2016, 2017]), 0)
        self.assertEqual((g.num_cases, g.cases_in([2016, 2017])), (3, 2))

    def test_years_travel_with_context_only_when_present(self) -> None:
        self.assertEqual(clause_only_chunk({"node_id": "D", "text": "t", "years": [2015]})["years"], [2015])
        self.assertNotIn("years", clause_only_chunk({"node_id": "R1:Art1", "text": "t"}))


if __name__ == "__main__":
    unittest.main()
