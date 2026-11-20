"""
Engine Declare4Py với bảng hồ sơ riêng (đề xuất 1) + điều kiện ngày theo múi giờ (đề xuất 3).

BPIC2018 tách event (2,5 triệu) và hồ sơ (43 809 × 60 thuộc tính). Engine nhận `cases=` và lưu thuộc tính
hồ sơ MỘT lần mỗi trace (khóa '_case' dùng chung), không chép vào từng event.
Khi không truyền `cases`, hành vi giữ nguyên như BPIC2017 (đã có test ở test_declare_engine_semantics.py).
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.symbolic.declare4py_verifier import Declare4Py  # noqa: E402

EVENTS = pd.DataFrame([
    # c1: nộp 23:59 ngày 15/5 giờ Đức -> kịp hạn
    {"case:concept:name": "c1", "concept:name": "mail income", "time:timestamp": "2016-05-15T21:59:00Z", "success": True},
    {"case:concept:name": "c1", "concept:name": "begin payment", "time:timestamp": "2016-12-20T09:00:00Z", "success": True},
    # c2: nộp 00:30 ngày 16/5 giờ Đức (22:30 UTC ngày 15/5) -> trễ hạn
    {"case:concept:name": "c2", "concept:name": "mail income", "time:timestamp": "2016-05-15T22:30:00Z", "success": True},
    # c3: không có bản ghi trong bảng hồ sơ -> không biết năm -> điều kiện ngày không thỏa
    {"case:concept:name": "c3", "concept:name": "mail income", "time:timestamp": "2016-04-01T10:00:00Z", "success": False},
])
CASES = pd.DataFrame([
    {"case:concept:name": "c1", "case:year": "2016", "case:young farmer": True, "case:area": 12.0},
    {"case:concept:name": "c2", "case:year": "2016", "case:young farmer": False, "case:area": 40.0},
])


def _states(engine: Declare4Py, decl_line: str) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".decl", delete=False, encoding="utf-8") as f:
        f.write(decl_line + "\n")
        path = f.name
    try:
        engine.parse_decl_model(path)
        res = engine.conformance_checking(consider_vacuity=True)
    finally:
        os.unlink(path)
    return {cid: next(iter(r.values())).state for (_, cid), r in res.items()}


class TestCaseTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = Declare4Py(EVENTS, cases=CASES, timezone="Europe/Berlin")

    def test_case_attributes_stored_once_per_trace(self) -> None:
        events = self.engine._trace_index["c1"]["events"]
        self.assertIs(events[0]["_case"], events[1]["_case"])
        self.assertNotIn("case:area", events[0])
        self.assertEqual(events[0]["_case"]["case:area"], 12.0)

    def test_event_columns_beyond_bpic2017_list_kept(self) -> None:
        self.assertIn("success", self.engine._trace_index["c1"]["events"][0])

    def test_case_without_record_has_empty_case(self) -> None:
        self.assertEqual(self.engine._trace_index["c3"]["events"][0]["_case"], {})

    def test_case_attribute_condition_with_space(self) -> None:
        states = _states(self.engine, "Response[mail income, begin payment] | A.case:young farmer == True | |")
        self.assertEqual(states, {"c1": "Satisfied", "c2": "Vacuously Satisfied", "c3": "Vacuously Satisfied"})

    def test_deadline_in_local_time(self) -> None:
        states = _states(self.engine, "Existence[mail income] | A.date <= year-05-15 | |")
        self.assertEqual(states, {"c1": "Satisfied", "c2": "Violated", "c3": "Violated"})

    def test_conjunction_of_case_and_date(self) -> None:
        states = _states(self.engine, "Absence[mail income] | A.case:area > 20 and A.date > year-05-15 | |")
        self.assertEqual(states["c2"], "Violated")
        self.assertEqual(states["c1"], "Satisfied")


class TestTimezoneDefaultUTC(unittest.TestCase):
    def test_same_deadline_in_utc_accepts_c2(self) -> None:
        engine = Declare4Py(EVENTS, cases=CASES)
        states = _states(engine, "Existence[mail income] | A.date <= year-05-15 | |")
        self.assertEqual(states["c2"], "Satisfied")


class TestWithoutCaseTableUnchanged(unittest.TestCase):
    def test_no_case_key_and_bpic2017_columns_only(self) -> None:
        engine = Declare4Py(EVENTS)
        ev = engine._trace_index["c1"]["events"][0]
        self.assertNotIn("_case", ev)
        self.assertNotIn("success", ev)  # danh sách cột BPIC2017 giữ nguyên khi không có bảng hồ sơ


if __name__ == "__main__":
    unittest.main()
