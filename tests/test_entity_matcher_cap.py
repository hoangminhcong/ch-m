"""
Generic Entity Matcher (Tầng 3.1, verbalizer_roundtrip.py) mở rộng cho bộ CAP:
  - đơn vị diện tích 'hectare(s)' / 'ha';
  - mốc ngày lịch ('15 May', '1 December') cho điều kiện 'date';
  - giá trị số trong extra_conditions cũng phải có trong văn bản luật.
Văn bản Directive 2008/48/EC (BPIC2017) phải cho đúng các thực thể như trước (không ai có đơn vị 'ha').
"""

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.symbolic.verbalizer_roundtrip import (  # noqa: E402
    extract_clause_dates,
    extract_clause_numeric_entities,
    verify_generic_numeric_entities,
)

CHUNKS_2017 = PROJECT_ROOT / "data" / "processed" / "directive_chunks.json"


def _ast(**kw):
    base = {"template_name": "Existence", "activation_activity": "x", "activation_attr": None,
            "activation_op": None, "activation_val": None, "extra_conditions": [], "time_max": None}
    return {**base, **kw}


class TestHectares(unittest.TestCase):
    def test_hectare_units_extracted(self) -> None:
        ents = extract_clause_numeric_entities("at least 1 hectare; holdings above 30 hectares or 0,3 ha")
        self.assertIn((1.0, "ha"), ents)
        self.assertIn((30.0, "ha"), ents)
        self.assertIn((0.3, "ha"), ents)

    def test_area_threshold_from_text_accepted(self) -> None:
        chunk = {"text": "The minimum eligible area shall be 1 hectare."}
        ok, _, _ = verify_generic_numeric_entities(_ast(activation_attr="case:area", activation_op=">=",
                                                        activation_val=1.0), chunk)
        self.assertTrue(ok)


class TestDates(unittest.TestCase):
    def test_extract_day_month_both_orders(self) -> None:
        dates = extract_clause_dates("not later than 15 May; from 1 December to 30 June; by June 1st")
        self.assertEqual(dates, {(5, 15), (12, 1), (6, 30), (6, 1)})

    def test_date_in_text_accepted(self) -> None:
        chunk = {"text": "The final dates shall not be later than 15 May each year."}
        ok, _, _ = verify_generic_numeric_entities(
            _ast(activation_attr="date", activation_op="<=", activation_val="year-05-15"), chunk)
        self.assertTrue(ok)

    def test_date_not_in_text_is_mismatch(self) -> None:
        chunk = {"text": "The final dates shall not be later than 15 May each year."}
        ok, verdict, diag = verify_generic_numeric_entities(
            _ast(activation_attr="date", activation_op="<=", activation_val="year-05-31"), chunk)
        self.assertFalse(ok)
        self.assertEqual(verdict, "THRESHOLD_MISMATCH")
        self.assertIn("15 May", diag)

    def test_date_without_any_date_in_text_is_baseless(self) -> None:
        ok, verdict, _ = verify_generic_numeric_entities(
            _ast(activation_attr="date", activation_op="<=", activation_val="year-05-15"),
            {"text": "Member States shall carry out administrative checks."})
        self.assertFalse(ok)
        self.assertEqual(verdict, "BASELESS")

    def test_date_in_extra_conditions_checked(self) -> None:
        chunk = {"text": "Payments shall be made within the period from 1 December to 30 June of the following year."}
        good = _ast(activation_attr="date", activation_op=">=", activation_val="year-12-01",
                    extra_conditions=[{"attr": "date", "op": "<=", "val": "year+1-06-30"}])
        bad = _ast(activation_attr="date", activation_op=">=", activation_val="year-12-01",
                   extra_conditions=[{"attr": "date", "op": "<=", "val": "year+1-07-31"}])
        self.assertTrue(verify_generic_numeric_entities(good, chunk)[0])
        self.assertFalse(verify_generic_numeric_entities(bad, chunk)[0])


class TestExtraNumericConditions(unittest.TestCase):
    def test_numeric_extra_condition_must_appear(self) -> None:
        chunk = {"text": "Young farmers with at least 1 hectare are eligible."}
        ok, verdict, _ = verify_generic_numeric_entities(
            _ast(activation_attr="case:young farmer", activation_op="==", activation_val=True,
                 extra_conditions=[{"attr": "case:area", "op": ">=", "val": 5}]), chunk)
        self.assertFalse(ok)
        self.assertEqual(verdict, "THRESHOLD_MISMATCH")

    def test_boolean_extra_condition_not_treated_as_number(self) -> None:
        ok, _, _ = verify_generic_numeric_entities(
            _ast(activation_attr="case:area", activation_op=">=", activation_val=1.0,
                 extra_conditions=[{"attr": "case:young farmer", "op": "==", "val": True}]),
            {"text": "at least 1 hectare"})
        self.assertTrue(ok)


from src.datasets import skip_unless_bpic2017  # noqa: E402  (bộ BPIC2017 đang tạm vô hiệu)


@skip_unless_bpic2017
@unittest.skipUnless(CHUNKS_2017.exists(), "cần data/processed/directive_chunks.json")
class TestDirectiveEntitiesUnchanged(unittest.TestCase):
    def test_no_directive_clause_gains_area_or_date_entities(self) -> None:
        chunks = json.loads(CHUNKS_2017.read_text(encoding="utf-8"))
        with_ha = [c["article_id"] for c in chunks if any(u == "ha" for _, u in extract_clause_numeric_entities(c["text"]))]
        self.assertEqual(with_ha, [])


if __name__ == "__main__":
    unittest.main()
