"""
v2 (docs/V2_DANG_KY_TRUOC.md mục 4, thành phần 1, 3, 4, 5, 11): hồ sơ tầng Tiến trình khai phá từ log —
năm hoạt động, activity "cùng bước" ở loại giấy tờ khác, tài liệu mỗi hồ sơ (docid), vai trò (org:resource),
thuộc tính event theo activity, bước trước/sau. Log tổng hợp nhỏ; không đọc dữ liệu thật.
"""

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.process_profile import build_process_profile, resource_kind  # noqa: E402

PARCEL15 = "Parcel document / Main / initialize"
GEO = "Geo parcel document / Declared / create"
GEO_INIT = "Geo parcel document / Main / initialize"
MAIL = "Payment application / Application / mail income"
PAY = "Payment application / Application / begin payment"


def _ev(case, name, day, resource="a1b2c3", docid="d", note="none"):
    return {"case:concept:name": case, "concept:name": name,
            "time:timestamp": pd.Timestamp(f"2016-01-{day:02d}", tz="UTC"),
            "org:resource": resource, "docid": docid, "note": note, "success": True}


EVENTS = pd.DataFrame([
    _ev("c15", MAIL, 1, "Processing automaton", "p1"), _ev("c15", PARCEL15, 2, docid="g1"),
    _ev("c15", PAY, 3, docid="p1"),
    _ev("c16", MAIL, 1, "Processing automaton", "p2"), _ev("c16", GEO, 2, docid="g2"),
    _ev("c16", GEO_INIT, 3, docid="g3"), _ev("c16", PAY, 4, "DP-Z", "p2"),
    _ev("c17", MAIL, 1, "Processing automaton", "p3"), _ev("c17", GEO, 2, docid="g4"),
    _ev("c17", PAY, 3, docid="p3"),
])
CASES = pd.DataFrame({"case:concept:name": ["c15", "c16", "c17"], "case:year": [2015, 2016, 2017]})


class TestResourceKind(unittest.TestCase):
    def test_kinds(self) -> None:
        for name, kind in (("Document processing automaton", "automated"),
                           ("Reference alignment processor", "automated"), ("scheduler", "automated"),
                           ("Remote inspection export", "automated"), ("727350", "staff"), ("97d224", "staff"),
                           ("DP-Z", "unknown"), ("0;n/a", "unknown"), (None, "unknown")):
            with self.subTest(name=name):
                self.assertEqual(resource_kind(name), kind)


class TestProcessProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.p = build_process_profile(EVENTS, CASES)

    def test_years_per_activity(self) -> None:
        acts = self.p["activities"]
        self.assertEqual(self.p["years"], [2015, 2016, 2017])
        self.assertEqual(acts[PARCEL15]["years"], [2015])
        self.assertEqual(acts[GEO]["years"], [2016, 2017])
        self.assertEqual(acts[MAIL]["years"], [2015, 2016, 2017])

    def test_parts_and_case_ratio(self) -> None:
        a = self.p["activities"][GEO]
        self.assertEqual((a["doctype"], a["subprocess"], a["action"]), ("Geo parcel document", "Declared", "create"))
        self.assertEqual((a["case_count"], a["case_ratio"]), (2, round(2 / 3, 4)))

    def test_same_step_siblings_other_doctype(self) -> None:
        """Cùng tiến trình con + hành động, khác loại giấy tờ (VD 'Main / initialize' ở Parcel và Geo parcel)."""
        self.assertEqual(self.p["activities"][PARCEL15]["same_step"], [GEO_INIT])
        self.assertEqual(self.p["activities"][GEO_INIT]["same_step"], [PARCEL15])
        self.assertEqual(self.p["activities"][MAIL]["same_step"], [])

    def test_roles(self) -> None:
        self.assertEqual(self.p["activities"][MAIL]["roles"], {"automated": 1.0, "staff": 0.0, "unknown": 0.0})
        self.assertEqual(self.p["activities"][PAY]["roles"]["unknown"], round(1 / 3, 4))

    def test_neighbours(self) -> None:
        a = self.p["activities"][MAIL]
        self.assertEqual(a["predecessors"], [])
        self.assertEqual(a["successors"][0], {"activity": GEO, "count": 2})

    def test_documents_per_case(self) -> None:
        d = self.p["documents"]["Geo parcel document"]
        self.assertEqual(d["cases"], 2)
        self.assertEqual((d["per_case_median"], d["per_case_max"]), (1.5, 2))
        self.assertEqual(self.p["documents"]["Payment application"]["per_case_max"], 1)

    def test_event_attributes_per_activity(self) -> None:
        self.assertIn("note", self.p["activities"][MAIL]["event_attributes"])
        self.assertNotIn("docid", self.p["activities"][MAIL]["event_attributes"])

    def test_doctype_years_and_replacements(self) -> None:
        """Hai loại giấy tờ có năm không giao nhau và gộp lại phủ đủ các năm của log = thay thế nhau theo năm."""
        self.assertEqual(self.p["doctype_years"]["Parcel document"], [2015])
        self.assertEqual(self.p["doctype_years"]["Geo parcel document"], [2016, 2017])
        self.assertEqual(self.p["doctype_replacements"],
                         {"Geo parcel document": ["Parcel document"], "Parcel document": ["Geo parcel document"]})

    def test_same_timestamp_keeps_log_order(self) -> None:
        """Rà soát 2026-11-18 H1: event cùng thời điểm giữ THỨ TỰ CỦA LOG (như process_graph_builder), không xếp
        theo tên activity — trước đây 'initialize → begin editing' bị đảo thành 'begin editing → initialize'."""
        t = pd.Timestamp("2016-01-01", tz="UTC")
        ev = pd.DataFrame([{"case:concept:name": "c", "concept:name": n, "time:timestamp": t}
                           for n in ("Z / M / initialize", "Z / M / begin editing", "Z / M / finish editing")])
        p = build_process_profile(ev, pd.DataFrame({"case:concept:name": ["c"], "case:year": [2016]}))
        self.assertEqual(p["activities"]["Z / M / initialize"]["successors"][0]["activity"], "Z / M / begin editing")
        self.assertEqual(p["activities"]["Z / M / begin editing"]["successors"][0]["activity"],
                         "Z / M / finish editing")

    def test_deterministic_for_same_input(self) -> None:
        self.assertEqual(build_process_profile(EVENTS, CASES), self.p)


if __name__ == "__main__":
    unittest.main()
