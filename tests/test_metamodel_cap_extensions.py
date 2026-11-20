"""
Mở rộng metamodel (AST, Tầng 1) và Γ (Tầng 2) ĐỒNG BỘ với engine (data_conditions.py) cho bộ CAP:
  - nhiều điều kiện nối 'and' (extra_conditions);
  - thuộc tính giả 'date' với giá trị year-MM-DD / year+k-MM-DD / YYYY-MM-DD.
Ràng buộc BPIC2017 cũ (không dùng trường mới) phải sinh đúng dòng .decl như trước.
"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.mde.constraint_ast import DeclareConstraintAST, validate_layer1_ast  # noqa: E402
from src.mde.typing_environment import ProcessTypingEnvironment  # noqa: E402
from src.symbolic.data_conditions import compile_condition  # noqa: E402
from src.symbolic.verbalizer_roundtrip import verbalize_declare_ast  # noqa: E402

MAIL = "Payment application / Application / mail income"
PAY = "Payment application / Application / begin payment"
SCHEMA = {
    "valid_activities": [MAIL, PAY],
    "activities_by_origin": {"Payment application": [MAIL, PAY]},
    "case_attributes": {
        "case:year": {"type": "String", "samples": ["2015", "2016", "2017"]},
        "case:young farmer": {"type": "Boolean", "samples": ["False", "True"]},
        "case:area": {"type": "Float", "samples": [0.0, 576.07]},
    },
    "event_attributes": {"time:timestamp": {"type": "Timestamp", "samples": []}},
}
NO_YEAR_SCHEMA = {**SCHEMA, "case_attributes": {k: v for k, v in SCHEMA["case_attributes"].items() if k != "case:year"}}


def _ast(**kw) -> DeclareConstraintAST:
    base = {"article_id": "R809:Art13(1)", "template_name": "Existence", "activation_activity": MAIL}
    return DeclareConstraintAST.model_validate({**base, **kw})


class TestASTSerialization(unittest.TestCase):
    def test_bpic2017_line_unchanged(self) -> None:
        ast = DeclareConstraintAST(
            article_id="Article 10(1)", template_name="Response", activation_activity="O_Accepted",
            target_activity="A_Pending", activation_attr="OfferedAmount", activation_op=">=",
            activation_val=200.0, time_max=30)
        self.assertEqual(ast.to_declare4py_line(), "Response[O_Accepted, A_Pending] | A.OfferedAmount >= 200.0 | | 0,30,d")
        self.assertEqual(ast.extra_conditions, [])

    def test_conjunction_line(self) -> None:
        ast = _ast(template_name="Response", target_activity=PAY, activation_attr="case:young farmer",
                   activation_op="==", activation_val=True,
                   extra_conditions=[{"attr": "case:area", "op": ">", "val": 10}])
        self.assertEqual(ast.to_declare4py_line(),
                         f"Response[{MAIL}, {PAY}] | A.case:young farmer == True and A.case:area > 10 | | ")

    def test_date_value_not_quoted(self) -> None:
        ast = _ast(activation_attr="date", activation_op="<=", activation_val="year-05-15")
        self.assertEqual(ast.to_declare4py_line(), f"Existence[{MAIL}] | A.date <= year-05-15 | | ")

    def test_window_with_year_offset(self) -> None:
        ast = _ast(activation_attr="date", activation_op=">=", activation_val="year-12-01",
                   extra_conditions=[{"attr": "date", "op": "<=", "val": "year+1-06-30"}])
        self.assertIn("A.date >= year-12-01 and A.date <= year+1-06-30", ast.to_declare4py_line())

    def test_serialized_condition_runs_on_engine(self) -> None:
        """Dòng do metamodel sinh ra phải được engine hiểu đúng (không rơi về 'luôn đúng')."""
        ast = _ast(activation_attr="date", activation_op="<=", activation_val="year-05-15",
                   extra_conditions=[{"attr": "case:young farmer", "op": "==", "val": True}])
        cond = compile_condition(ast.to_declare4py_line().split("|")[1].strip(), timezone="Europe/Berlin")
        late = datetime(2016, 5, 15, 22, 30, tzinfo=timezone.utc).timestamp()  # 00:30 ngày 16/5 giờ Đức
        ok = datetime(2016, 5, 15, 21, 0, tzinfo=timezone.utc).timestamp()
        case = {"case:year": "2016", "case:young farmer": True}
        self.assertTrue(cond({"_ts_sec": ok, "_case": case}))
        self.assertFalse(cond({"_ts_sec": late, "_case": case}))
        self.assertFalse(cond({"_ts_sec": ok, "_case": {**case, "case:young farmer": False}}))


class TestLayer1(unittest.TestCase):
    def test_rejects_malformed_date(self) -> None:
        ok, msg = validate_layer1_ast({"article_id": "x", "template_name": "Existence", "activation_activity": MAIL,
                                       "activation_attr": "date", "activation_op": "<=", "activation_val": "15/05"})
        self.assertFalse(ok)
        self.assertIn("date", str(msg))

    def test_rejects_malformed_date_in_extra(self) -> None:
        ok, _ = validate_layer1_ast({"article_id": "x", "template_name": "Existence", "activation_activity": MAIL,
                                     "activation_attr": "case:area", "activation_op": ">", "activation_val": 1,
                                     "extra_conditions": [{"attr": "date", "op": "<=", "val": "May 15"}]})
        self.assertFalse(ok)

    def test_extra_conditions_require_primary_condition(self) -> None:
        ok, msg = validate_layer1_ast({"article_id": "x", "template_name": "Existence", "activation_activity": MAIL,
                                       "extra_conditions": [{"attr": "case:area", "op": ">", "val": 1}]})
        self.assertFalse(ok)
        self.assertIn("extra_conditions", str(msg))


class TestLayer2Gamma(unittest.TestCase):
    def setUp(self) -> None:
        self.gamma = ProcessTypingEnvironment(SCHEMA)

    def test_relative_date_accepted_when_year_attribute_exists(self) -> None:
        ok, err = self.gamma.validate_ast(_ast(activation_attr="date", activation_op="<=", activation_val="year-05-15"))
        self.assertTrue(ok, err)

    def test_relative_date_rejected_without_year_attribute(self) -> None:
        ok, err = ProcessTypingEnvironment(NO_YEAR_SCHEMA).validate_ast(
            _ast(activation_attr="date", activation_op="<=", activation_val="year-05-15"))
        self.assertFalse(ok)
        self.assertIn("case:year", err)

    def test_absolute_date_needs_no_year_attribute(self) -> None:
        ok, err = ProcessTypingEnvironment(NO_YEAR_SCHEMA).validate_ast(
            _ast(activation_attr="date", activation_op="<", activation_val="2016-01-01"))
        self.assertTrue(ok, err)

    def test_extra_condition_unknown_attribute_rejected(self) -> None:
        ok, err = self.gamma.validate_ast(_ast(
            activation_attr="case:area", activation_op=">", activation_val=10,
            extra_conditions=[{"attr": "case:old farmer", "op": "==", "val": True}]))
        self.assertFalse(ok)
        self.assertIn("case:old farmer", err)

    def test_extra_condition_type_violation_rejected(self) -> None:
        ok, err = self.gamma.validate_ast(_ast(
            activation_attr="case:area", activation_op=">", activation_val=10,
            extra_conditions=[{"attr": "case:young farmer", "op": ">", "val": 1}]))
        self.assertFalse(ok)
        self.assertIn("young farmer", err)

    def test_attribute_with_space_and_boolean(self) -> None:
        ok, err = self.gamma.validate_ast(_ast(activation_attr="case:young farmer", activation_op="==",
                                               activation_val=True))
        self.assertTrue(ok, err)


class TestVerbalizer(unittest.TestCase):
    def test_extra_conditions_verbalized(self) -> None:
        ast = _ast(activation_attr="case:area", activation_op=">", activation_val=10,
                   extra_conditions=[{"attr": "date", "op": "<=", "val": "year-05-15"}])
        text = verbalize_declare_ast(ast.model_dump())
        self.assertIn("case:area > 10", text)
        self.assertIn("date <= year-05-15", text)

    def test_bpic2017_verbalization_unchanged_without_extra(self) -> None:
        ast = _ast(activation_attr="case:area", activation_op=">", activation_val=10)
        d = ast.model_dump()
        d.pop("extra_conditions")
        self.assertEqual(verbalize_declare_ast(ast.model_dump()), verbalize_declare_ast(d))


if __name__ == "__main__":
    unittest.main()
