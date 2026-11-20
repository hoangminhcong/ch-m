"""
M8 — biên dịch AST → Cypher (src/kg/cypher_compiler.py) và đồ thị sự kiện (src/kg/event_graph.py).
Phần không cần Neo4j chạy luôn; phần đối chiếu Cypher ↔ engine chỉ chạy khi Neo4j kết nối được (.env), nếu không thì bỏ qua.
"""

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.cypher_compiler import UnsupportedConstraint, compile_constraint, coverage  # noqa: E402
from src.kg.event_graph import event_graph_rows, select_cases  # noqa: E402
from src.mde.constraint_ast import BINARY_TEMPLATES, UNARY_TEMPLATES  # noqa: E402


def _ast(tpl, a="A", b="B", cond=None, **extra):
    ast = {"article_id": "x", "template_name": tpl, "activation_activity": a,
           "target_activity": None if tpl in UNARY_TEMPLATES else b, **extra}
    if cond:
        ast.update(activation_attr=cond[0], activation_op=cond[1], activation_val=cond[2])
    return ast


class TestCompile(unittest.TestCase):
    def test_every_template_compiles_untimed(self) -> None:
        for tpl in sorted(UNARY_TEMPLATES | BINARY_TEMPLATES):
            with self.subTest(tpl=tpl):
                q = compile_constraint(_ast(tpl)).cypher
                self.assertIn("RETURN c.id AS case_id", q)
                self.assertIn("AS violated", q)

    def test_calendar_windows_follow_regulation_1182_71(self) -> None:
        q = compile_constraint(_ast("Response", time_min=0, time_max=30, time_unit="d")).cypher
        self.assertIn("duration({days: 30})", q)
        self.assertIn("dayOfWeek WHEN 6 THEN 2 WHEN 7 THEN 1", q)  # hạn rơi vào cuối tuần → thứ Hai
        self.assertIn("duration({months: 2})", compile_constraint(
            _ast("Response", time_min=0, time_max=2, time_unit="mo")).cypher)
        self.assertIn("duration.inDays(", compile_constraint(
            _ast("Response", time_min=0, time_max=2, time_unit="wd")).cypher)
        self.assertIn("ev[j].ts - ev[i].ts", compile_constraint(
            _ast("Response", time_min=0, time_max=3, time_unit="h")).cypher)
        # không tính theo lịch (bộ BPIC2017): ngày = 86 400 giây như engine
        self.assertIn("86400.0", compile_constraint(_ast("Response", time_min=0, time_max=1, time_unit="d"),
                                                    calendar_periods=False).cypher)

    def test_date_condition_uses_local_day_and_case_year(self) -> None:
        q = compile_constraint(_ast("Absence", cond=("date", ">", "year-05-15"))).cypher
        self.assertIn("ev[i].day >", q)
        self.assertIn("toInteger(toFloat(toString(coalesce(ev[i]['case:year'], c['case:year'])))) + 0", q)
        self.assertIn("CASE WHEN ev[i].day IS NULL", q)  # không bao giờ tính date({year: null})

    def test_still_refused_cases(self) -> None:
        with self.assertRaisesRegex(UnsupportedConstraint, "mo"):
            compile_constraint(_ast("Response", time_min=0, time_max=1, time_unit="mo"), calendar_periods=False)
        with self.assertRaisesRegex(UnsupportedConstraint, "29/02"):
            compile_constraint(_ast("Absence", cond=("date", ">", "year-02-29")))
        ok, skipped = coverage({"k1": _ast("Response"),
                                "k2": _ast("Absence", cond=("date", ">", "year-02-29"))})
        self.assertEqual((ok, [k for k, _ in skipped]), (["k1"], ["k2"]))

    def test_alternate_templates_break_on_unconditioned_activity_like_engine(self) -> None:
        q = compile_constraint(_ast("Alternate Response", cond=("flag", "==", True))).cypher
        self.assertIn("head([k IN a0 WHERE k > i])", q)
        q = compile_constraint(_ast("Alternate Precedence", cond=("flag", "==", True))).cypher
        self.assertIn("last([k IN b0 WHERE k < j])", q)

    def test_condition_follows_engine_lookup_and_coercion(self) -> None:
        q = compile_constraint(_ast("Existence", cond=("young farmer", "==", True))).cypher
        self.assertIn("coalesce(ev[i]['young farmer'], ev[i]['case:young farmer'], c['young farmer'], "
                      "c['case:young farmer'])", q)
        self.assertIn("toLower(toString(", q)
        q = compile_constraint(_ast("Existence", cond=("case:year", "==", 2016))).cypher
        self.assertIn("toFloatOrNull(toString(", q)  # chuỗi '2016' trong log vẫn bằng số 2016
        q = compile_constraint(_ast("Existence", cond=("case:area", ">=", 1.5))).cypher
        self.assertIn(">= 1.5", q)

    def test_precedence_condition_sits_on_target(self) -> None:
        q = compile_constraint(_ast("Precedence", cond=("case:x", "==", "y"))).cypher
        a_part, b_part = q.split(" AS a, ")
        self.assertNotIn("case:x", a_part.split("WITH c, ev, ")[1])
        self.assertIn("case:x", b_part)

    def test_group_activities(self) -> None:
        q = compile_constraint(_ast("Response", a="{A1 | A2}")).cypher
        self.assertIn("IN ['A1', 'A2']", q)


