"""
Tập positive mới (docs/V2_DANG_KY_TRUOC.md mục 5.1): dựng lại văn bản InVeKoSV / DirektZahlDurchfV có hiệu lực tại
một ngày, từ các trang so sánh phiên bản của buzer.de (ô 'hunc' = không đổi, 'halt' = bản cũ, 'hneu' = bản mới).
HTML tổng hợp nhỏ theo đúng cấu trúc trang thật; không gọi mạng.
"""

import sys
import unittest
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.preprocessing.de_law_versions import (  # noqa: E402
    parse_version_page,
    split_absaetze,
    text_at,
)


def _page(effective: str, blocks: str) -> str:
    return (f'<html><body><table class="tdiff"><tr><th>X a.F. (alte Fassung) in der vor dem {effective} geltenden '
            f'Fassung</th><th>X n.F. (neue Fassung) in der am {effective} geltenden Fassung</th></tr>'
            f'{blocks}</table></body></html>')


def _block(sec: str, rows: str, first: bool = False) -> str:
    prev = "(keine fr&uuml;here Fassung vorhanden)" if first else f"&larr; fr&uuml;here Fassung von &sect; {sec}"
    return (f'<tr class="noprint"><td>{prev}</td><td>n&auml;chste Fassung von &sect; {sec} &rarr;</td></tr>'
            f'<tr class="noprint"><td colspan="2"><a>aktuelle Fassung &sect; {sec} zeigen</a></td></tr>{rows}')


def _same(text: str) -> str:
    return ('<tr><td colspan="2"><div class="hunc"><span class="hdiff">(Textabschnitt unver&auml;ndert)</span> '
            f'{text}</div></td></tr>')


def _diff(old: str, new: str) -> str:
    return (f'<tr><td class="halt"><span class="hdiff">(Text alte Fassung)</span> <a class="noprint">x</a>{old}</td>'
            f'<td class="hneu"><span class="hdiff">(Text neue Fassung)</span>{new}</td></tr>')


P2016 = _page("17.03.2016", _block("7", _same("&sect; 7 Form und Frist<br />(1) Der Antrag ist bis zum")
                                     + _diff("15. Mai", "15. Mai <span class='happ'>des Antragsjahres</span>")
                                     + _same("zu stellen.<br />(2) Ein Satz.")))
P2017 = _page("05.05.2017", _block("7", _same("&sect; 7 Form und Frist<br />(1) Der Antrag ist bis zum")
                                     + _diff("15. Mai des Antragsjahres", "31. Mai des Antragsjahres")
                                     + _same("zu stellen.<br />(2) Ein Satz."))
              + _block("10a", _diff("", "&sect; 10a Neu<br />Text neu."), first=True)
              + _block("8", _same("&sect; 8 Angaben<br />(1) <span class='satz' title='Satz 1'>1</span> Erster."
                                  " <span class='satz' title='Satz 2'>2</span> Zweiter.")
                       + _diff("Alt.", "Neu."), first=True))


class TestParseVersionPage(unittest.TestCase):
    def test_effective_date_and_sections(self) -> None:
        v = parse_version_page(P2016)
        self.assertEqual(v["effective"], date(2016, 3, 17))
        self.assertEqual(list(v["sections"]), ["7"])

    def test_old_and_new_text_reconstructed(self) -> None:
        s = parse_version_page(P2016)["sections"]["7"]
        self.assertIn("bis zum 15. Mai zu stellen.", s["old"])
        self.assertIn("bis zum 15. Mai des Antragsjahres zu stellen.", s["new"])
        self.assertNotIn("Textabschnitt", s["new"])
        self.assertNotIn("Text neue Fassung", s["new"])

    def test_new_section_has_no_old_text(self) -> None:
        s = parse_version_page(P2017)["sections"]["10a"]
        self.assertEqual(s["old"], "")
        self.assertIn("Text neu.", s["new"])

    def test_first_change_keeps_old_text_and_sentence_numbers_dropped(self) -> None:
        """'(keine frühere Fassung vorhanden)' = lần đổi đầu tiên, KHÔNG phải § mới; số câu của buzer bị bỏ."""
        s = parse_version_page(P2017)["sections"]["8"]
        self.assertIn("Alt.", s["old"])
        self.assertIn("(1) Erster. Zweiter.", s["new"])


