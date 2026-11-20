"""
Ngữ nghĩa của kiểm tập ràng buộc (`_holds` và DFA, src/symbolic/constraint_set_checks.py) phải khớp ENGINE Declare4Py —
chuẩn mà mọi kết quả trên log dùng. 2026-11-20: trước đây DFA chỉ được so với `_holds`, nên khi `_holds` lệch engine
(Choice / Exclusive Choice có điều kiện: engine áp điều kiện cho cả A và B) không test nào bắt được. Test này so
THẲNG với engine: 17 mẫu × (không / có điều kiện hồ sơ) trên mọi vết độ dài 1..4 của {A, B, C}.
"""

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.declare_engine_validation import exhaustive_log  # noqa: E402
from src.mde.constraint_ast import BINARY_TEMPLATES, UNARY_TEMPLATES  # noqa: E402
from src.symbolic.constraint_set_checks import OTHER, _alphabet, _holds, accepts, make_spec  # noqa: E402
from src.symbolic.declare4py_verifier import Declare4Py  # noqa: E402


def _ast(tpl, cond):
    ast = {"article_id": "x", "template_name": tpl, "activation_activity": "A",
           "target_activity": None if tpl in UNARY_TEMPLATES else "B"}
    if cond:
        ast.update(activation_attr="case:flag", activation_op="==", activation_val=True)
    return ast


class TestSetCheckSemanticsMatchEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        df = exhaustive_log(["A", "B", "C"], 4)
        ids = sorted(df["case:concept:name"].unique())
        cls.flag = {cid: i % 2 == 0 for i, cid in enumerate(ids)}
        cases = pd.DataFrame({"case:concept:name": ids, "case:flag": [cls.flag[c] for c in ids]})
        cls.engine = Declare4Py(df, cases=cases)

    def _trace(self, symbols, ci, case_id):
        """Vết của hồ sơ trên bảng chữ của spec: activity ngoài spec → OTHER; bit điều kiện = case:flag của hồ sơ."""
        known = {s[0] for s in symbols}
        out = []
        for e in self.engine._trace_index[case_id]["events"]:
            act = e["concept:name"]
            if act not in known:
                out.append(OTHER)
                continue
            n_bits = sum(1 for (a, _c) in ci if a == act)
            out.append((act, tuple([self.flag[case_id]] * n_bits)))
        return tuple(out)

    def test_holds_and_dfa_agree_with_engine_case_by_case(self) -> None:
        for tpl in sorted(UNARY_TEMPLATES | BINARY_TEMPLATES):
            for cond in (False, True):
                spec = make_spec("x", _ast(tpl, cond))
                symbols, ci = _alphabet([spec])
                parsed = self.engine.parse_decl_lines([spec.decl])[0]
                for case_id, res, _ in self.engine.case_results(parsed):
                    trace = self._trace(symbols, ci, case_id)
                    engine_ok = res.state != "Violated"
                    with self.subTest(tpl=tpl, cond=cond, case=case_id):
                        self.assertEqual(_holds(spec, trace, ci), engine_ok)
                        self.assertEqual(accepts(spec, trace, ci), engine_ok)


class TestEventLevelConditionMatchesEngine(unittest.TestCase):
    """Điều kiện trên TỪNG event (VD điều kiện ngày): event chẵn trong hồ sơ có flag = True. Bắt các chỗ engine xét
    activity KHÔNG kèm điều kiện (VD Alternate Response ngắt ở A bất kỳ)."""

    @classmethod
    def setUpClass(cls) -> None:
        df = exhaustive_log(["A", "B", "C"], 4)
        df["flag"] = df.groupby("case:concept:name").cumcount() % 2 == 0
        ids = sorted(df["case:concept:name"].unique())
        # có bảng hồ sơ → engine giữ MỌI cột event (như cấu hình CAP); không có → chỉ cột BPIC2017 cố định
        cls.engine = Declare4Py(df, cases=pd.DataFrame({"case:concept:name": ids}))

    def test_holds_and_dfa_agree_with_engine(self) -> None:
        for tpl in sorted(UNARY_TEMPLATES | BINARY_TEMPLATES):
            ast = {"article_id": "x", "template_name": tpl, "activation_activity": "A",
                   "target_activity": None if tpl in UNARY_TEMPLATES else "B",
                   "activation_attr": "flag", "activation_op": "==", "activation_val": True}
            spec = make_spec("x", ast)
            symbols, ci = _alphabet([spec])
            known = {s[0] for s in symbols}
            parsed = self.engine.parse_decl_lines([spec.decl])[0]
            for case_id, res, events in self.engine.case_results(parsed):
                trace = tuple(OTHER if e["concept:name"] not in known else
                              (e["concept:name"], tuple([bool(e["flag"])] * sum(1 for (a, _c) in ci
                                                                              if a == e["concept:name"])))
                              for e in events)
                engine_ok = res.state != "Violated"
                with self.subTest(tpl=tpl, case=case_id):
                    self.assertEqual(_holds(spec, trace, ci), engine_ok)
                    self.assertEqual(accepts(spec, trace, ci), engine_ok)


if __name__ == "__main__":
    unittest.main()
