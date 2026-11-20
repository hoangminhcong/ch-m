"""
Tập Đức (docs/V2_DANG_KY_TRUOC.md mục 5.1: giữ nguyên tiếng Đức): Entity Matcher nhận số / ngày tiếng Đức —
'15. Mai', 'drei Tage', '14 aufeinanderfolgende Tage', 'einem Monat', '0,3 Hektar', '1.000 Euro', '5 Prozent'.
Văn bản tiếng Anh cho kết quả như cũ.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.symbolic.verbalizer_roundtrip import extract_clause_dates, extract_clause_numeric_entities  # noqa: E402


def _ents(text):
    return set(extract_clause_numeric_entities(text))


class TestGermanDates(unittest.TestCase):
    def test_day_dot_month(self) -> None:
        self.assertEqual(extract_clause_dates("bis zum 15. Mai des Antragsjahres"), {(5, 15)})
        self.assertEqual(extract_clause_dates("im Zeitraum 1. Juni bis 15. Juli"), {(6, 1), (7, 15)})
        self.assertEqual(extract_clause_dates("bis zum 31. März"), {(3, 31)})

    def test_english_unchanged(self) -> None:
        self.assertEqual(extract_clause_dates("not later than 15 May"), {(5, 15)})
        self.assertEqual(extract_clause_dates("Member States may decide"), set())


class TestGermanNumbers(unittest.TestCase):
    def test_number_words_with_units(self) -> None:
        self.assertIn((3.0, "days"), _ents("spätestens drei Tage vorher schriftlich anzuzeigen"))
        self.assertIn((2.0, "weeks"), _ents("innerhalb von zwei Wochen"))
        self.assertIn((1.0, "months"), _ents("binnen einem Monat nach Zugang"))
        self.assertIn((21.0, "days"), _ents("an nicht mehr als einundzwanzig Tagen"))

    def test_digits_with_adjective_and_units(self) -> None:
        self.assertIn((14.0, "days"), _ents("nicht länger als 14 aufeinanderfolgende Tage"))
        self.assertIn((10.0, "days"), _ents("innerhalb von 10 Kalendertagen"))
        self.assertIn((0.3, "ha"), _ents("mindestens 0,3 Hektar"))
        self.assertIn((5.0, "%"), _ents("mindestens 5 Prozent"))

    def test_german_thousands_separator(self) -> None:
        ents = _ents("Beträge bis 1.250 Euro")
        self.assertIn((1250.0, "EUR"), ents)
        self.assertNotIn((1.25, "EUR"), ents)

    def test_english_decimal_with_three_digits_not_read_as_thousands(self) -> None:
        """Rà soát MEDIUM-1: tiếng Anh dùng dấu chấm thập phân — '0.100 ha', '1.500 hectares' giữ như v1."""
        self.assertIn((0.1, "ha"), _ents("at least 0.100 ha"))
        self.assertIn((1.5, "ha"), _ents("of 1.500 hectares"))
        self.assertNotIn((1500.0, "ha"), _ents("of 1.500 hectares"))

    def test_english_unchanged(self) -> None:
        self.assertEqual(_ents("within two working days and EUR 200"), {(2.0, "days"), (200.0, "EUR")})
        self.assertIn((12.0, "months"), _ents("within 12 months"))
        # Hồi quy lỗi '%' của v1 (sửa 2026-11-18 → v1.1): '\b' sau '%' không bao giờ khớp nên '5 %' bị bỏ sót.
        self.assertIn((5.0, "%"), _ents("5 % of the beneficiaries"))
        self.assertIn((0.5, "%"), _ents("reduced by 0,5 %."))
        self.assertIn((3.0, "%"), _ents("at least 3% of"))
        self.assertNotIn((5.0, "days"), _ents("5 dayside"))  # đơn vị chữ vẫn cần ranh giới như trước


if __name__ == "__main__":
    unittest.main()
