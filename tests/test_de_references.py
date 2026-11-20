"""
Dẫn chiếu trong văn bản Đức (InVeKoSV / DirektZahlDurchfV) → node đồ thị: tới 4 Quy định CAP (R1306, R1307, R640,
R809 — trong phạm vi) và giữa các § của hai văn bản Đức. Quy định EU khác / luật Đức khác → ngoài phạm vi.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.preprocessing.de_references import extract_de_references  # noqa: E402


def _targets(text, law="InVeKoSV"):
    return [(r["target"], r["in_scope"]) for r in extract_de_references(text, law)]


class TestEuReferences(unittest.TestCase):
    def test_article_with_paragraph_and_regulation(self) -> None:
        t = "Der Antrag ist nach Artikel 11 der Delegierten Verordnung (EU) Nr. 640/2014 zu stellen."
        self.assertEqual(_targets(t), [("R640:Art11", True)])

    def test_genitive_absatz_buchstabe(self) -> None:
        t = "Flächen im Sinne des Artikels 32 Absatz 2 Buchstabe b der Verordnung (EU) Nr. 1307/2013 des Betriebes"
        self.assertEqual(_targets(t), [("R1307:Art32(2)", True)])

    def test_list_of_articles(self) -> None:
        t = "nach den Artikeln 11 und 12 der Durchführungsverordnung (EU) Nr. 809/2014"
        self.assertEqual(_targets(t), [("R809:Art11", True), ("R809:Art12", True)])

    def test_other_eu_regulation_out_of_scope(self) -> None:
        self.assertEqual(_targets("Artikel 2 Absatz 10 der Verordnung (EU) Nr. 1303/2013"),
                         [("EU-1303/2013:Art2(10)", False)])


class TestParagraphLists(unittest.TestCase):
    """Rà soát 2026-11-18 HIGH-2: 'Absatz 1 und 2' trước đây sinh §2 / Art 2 giả."""

    def test_absatz_list_and_range(self) -> None:
        self.assertEqual([t for t, _ in _targets("nach § 6 Absatz 1 und 2 der InVeKoS-Verordnung")],
                         ["DE-InVeKoSV:§6(1)", "DE-InVeKoSV:§6(2)"])
        self.assertEqual([t for t, _ in _targets("Artikel 4 Absatz 1 bis 3 der Verordnung (EU) Nr. 1307/2013")],
                         ["R1307:Art4(1)", "R1307:Art4(2)", "R1307:Art4(3)"])

    def test_qualifier_lists_are_not_new_targets(self) -> None:
        self.assertEqual([t for t, _ in _targets("§ 9 Satz 1 und 2 gilt; Artikel 29 Absatz 1 Unterabsatz 1 "
                                                 "Buchstabe a bis c der Durchführungsverordnung (EU) Nr. 809/2014")],
                         ["DE-InVeKoSV:§9", "R809:Art29(1)"])

    def test_article_keyword_restarts(self) -> None:
        t = "Artikel 11 Absatz 4 und Artikel 12 der Delegierten Verordnung (EU) Nr. 640/2014"
        self.assertEqual([x for x, _ in _targets(t)], ["R640:Art11(4)", "R640:Art12"])


class TestParserAuditM4(unittest.TestCase):
    """Rà soát 2026-11-18 M4: bổ ngữ số nhiều, khoảng có chữ cái, 'des Gesetzes über …' (luật ngoài bộ)."""

    def test_plural_qualifier(self) -> None:
        t = "Artikel 44 Absatz 3 Unterabsätze 1 bis 3 der Verordnung (EU) Nr. 1307/2013"
        self.assertEqual([x for x, _ in _targets(t)], ["R1307:Art44(3)"])

    def test_letter_suffix_range(self) -> None:
        self.assertEqual([x for x, _ in _targets("nach den §§ 24a bis 24d")],
                         ["DE-InVeKoSV:§24a", "DE-InVeKoSV:§24b", "DE-InVeKoSV:§24c", "DE-InVeKoSV:§24d"])

    def test_gesetz_ueber_is_other_law(self) -> None:
        t = "im Sinne des § 36 Absatz 1 Nummer 1 des Gesetzes über Ordnungswidrigkeiten"
        self.assertEqual(_targets(t), [("DE-Gesetz über Ordnungswidrigkeiten:§36(1)", False)])


class TestChainedReferences(unittest.TestCase):
    def test_chain_inherits_law_of_last_member(self) -> None:
        """'§ 27 Absatz 2, des § 28 oder des § 29 der DZDV': cả ba thuộc DirektZahlDurchfV (trước đây §27 gán nhầm)."""
        t = ("aus Ackerflächen im Sinne des § 27 Absatz 2, des § 28 oder des § 29 der "
             "Direktzahlungen-Durchführungsverordnung")
        self.assertEqual([x for x, _ in _targets(t)], ["DE-DirektZahlDurchfV:§27(2)", "DE-DirektZahlDurchfV:§28",
                                                       "DE-DirektZahlDurchfV:§29"])

    def test_separate_sentences_do_not_chain(self) -> None:
        t = "nach § 19. Im Übrigen gilt § 5 der Direktzahlungen-Durchführungsverordnung."
        self.assertEqual([x for x, _ in _targets(t)], ["DE-InVeKoSV:§19", "DE-DirektZahlDurchfV:§5"])


class TestNationalReferences(unittest.TestCase):
    def test_internal_section_and_paragraph(self) -> None:
        t = "Satz 1 gilt für Landschaftselemente im Sinne des § 19 sowie für Flächen nach § 27 Absatz 2."
        self.assertEqual(_targets(t), [("DE-InVeKoSV:§19", True), ("DE-InVeKoSV:§27(2)", True)])

    def test_section_of_other_german_law(self) -> None:
        t = ("mit Ausnahme der in § 32 Absatz 2 der Direktzahlungen-Durchführungsverordnung genannten Arten; "
             "nach § 12 Absatz 1 des Direktzahlungen-Durchführungsgesetzes")
        self.assertEqual(_targets(t), [("DE-DirektZahlDurchfV:§32(2)", True),
                                       ("DE-DirektZahlDurchfG:§12(1)", False)])

    def test_section_ranges_and_lists(self) -> None:
        self.assertEqual([t for t, _ in _targets("die §§ 15 und 16 sowie §§ 20 bis 22")],
                         ["DE-InVeKoSV:§15", "DE-InVeKoSV:§16", "DE-InVeKoSV:§20", "DE-InVeKoSV:§21",
                          "DE-InVeKoSV:§22"])


class TestInVerbindungMit(unittest.TestCase):
    """Kiểm metamodel 2026-11-19 — câu nguyên văn InVeKoSV §3(1), §16(2), DirektZahlDurchfV §24d(1), §12."""

    def test_absatz_after_in_verbindung_mit_belongs_to_named_law(self) -> None:
        t = ("Die Landesregierungen bestimmen durch Rechtsverordnung nach § 6 Absatz 1 Nummer 2 in Verbindung mit "
             "Absatz 5 Satz 1 des Marktorganisationsgesetzes, auf welche")
        self.assertEqual(_targets(t), [("DE-Marktorganisationsgesetzes:§6(1)", False),
                                       ("DE-Marktorganisationsgesetzes:§6(5)", False)])

    def test_section_before_in_verbindung_mit_inherits_law(self) -> None:
        t = "nach § 9a Satz 1 und 2 in Verbindung mit § 6 Absatz 5 Satz 1 des Marktorganisationsgesetzes festlegen"
        self.assertEqual(_targets(t), [("DE-Marktorganisationsgesetzes:§9a", False),
                                       ("DE-Marktorganisationsgesetzes:§6(5)", False)])

    def test_internal_absatz_list_after_in_verbindung_mit(self) -> None:
        t = "Nach der Bekanntgabe einer Feststellung nach § 24c Absatz 1 in Verbindung mit Absatz 2 oder 3 hat"
        self.assertEqual(_targets(t, "DirektZahlDurchfV"),
                         [(f"DE-DirektZahlDurchfV:§24c({a})", True) for a in (1, 2, 3)])

    def test_own_section_followed_by_eu_articles_unchanged(self) -> None:
        t = ("bis zu dem in § 7 Absatz 1 in Verbindung mit den Artikeln 12 und 13 der Delegierten Verordnung (EU) "
             "Nr. 640/2014 vorgesehenen Schlusstermin")
        self.assertEqual(_targets(t), [("DE-InVeKoSV:§7(1)", True), ("R640:Art12", True), ("R640:Art13", True)])


class TestLabelSheetAcceptsGermanIds(unittest.TestCase):
    def test_german_ids_parsed_and_cap_ids_unchanged(self) -> None:
        from src.evaluation.cap_gold import parse_label_sheet
        tail = (": **Quan sát được:** Có · **Ràng buộc mới:** — · **Cần điều tham chiếu:** Có · "
                "**Độ chắc chắn:** Cao · **Lý do:** x")
        sheet = "\n".join(f"{nid}{tail}" for nid in
                          ("DE-InVeKoSV:§7(1)", "DE-InVeKoSV:§7(3)@2016", "DE-DirektZahlDurchfV:§12a@2017",
                           "R809:Art22(1)"))
        self.assertEqual(sorted(parse_label_sheet(sheet)),
                         ["DE-DirektZahlDurchfV:§12a@2017", "DE-InVeKoSV:§7(1)", "DE-InVeKoSV:§7(3)@2016",
                          "R809:Art22(1)"])


class TestGermanSheet(unittest.TestCase):
    DE = [{"node_id": "DE-InVeKoSV:§7(1)", "law": "InVeKoSV", "article_title": "Form und Frist", "years": [2015, 2016],
           "text": "(1) Antrag nach Artikel 11 der Delegierten Verordnung (EU) Nr. 640/2014 und § 19.",
           "refs": [{"target": "R640:Art11", "in_scope": True, "kind": "eu"},
                    {"target": "DE-InVeKoSV:§19", "in_scope": True, "kind": "internal"}]},
          {"node_id": "DE-InVeKoSV:§19@2015", "law": "InVeKoSV", "article_title": "LE", "years": [2015],
           "text": "Text 2015.", "refs": []},
          {"node_id": "DE-InVeKoSV:§19@2016-2017", "law": "InVeKoSV", "article_title": "LE", "years": [2016, 2017],
           "text": "Text 2016.", "refs": []}]
    CAP = {"R640:Art11(1)": {"text": "The single application shall cover …"}}

    def test_section_shows_eu_text_and_same_year_german_version(self) -> None:
        from scripts.export_de_candidates import section
        s = section(self.DE[0], self.DE, self.CAP)
        self.assertIn("The single application", s)
        self.assertIn("dẫn chiếu EU", s)
        self.assertIn("Text 2015.", s)  # hòa 1–1 năm: hiện cả hai phiên bản trùng nhiều nhất
        self.assertIn("năm 2015, 2016", s)

    def test_markdown_has_one_answer_line_per_item(self) -> None:
        from scripts.export_de_candidates import build_markdown
        md = build_markdown(self.DE, self.CAP)
        self.assertEqual(md.count("**Quan sát được:** ___"), 3)


if __name__ == "__main__":
    unittest.main()