SINGLE = ('<table class="tdiff"><tr><th>&sect; 12a X a.F. (alte Fassung) in der vor dem 28.10.2016 geltenden Fassung'
          '</th><th>&sect; 12a X n.F. (neue Fassung) in der am 28.10.2016 geltenden Fassung</th></tr>'
          '<tr class="noprint"><td>&larr; vorherige &Auml;nderung durch Artikel 1</td><td></td></tr>'
          + _diff("", "&sect; 12a Anpassung<br />Der Wert wird angepasst.") + '</table>')


class TestSingleSectionPage(unittest.TestCase):
    def test_section_label_taken_from_column_header(self) -> None:
        """Trang sửa một § (al…-n.htm): nhãn § nằm ở tiêu đề cột, dòng điều hướng chỉ ghi 'vorherige Änderung'."""
        v = parse_version_page(SINGLE)
        self.assertEqual((v["effective"], list(v["sections"])), (date(2016, 10, 28), ["12a"]))
        self.assertEqual(v["sections"]["12a"]["old"], "")
        self.assertIsNone(text_at("12a", date(2016, 5, 15), [v], {}))
        self.assertIn("angepasst", text_at("12a", date(2017, 5, 15), [v], {}))


class TestTextAt(unittest.TestCase):
    VERSIONS = [parse_version_page(P2016), parse_version_page(P2017)]
    CURRENT = {"7": "§ 7 aktuell", "1": "§ 1 nie geändert"}

    def test_latest_change_on_or_before_date(self) -> None:
        self.assertIn("15. Mai des Antragsjahres", text_at("7", date(2016, 5, 15), self.VERSIONS, self.CURRENT))
        self.assertIn("31. Mai", text_at("7", date(2017, 5, 15), self.VERSIONS, self.CURRENT))

    def test_before_first_change_uses_old_text(self) -> None:
        t = text_at("7", date(2015, 5, 15), self.VERSIONS, self.CURRENT)
        self.assertIn("bis zum 15. Mai zu stellen.", t)

    def test_never_changed_uses_current_and_not_yet_existing_is_none(self) -> None:
        self.assertEqual(text_at("1", date(2015, 5, 15), self.VERSIONS, self.CURRENT), "§ 1 nie geändert")
        self.assertIsNone(text_at("10a", date(2016, 5, 15), self.VERSIONS, self.CURRENT))


class TestSectionTextValidation(unittest.TestCase):
    """Rà soát 2026-11-18 H5: đánh số lại (§ 35 cũ → § 36) làm 'text_at' trả văn bản của § KHÁC, kèm cả Anlage."""

    def test_heading_must_match_section(self) -> None:
        from src.preprocessing.de_law_versions import section_text_or_none
        self.assertIsNone(section_text_or_none("36", "§ 35 Inkrafttreten\nDiese Verordnung tritt … in Kraft."))
        self.assertEqual(section_text_or_none("7", "§ 7 Form\n(1) Text."), "§ 7 Form\n(1) Text.")
        self.assertIsNone(section_text_or_none("7", None))

    def test_annex_blocks_cut(self) -> None:
        from src.preprocessing.de_law_versions import section_text_or_none
        t = section_text_or_none("35", "§ 35 Inkrafttreten\nDiese Verordnung tritt in Kraft.\nAnlage 3 (zu § 32)\nTabelle")
        self.assertEqual(t, "§ 35 Inkrafttreten\nDiese Verordnung tritt in Kraft.")


class TestSplitAbsaetze(unittest.TestCase):
    def test_numbered_paragraphs(self) -> None:
        parts = split_absaetze("§ 7 Form und Frist\n(1) Der Antrag ist bis zum 15. Mai zu stellen.\n(2) Ein Satz.")
        self.assertEqual([p["absatz"] for p in parts], ["1", "2"])
        self.assertEqual(parts[0]["title"], "Form und Frist")
        self.assertTrue(parts[1]["text"].startswith("(2) Ein Satz"))

    def test_section_without_paragraphs_is_one_chunk(self) -> None:
        parts = split_absaetze("§ 17 Betriebsnummer\nDie Landesstelle teilt eine Nummer zu.")
        self.assertEqual([(p["absatz"], p["text"]) for p in parts], [(None, "Die Landesstelle teilt eine Nummer zu.")])


if __name__ == "__main__":
    unittest.main()