class TestEventGraphRows(unittest.TestCase):
    def test_rows_follow_engine_order_and_drop_missing(self) -> None:
        from src.symbolic.declare4py_verifier import Declare4Py
        ev = pd.DataFrame([{"case:concept:name": "c1", "concept:name": "B", "time:timestamp": "2017-01-02T00:00:00Z"},
                           {"case:concept:name": "c1", "concept:name": "A", "time:timestamp": "2017-01-01T00:00:00Z"}])
        cs = pd.DataFrame([{"case:concept:name": "c1", "case:area": float("nan"), "case:year": 2017}])
        engine = Declare4Py(ev, cases=cs)
        cases, events = event_graph_rows(engine._trace_index, select_cases(engine._trace_index, None))
        self.assertEqual(cases, [{"id": "c1", "props": {"case:year": 2017}}])
        self.assertEqual([(e["idx"], e["activity"]) for e in events], [(0, "A"), (1, "B")])

    def test_select_cases_is_deterministic_subset_in_engine_order(self) -> None:
        index = {f"c{i}": {} for i in range(50)}
        first, again = select_cases(index, 10), select_cases(index, 10)
        self.assertEqual(first, again)
        self.assertEqual(first, [k for k in index if k in set(first)])


class TestAgainstEngineOnNeo4j(unittest.TestCase):
    """Chỉ chạy khi Neo4j kết nối được — đối chiếu vét cạn 17 mẫu × điều kiện trên mọi vết ≤ 3 của {A, B, C}."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from src.kg.neo4j_store import Neo4jKGStore
            cls.store = Neo4jKGStore.from_env()
        except Exception as exc:  # noqa: BLE001 — không có Neo4j / .env: bỏ qua
            raise unittest.SkipTest(f"Neo4j không sẵn sàng: {type(exc).__name__}")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.store.close()

    def _check(self, engine, rules) -> None:
        from scripts.verify_cypher_compiler import compare
        from src.kg.event_graph import write_event_graph
        ids = select_cases(engine._trace_index, None)
        cases, events = event_graph_rows(engine._trace_index, ids, engine.timezone)
        with self.store._session() as session:
            write_event_graph(session, cases, events)
            rows, skipped = compare(engine, rules, session, ids)
        self.assertEqual(skipped, [])
        self.assertEqual([r for r in rows if r[3]], [])

    def test_synthetic_exhaustive(self) -> None:
        from scripts.verify_cypher_compiler import synthetic
        self._check(*synthetic())

    def test_synthetic_timed_and_dated(self) -> None:
        """Thời hạn ngày / tuần / tháng / ngày làm việc / giờ và điều kiện ngày: cuối tuần, cuối tháng, năm nhuận,
        đổi giờ, 23:30 giờ Đức."""
        from scripts.verify_cypher_compiler import synthetic_timed
        self._check(*synthetic_timed())


if __name__ == "__main__":
    unittest.main()
