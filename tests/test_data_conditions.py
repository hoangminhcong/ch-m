"""
Test cho src/symbolic/data_conditions.py — biên dịch điều kiện dữ liệu của dòng .decl (Tầng 3).

Mở rộng cho bộ CAP / BPIC2018 (đề xuất 2–3), giữ nguyên hành vi cho các điều kiện BPIC2017 hiện có:
  - tên thuộc tính có dấu cách / gạch nối ('case:young farmer', 'case:program-id');
  - nối nhiều điều kiện bằng 'and';
  - điều kiện ngày lịch theo giờ địa phương: 'A.date <= year-05-15' (year = case:year của hồ sơ).
"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.symbolic.data_conditions import compile_condition, split_conjunction  # noqa: E402


def _ts(iso_utc: str) -> float:
    return datetime.fromisoformat(iso_utc).replace(tzinfo=timezone.utc).timestamp()


class TestBPIC2017ConditionsUnchanged(unittest.TestCase):
    """Năm dạng điều kiện đang có trong benchmark / verified_constraints phải cho kết quả như cũ."""

    def test_numeric_and_boolean(self) -> None:
        ev = {"OfferedAmount": 5000.0, "CreditScore": 0.0, "Accepted": False, "case:RequestedAmount": 150.0}
        self.assertTrue(compile_condition("A.OfferedAmount <= 10000.0")(ev))
        self.assertFalse(compile_condition("A.OfferedAmount >= 200.0")({"OfferedAmount": 100.0}))
        self.assertTrue(compile_condition("A.CreditScore >= 0.0")(ev))
        self.assertTrue(compile_condition("A.Accepted == False")(ev))
        self.assertFalse(compile_condition("A.case:RequestedAmount >= 200.0")(ev))

    def test_short_name_falls_back_to_case_prefix(self) -> None:
        self.assertTrue(compile_condition("A.RequestedAmount >= 200")({"case:RequestedAmount": 500.0}))

    def test_missing_or_nan_value_is_false(self) -> None:
        self.assertFalse(compile_condition("A.OfferedAmount >= 200")({}))
        self.assertFalse(compile_condition("A.OfferedAmount >= 200")({"OfferedAmount": float("nan")}))

    def test_empty_condition_always_true(self) -> None:
        self.assertTrue(compile_condition("")({}))

    def test_string_equality_quoted(self) -> None:
        cond = compile_condition('A.case:LoanGoal == "Car"')
        self.assertTrue(cond({"case:LoanGoal": "Car"}))
        self.assertFalse(cond({"case:LoanGoal": "Home"}))


class TestNamesWithSpacesAndConjunction(unittest.TestCase):
    def test_attribute_with_space(self) -> None:
        cond = compile_condition("A.case:young farmer == True")
        self.assertTrue(cond({"case:young farmer": True}))
        self.assertFalse(cond({"case:young farmer": False}))

    def test_attribute_with_hyphen(self) -> None:
        self.assertTrue(compile_condition('A.case:program-id == "215"')({"case:program-id": "215"}))

    def test_and_conjunction(self) -> None:
        cond = compile_condition("A.case:young farmer == True and A.case:area > 10")
        self.assertTrue(cond({"case:young farmer": True, "case:area": 12.5}))
        self.assertFalse(cond({"case:young farmer": True, "case:area": 3.0}))
        self.assertFalse(cond({"case:young farmer": False, "case:area": 12.5}))

    def test_and_inside_quotes_is_not_split(self) -> None:
        self.assertEqual(split_conjunction('A.x == "a and b" and A.y > 1'), ['A.x == "a and b"', "A.y > 1"])

    def test_case_attributes_read_from_shared_case_record(self) -> None:
        """Thuộc tính hồ sơ lưu một lần mỗi trace (khóa '_case'), không chép vào từng event."""
        ev = {"concept:name": "x", "_case": {"case:area": 20.0, "case:young farmer": True}}
        self.assertTrue(compile_condition("A.case:area > 10 and A.young farmer == True")(ev))


class TestCalendarDateConditions(unittest.TestCase):
    def setUp(self) -> None:
        self.deadline = compile_condition("A.date <= year-05-15", timezone="Europe/Berlin")

    def _ev(self, iso_utc: str, year: object = "2016") -> dict:
        return {"_ts_sec": _ts(iso_utc), "_case": {"case:year": year}}

    def test_before_deadline_local_time(self) -> None:
        self.assertTrue(self.deadline(self._ev("2016-05-15T21:59:00")))  # 23:59 giờ Đức (CEST, +2)

    def test_boundary_0030_on_16_may_berlin_violates(self) -> None:
        """00:30 ngày 16/5 giờ Đức = 22:30 ngày 15/5 UTC: theo UTC thì 'kịp hạn', theo giờ Đức thì trễ."""
        ev = self._ev("2016-05-15T22:30:00")
        self.assertFalse(self.deadline(ev))
        self.assertTrue(compile_condition("A.date <= year-05-15", timezone="UTC")(ev))

    def test_year_offset_window(self) -> None:
        window = compile_condition("A.date >= year-12-01 and A.date <= year+1-06-30", timezone="Europe/Berlin")
        self.assertTrue(window(self._ev("2017-03-10T10:00:00")))
        self.assertTrue(window(self._ev("2016-11-30T23:30:00")))  # 00:30 ngày 01/12 giờ Đức (CET, +1)
        self.assertFalse(window(self._ev("2016-11-30T22:30:00")))  # 23:30 ngày 30/11 giờ Đức
        self.assertFalse(window(self._ev("2017-07-01T08:00:00")))

    def test_year_from_integer_attribute(self) -> None:
        self.assertTrue(self.deadline(self._ev("2016-05-01T10:00:00", year=2016)))

    def test_missing_or_bad_year_is_not_satisfied(self) -> None:
        self.assertFalse(self.deadline({"_ts_sec": _ts("2016-05-01T10:00:00"), "_case": {}}))
        self.assertFalse(self.deadline(self._ev("2016-05-01T10:00:00", year="unknown")))

    def test_absolute_date(self) -> None:
        cond = compile_condition("A.date < 2016-01-01", timezone="Europe/Berlin")
        self.assertTrue(cond(self._ev("2015-12-31T22:00:00")))  # 23:00 ngày 31/12 giờ Đức
        self.assertFalse(cond(self._ev("2015-12-31T23:30:00")))  # 00:30 ngày 01/01

    def test_custom_year_attribute(self) -> None:
        cond = compile_condition("A.date <= year-05-15", timezone="UTC", year_attr="case:campaign")
        self.assertTrue(cond({"_ts_sec": _ts("2016-05-01T10:00:00"), "case:campaign": "2016"}))

    def test_missing_timestamp_is_not_satisfied(self) -> None:
        self.assertFalse(self.deadline({"_case": {"case:year": "2016"}}))


class TestNumericStringEquality(unittest.TestCase):
    """case:year của BPIC2018 là chuỗi '2016'; dòng .decl ghi 'A.case:year == 2016' (không nháy) → so như số."""

    def test_year_string_matches_unquoted_number(self) -> None:
        ev = {"_case": {"case:year": "2016"}}
        self.assertTrue(compile_condition("A.case:year == 2016")(ev))
        self.assertFalse(compile_condition("A.case:year == 2018")(ev))
        self.assertTrue(compile_condition("A.case:year != 2018")(ev))
        self.assertTrue(compile_condition('A.case:year == "2016"')(ev))

    def test_non_numeric_string_still_unequal(self) -> None:
        ev = {"case:LoanGoal": "Car"}
        self.assertFalse(compile_condition("A.case:LoanGoal == 5")(ev))
        self.assertTrue(compile_condition("A.case:LoanGoal != 5")(ev))


if __name__ == "__main__":
    unittest.main()
