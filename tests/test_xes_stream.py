"""
Test cho src/preprocessing/xes_stream.py: chuyển XES rất lớn (BPIC2018, 1,9 GB) sang parquet bằng cách
đọc tuần tự từng hồ sơ, tách bảng event và bảng hồ sơ.
"""

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.preprocessing.xes_stream import CASE_COL, convert_xes  # noqa: E402

XES = """<?xml version="1.0" encoding="UTF-8" ?>
<log xes.version="1.0">
  <global scope="trace">
    <string key="concept:name" value="none"/>
    <boolean key="young farmer" value="false"/>
    <float key="area" value="0.0"/>
    <int key="number_parcels" value="0"/>
    <string key="year" value="none"/>
  </global>
  <global scope="event">
    <string key="concept:name" value="none"/>
    <string key="doctype" value="none"/>
    <date key="time:timestamp" value="1970-01-01T01:00:00.000+01:00"/>
    <boolean key="success" value="false"/>
  </global>
  <trace>
    <string key="concept:name" value="C1"/>
    <boolean key="young farmer" value="true"/>
    <float key="area" value="12.5"/>
    <int key="number_parcels" value="3"/>
    <string key="year" value="2015"/>
    <float key="amount_applied1" value="5.0"/>
    <event>
      <string key="concept:name" value="mail income"/>
      <string key="doctype" value="Payment application"/>
      <date key="time:timestamp" value="2015-05-08T00:00:00.000+02:00"/>
      <boolean key="success" value="true"/>
    </event>
    <event>
      <string key="concept:name" value="finish payment"/>
      <string key="doctype" value="Payment application"/>
      <date key="time:timestamp" value="2015-12-20T10:00:00.000+01:00"/>
      <boolean key="success" value="false"/>
    </event>
  </trace>
  <trace>
    <string key="concept:name" value="C2"/>
    <boolean key="young farmer" value="false"/>
    <float key="area" value="3.0"/>
    <int key="number_parcels" value="1"/>
    <string key="year" value="2016"/>
    <event>
      <string key="concept:name" value="mail income"/>
      <date key="time:timestamp" value="2016-05-10T00:00:00.000+02:00"/>
      <boolean key="success" value="true"/>
    </event>
  </trace>
</log>
"""


class TestConvertXes(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.xes = d / "log.xes"
        self.xes.write_text(XES, encoding="utf-8")
        self.events_out, self.cases_out = d / "events.parquet", d / "cases.parquet"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, chunk=1000):
        stats = convert_xes(self.xes, self.events_out, self.cases_out, chunk_traces=chunk)
        return stats, pd.read_parquet(self.events_out), pd.read_parquet(self.cases_out)

    def test_counts(self) -> None:
        stats, ev, cs = self._run()
        self.assertEqual(stats, {"cases": 2, "events": 3})
        self.assertEqual(len(ev), 3)
        self.assertEqual(len(cs), 2)

    def test_events_carry_case_id_and_pm4py_columns(self) -> None:
        _, ev, _ = self._run()
        self.assertEqual(list(ev[CASE_COL]), ["C1", "C1", "C2"])
        self.assertEqual(list(ev["concept:name"]), ["mail income", "finish payment", "mail income"])

    def test_timestamps_are_utc(self) -> None:
        _, ev, _ = self._run()
        self.assertEqual(str(ev["time:timestamp"].dt.tz), "UTC")
        self.assertEqual(ev["time:timestamp"].iloc[0], pd.Timestamp("2015-05-07T22:00:00Z"))

    def test_typed_case_attributes(self) -> None:
        _, _, cs = self._run()
        c1 = cs.set_index(CASE_COL).loc["C1"]
        self.assertIs(bool(c1["case:young farmer"]), True)
        self.assertEqual(c1["case:area"], 12.5)
        self.assertEqual(c1["case:number_parcels"], 3)
        self.assertEqual(c1["case:year"], "2015")

    def test_missing_event_attribute_is_null(self) -> None:
        _, ev, _ = self._run()
        self.assertTrue(pd.isna(ev["doctype"].iloc[2]))

    def test_undeclared_case_attribute_is_kept_with_its_type(self) -> None:
        """BPIC2018 có amount_applied1..3 không khai báo trong <global>: không được bỏ."""
        _, _, cs = self._run()
        cs = cs.set_index(CASE_COL)
        self.assertEqual(cs.loc["C1", "case:amount_applied1"], 5.0)
        self.assertTrue(pd.isna(cs.loc["C2", "case:amount_applied1"]))
        self.assertEqual(str(cs["case:amount_applied1"].dtype), "float64")

    def test_chunking_does_not_change_result(self) -> None:
        _, ev1, cs1 = self._run(chunk=1)
        _, ev2, cs2 = self._run(chunk=1000)
        pd.testing.assert_frame_equal(ev1, ev2)
        pd.testing.assert_frame_equal(cs1, cs2)


if __name__ == "__main__":
    unittest.main()
