"""
Chỉ mục trace của Declare4Py (load_dataframe_log): cách nhanh (một lần to_dict rồi chia theo hồ sơ) phải cho KẾT QUẢ
Y HỆT cách cũ (to_dict từng nhóm groupby) — cùng thứ tự hồ sơ, thứ tự event, giá trị, kiểu; bỏ hồ sơ có khóa rỗng.
Đã so trên toàn log BPIC2018 (43 809 hồ sơ, 2 514 266 event: 0 khác biệt); test này giữ các ca biên.
"""

import math
import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.symbolic.data_conditions import CASE_KEY  # noqa: E402
from src.symbolic.declare4py_verifier import Declare4Py  # noqa: E402

# hồ sơ xen kẽ, thời gian lộn xộn, một event không có mã hồ sơ, giá trị rỗng ở cột event
EVENTS = pd.DataFrame([
    {"case:concept:name": "b", "concept:name": "x", "time:timestamp": "2017-01-03T00:00:00Z", "note": "n1"},
    {"case:concept:name": "a", "concept:name": "y", "time:timestamp": "2017-01-02T00:00:00Z", "note": None},
    {"case:concept:name": None, "concept:name": "z", "time:timestamp": "2017-01-01T00:00:00Z", "note": "lost"},
    {"case:concept:name": "b", "concept:name": "w", "time:timestamp": "2017-01-01T00:00:00Z", "note": "n2"},
    {"case:concept:name": "a", "concept:name": "v", "time:timestamp": "2017-01-02T00:00:00Z", "note": "tie"},
    {"case:concept:name": "c", "concept:name": "u", "time:timestamp": "2017-01-05T00:00:00Z", "note": "n3"},
])
CASES = pd.DataFrame([{"case:concept:name": "a", "case:year": 2017, "case:area": float("nan")},
                      {"case:concept:name": "b", "case:year": 2016, "case:area": 1.5}])


def _old_index(df: pd.DataFrame, cases: pd.DataFrame) -> dict:
    """Cách dựng chỉ mục TRƯỚC khi tối ưu (groupby + to_dict từng nhóm), trên df đã sắp của engine."""
    cols = [c for c in df.columns if not c.startswith("case:") and c != "_ts_sec"]
    case_records = {str(k): v for k, v in cases.set_index("case:concept:name").to_dict("index").items()}
    out = {}
    for case_id, group in df.groupby("case:concept:name", sort=False):
        records = group[cols + ["_ts_sec"]].to_dict("records")
        for r in records:
            r[CASE_KEY] = case_records.get(str(case_id), {})
        out[str(case_id)] = {"events": records, "activities": [r["concept:name"] for r in records]}
    return out


def _same(a: object, b: object) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return list(a) == list(b) and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return type(a) is type(b) and a == b


class TestFastIndexMatchesGroupby(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = Declare4Py(EVENTS, cases=CASES)
        self.old = _old_index(self.engine.log_df, CASES)

    def test_same_cases_in_same_order_without_empty_key(self) -> None:
        self.assertEqual(list(self.engine._trace_index), list(self.old))
        self.assertNotIn("None", self.engine._trace_index)
        self.assertNotIn("nan", self.engine._trace_index)

    def test_same_events_values_and_types(self) -> None:
        for cid, trace in self.old.items():
            new = self.engine._trace_index[cid]
            self.assertEqual(new["activities"], trace["activities"], cid)
            self.assertEqual(len(new["events"]), len(trace["events"]), cid)
            for ro, rn in zip(trace["events"], new["events"], strict=True):
                self.assertTrue(_same(ro, rn), (cid, ro, rn))

    def test_events_sorted_by_time_within_case_and_ties_keep_input_order(self) -> None:
        self.assertEqual(self.engine._trace_index["b"]["activities"], ["w", "x"])
        self.assertEqual(self.engine._trace_index["a"]["activities"], ["y", "v"])

    def test_case_attributes_shared_once_per_trace(self) -> None:
        events = self.engine._trace_index["a"]["events"]
        self.assertIs(events[0][CASE_KEY], events[1][CASE_KEY])
        self.assertEqual(self.engine._trace_index["c"]["events"][0][CASE_KEY], {})


if __name__ == "__main__":
    unittest.main()
