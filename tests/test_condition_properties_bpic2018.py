"""
Kiểm toán bước 2 — test TÍNH CHẤT cho đường đi của điều kiện dữ liệu trên Γ và bảng hồ sơ BPIC2018 THẬT:

  giá trị (như LLM trả / như phiếu nhãn ghi) → AST → dòng .decl (format_condition) → engine (data_conditions)
  → đánh giá trên bản ghi hồ sơ THẬT  ==  phép so sánh Python trên giá trị có kiểu

với MỌI thuộc tính hồ sơ trong Γ, MỌI giá trị trong miền (chuỗi / Boolean) và các ngưỡng số, mọi phép so sánh.
Lớp lỗi này (VD 'case:year == 2016' luôn sai) trước đây chỉ lộ ra tình cờ.
Cần data/processed/gamma_bpic2018.json và data/interim/bpic2018_cases.parquet; không có → bỏ qua.
"""

import json
import math
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.cap_notation import notation_to_ast  # noqa: E402
from src.mde.constraint_ast import DeclareConstraintAST  # noqa: E402
from src.symbolic.data_conditions import CASE_KEY, compile_condition  # noqa: E402

GAMMA_PATH = PROJECT_ROOT / "data" / "processed" / "gamma_bpic2018.json"
CASES = PROJECT_ROOT / "data" / "interim" / "bpic2018_cases.parquet"
MAIL = "Payment application / Application / mail income"
ORDER_OPS = ("<", "<=", ">", ">=")


def _decl_condition(attr: str, op: str, val: Any) -> str:
    ast = DeclareConstraintAST.model_validate(
        {"article_id": "P", "template_name": "Existence", "activation_activity": MAIL,
         "activation_attr": attr, "activation_op": op, "activation_val": val})
    return ast.to_declare4py_line().split("|")[1].strip()


def _expected(real: Any, op: str, val: Any, typ: str) -> bool:
    if real is None or (isinstance(real, float) and math.isnan(real)):
        return False
    if typ == "Boolean":
        a, b = str(real).lower() == "true", str(val).lower() == "true"
    elif typ in ("Float", "Integer"):
        a, b = float(real), float(val)
    else:
        a, b = str(real), str(val)
    return {"==": a == b, "!=": a != b, "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]


def _llm_value(v: Any, typ: str) -> Any:
    """Giá trị như LLM thường trả trong JSON cho kiểu Γ đó."""
    if typ == "Boolean":
        return str(v).lower() == "true"
    if typ in ("Float", "Integer"):
        return float(v)
    return str(v)


@unittest.skipUnless(GAMMA_PATH.exists() and CASES.exists(), "cần gamma_bpic2018.json và bpic2018_cases.parquet")
class TestConditionRoundTripOnRealCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gamma = json.loads(GAMMA_PATH.read_text(encoding="utf-8"))
        cls.cases = pd.read_parquet(CASES)

    def _records(self, attr: str, n: int = 400) -> List[Dict[str, Any]]:
        col = self.cases[["case:concept:name", attr]]
        sample = pd.concat([col.drop_duplicates(attr), col.sample(min(n, len(col)), random_state=3)])
        return sample.to_dict("records")

    def _mismatches(self, attr: str, op: str, val: Any, typ: str) -> List[str]:
        line = _decl_condition(attr, op, val)
        pred = compile_condition(line)
        out = []
        for rec in self._records(attr):
            ev = {CASE_KEY: {attr: rec[attr]}}
            if pred(ev) != _expected(rec[attr], op, val, typ):
                out.append(f"{line!r} trên giá trị {rec[attr]!r}: engine={pred(ev)}")
        return out

    def test_every_listed_value_every_equality_op(self) -> None:
        for attr, meta in self.gamma["case_attributes"].items():
            values = (meta.get("domain") or {}).get("values")
            if not values or attr not in self.cases:
                continue
            for v in values:
                for op in ("==", "!="):
                    with self.subTest(attr=attr, value=v, op=op):
                        self.assertEqual(self._mismatches(attr, op, _llm_value(v, meta["type"]), meta["type"])[:2], [])

    def test_numeric_thresholds_every_op(self) -> None:
        for attr, meta in self.gamma["case_attributes"].items():
            if meta["type"] not in ("Float", "Integer") or attr not in self.cases:
                continue
            col = self.cases[attr].dropna()
            for q in (0.0, 0.5, 0.9):
                val = round(float(col.quantile(q)), 2)
                for op in ORDER_OPS + ("==",):
                    with self.subTest(attr=attr, op=op, val=val):
                        self.assertEqual(self._mismatches(attr, op, val, meta["type"])[:2], [])

    def test_notation_path_same_as_llm_path(self) -> None:
        """Phiếu nhãn (cap_notation) và LLM phải ra CÙNG dòng .decl cho cùng điều kiện."""
        for attr, meta in self.gamma["case_attributes"].items():
            values = (meta.get("domain") or {}).get("values")
            if not values:
                continue
            v = values[-1]
            with self.subTest(attr=attr):
                gold = notation_to_ast(f"Existence({MAIL}) | {attr} == {v}", self.gamma, "P")
                self.assertEqual(_decl_condition(gold["activation_attr"], "==", gold["activation_val"]),
                                 _decl_condition(attr, "==", _llm_value(v, meta["type"])))


if __name__ == "__main__":
    unittest.main()
