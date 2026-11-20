"""
Test cho src/preprocessing/parse_eu_act.py: tách các Quy định EU (CAP: 1306/2013, 1307/2013, 640/2014,
809/2014) thành từng khoản có tiền tố văn bản, và nhận diện dẫn chiếu trong / ngoài văn bản.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.preprocessing.parse_eu_act import find_references, split_articles  # noqa: E402

TEXT = """Whereas:
(1) Recital mentioning Article 9 should be ignored.
HAVE ADOPTED THIS REGULATION:
TITLE I
SCOPE AND DEFINITIONS
Article 1
Scope
This Regulation lays down the rules on payments.
Article 2
Payment to beneficiaries and
time limits
1. The payments shall be made within the period from 1 December to 30 June.
20.12.2013
EN
Official Journal of the European Union
L 347/585
2. Payments shall not be made before the verification referred to in Article 1 has been finalised.
CHAPTER II
Paying agencies and other bodies
S e c t i o n 1
G e n e r a l p r o v i s i o n s
Article 3
Late submission
Applications shall be submitted by the date set in accordance with point (b) of Article 78 of
Regulation (EU) No 1306/2013 and Article 13 of Delegated Regulation (EU) No 640/2014.
This Regulation shall be binding in its entirety.
ANNEX I
Article 4 in an annex must not be parsed
"""


class TestSplitArticles(unittest.TestCase):
    def setUp(self) -> None:
        self.chunks = {c["node_id"]: c for c in split_articles(TEXT, "R809")}

    def test_paragraph_ids_with_document_prefix(self) -> None:
        self.assertEqual(sorted(self.chunks), ["R809:Art1", "R809:Art2(1)", "R809:Art2(2)", "R809:Art3"])

    def test_recitals_and_annex_ignored(self) -> None:
        self.assertNotIn("R809:Art4", self.chunks)
        self.assertNotIn("Recital", " ".join(c["text"] for c in self.chunks.values()))

    def test_multiline_title(self) -> None:
        self.assertEqual(self.chunks["R809:Art2(1)"]["article_title"], "Payment to beneficiaries and time limits")
        self.assertEqual(self.chunks["R809:Art1"]["article_title"], "Scope")

    def test_page_header_and_structure_headings_removed(self) -> None:
        p2 = self.chunks["R809:Art2(2)"]["text"]
        self.assertNotIn("Official Journal", self.chunks["R809:Art2(1)"]["text"] + p2)
        self.assertNotIn("CHAPTER", p2)
        self.assertNotIn("S e c t i o n", p2)
        self.assertTrue(p2.endswith("has been finalised."))

    def test_text_joined_across_lines(self) -> None:
        self.assertIn("in accordance with point (b) of Article 78 of Regulation (EU) No 1306/2013",
                      self.chunks["R809:Art3"]["text"])

    def test_soft_hyphen_line_break_joined(self) -> None:
        text = "HAVE ADOPTED THIS REGULATION:\nArticle 1\nScope\nThe financing provided for in this Regu­\nlation shall apply.\n"
        self.assertIn("this Regulation shall apply", split_articles(text, "R1306")[0]["text"])

    def test_numeric_bound_flag(self) -> None:
        self.assertTrue(self.chunks["R809:Art2(1)"]["has_numeric_bound"])
        self.assertFalse(self.chunks["R809:Art1"]["has_numeric_bound"])


class TestParserAuditV12(unittest.TestCase):
    """v1.2 (rà soát dữ liệu H2, H3): dòng xuống hàng bắt đầu bằng năm, tiêu đề CHAPTER 2 / SECTION 3, chú thích '( 1 )'."""

    # bộ tách chỉ nhận Điều đánh số liên tục từ 'Article 1' (an toàn có sẵn) → dữ liệu thử bắt đầu từ Article 1
    def test_year_at_line_start_is_not_a_paragraph(self) -> None:
        text = ("HAVE ADOPTED THIS REGULATION:\nArticle 1\nPayment entitlements\n1. First paragraph.\n"
                "2. Entitlements shall expire on 31 December\n2014.\n3. Third paragraph.\n"
                "This Regulation shall be binding in its entirety")
        ids = [c["node_id"] for c in split_articles(text, "R1307")]
        self.assertEqual(ids, ["R1307:Art1(1)", "R1307:Art1(2)", "R1307:Art1(3)"])
        para2 = next(c for c in split_articles(text, "R1307") if c["node_id"] == "R1307:Art1(2)")
        self.assertTrue(para2["text"].endswith("31 December 2014."))

    def test_arabic_chapter_and_section_headings_dropped(self) -> None:
        text = ("HAVE ADOPTED THIS REGULATION:\nArticle 1\nReview\n1. Text of article one.\nCHAPTER 2\n"
                "Provisions applying to Bulgaria\nArticle 2\nOther\n1. Text two.\nSECTION 3\nGreening\n"
                "Article 3\nThird\n1. Text three.\nThis Regulation shall be binding in its entirety")
        texts = {c["node_id"]: c["text"] for c in split_articles(text, "R1307")}
        self.assertEqual(texts["R1307:Art1(1)"], "1. Text of article one.")
        self.assertEqual(texts["R1307:Art2(1)"], "1. Text two.")

    def test_spaced_footnote_removed(self) -> None:
        text = ("HAVE ADOPTED THIS REGULATION:\nArticle 1\nAccredited agencies\n1. Agencies shall act ( 1 ).\n"
                "( 1 ) Council Regulation (EC) No 58/2003 of 19 December 2002 (OJ L 11, 16.1.2003, p. 1).\n"
                "2. Second.\nThis Regulation shall be binding in its entirety")
        texts = {c["node_id"]: c["text"] for c in split_articles(text, "R1306")}
        self.assertNotIn("58/2003", texts["R1306:Art1(1)"])

    def test_word_broken_without_hyphen_rejoined_only_when_attested(self) -> None:
        """PDF R640: 'legisla\\ntion' (không gạch nối) nối lại vì 'legislation' có ở chỗ khác; 'of\\nthe' giữ nguyên."""
        text = ("HAVE ADOPTED THIS REGULATION:\nArticle 1\nScope\n1. Union legisla\ntion applies under the\n"
                "rules of\nthe legislation in force.\nThis Regulation shall be binding in its entirety")
        self.assertEqual(split_articles(text, "R640")[0]["text"],
                         "1. Union legislation applies under the rules of the legislation in force.")

    def test_footnote_with_page_abbreviation_without_dot_removed(self) -> None:
        """R809:Art5: '(OJ L 181, 20.6.2014, p 48).' — thiếu dấu chấm sau 'p'."""
        text = ("HAVE ADOPTED THIS REGULATION:\nArticle 1\nPenalties\nSubject to Union or national law.\n"
                "( 1 ) Commission Delegated Regulation (EU) No 640/2014 of 11 March 2014 supplementing "
                "(OJ L 181, 20.6.2014, p 48).\nThis Regulation shall be binding in its entirety")
        self.assertEqual(split_articles(text, "R809")[0]["text"], "Subject to Union or national law.")


class TestFindReferences(unittest.TestCase):
    KNOWN = {"1306/2013": "R1306", "640/2014": "R640"}

    def test_external_reference_to_known_regulation(self) -> None:
        refs = find_references("point (b) of Article 78 of Regulation (EU) No 1306/2013", "R809", self.KNOWN)
        self.assertEqual(refs, [{"target": "R1306:Art78", "kind": "external", "in_scope": True}])

    def test_external_reference_keeps_paragraph(self) -> None:
        refs = find_references("Article 72(1) of Regulation (EU) No 1306/2013", "R809", self.KNOWN)
        self.assertEqual(refs[0]["target"], "R1306:Art72(1)")

    def test_delegated_regulation_prefix(self) -> None:
        refs = find_references("Article 13 of Delegated Regulation (EU) No 640/2014", "R809", self.KNOWN)
        self.assertEqual(refs[0]["target"], "R640:Art13")

    def test_out_of_scope_regulation(self) -> None:
        refs = find_references("Article 28 of Regulation (EU) No 1305/2013", "R1307", self.KNOWN)
        self.assertEqual(refs, [{"target": "1305/2013:Art28", "kind": "external", "in_scope": False}])

    def test_internal_reference(self) -> None:
        refs = find_references("the verification referred to in Article 74 and Article 59(6)", "R1306", self.KNOWN)
        self.assertEqual([r["target"] for r in refs], ["R1306:Art74", "R1306:Art59(6)"])
        self.assertTrue(all(r["kind"] == "internal" for r in refs))

    def test_this_regulation_is_internal(self) -> None:
        refs = find_references("in accordance with Article 7 of this Regulation", "R1307", self.KNOWN)
        self.assertEqual(refs, [{"target": "R1307:Art7", "kind": "internal", "in_scope": True}])

    def test_point_suffix_does_not_break_external_reference(self) -> None:
        """640/2014 Điều 13: 'Article 78(b) of Regulation (EU) No 1306/2013' phải trỏ sang R1306."""
        refs = find_references("on the basis of Article 78(b) of Regulation (EU) No 1306/2013", "R640", self.KNOWN)
        self.assertEqual(refs, [{"target": "R1306:Art78", "kind": "external", "in_scope": True}])

    def test_paragraph_and_point_suffix(self) -> None:
        refs = find_references("Article 4(1)(c)(iii) of Regulation (EU) No 1306/2013", "R640", self.KNOWN)
        self.assertEqual(refs[0]["target"], "R1306:Art4(1)")

    def test_article_list_then_regulation(self) -> None:
        refs = find_references("Articles 46 and 47 of Regulation (EU) No 1308/2013", "R640", self.KNOWN)
        # F-REFLIST (kiểm toán đợt 2): MỌI phần tử của danh sách, không chỉ phần tử đầu
        self.assertEqual(refs, [{"target": "1308/2013:Art46", "kind": "external", "in_scope": False},
                                {"target": "1308/2013:Art47", "kind": "external", "in_scope": False}])

    def test_paragraph_list_then_regulation(self) -> None:
        known = {**self.KNOWN, "1307/2013": "R1307"}
        refs = find_references("Article 50(6), (7) and (8) of Regulation (EU) No 1307/2013", "R640", known)
        self.assertEqual(refs[0]["target"], "R1307:Art50(6)")

    def test_repeated_article_word_and_letter_suffix(self) -> None:
        refs = find_references("pursuant to Article 132(7) or Article 133a of Regulation (EC) No 73/2009", "R1307",
                               self.KNOWN)
        self.assertEqual([r["target"] for r in refs], ["73/2009:Art132(7)", "73/2009:Art133a"])

    def test_letter_suffix_article_list(self) -> None:
        refs = find_references("under Articles 85t and 103z of Council Regulation (EC) No 1234/2007", "R640", self.KNOWN)
        self.assertEqual([r["target"] for r in refs], ["1234/2007:Art85t", "1234/2007:Art103z"])

    def test_treaty_without_of(self) -> None:
        refs = find_references("in accordance with Articles 122 and 143 TFEU, or Article 258 TFEU", "R1306", self.KNOWN)
        self.assertEqual([r["target"] for r in refs], ["TFEU:Art122", "TFEU:Art143", "TFEU:Art258"])
        self.assertFalse(any(r["in_scope"] for r in refs))

    # v1.2 (rà soát dữ liệu H4) — câu lấy nguyên văn từ bộ CAP
    def test_regulation_without_no(self) -> None:
        known = {**self.KNOWN, "1307/2013": "R1307"}
        refs = find_references('"farmer", means a farmer within the meaning of Article 4 of Regulation (EU) 1307/2013;',
                               "R1306", known)
        self.assertEqual(refs, [{"target": "R1307:Art4", "kind": "external", "in_scope": True}])

    def test_euratom_first_and_bare_regulation(self) -> None:
        refs = find_references("The rules laid down in Article 8 of Regulation (Euratom, EC) No 2185/96 shall apply",
                               "R1306", self.KNOWN)
        self.assertEqual(refs[0]["target"], "2185/96:Art8")
        refs = find_references("Article 28(9) of Regulation 1305/2013", "R1306", self.KNOWN)
        self.assertEqual(refs[0]["target"], "1305/2013:Art28(9)")

    def test_in_conjunction_with_chain_takes_final_act(self) -> None:
        text = ("Article 133a of Regulation (EC) No 73/2009 in respect of 2013, with the exception of the reduction "
                "resulting from the application of Article 132(2) in conjunction with Articles 7 and 10 of that Regulation.")
        targets = [r["target"] for r in find_references(text, "R1307", self.KNOWN)]
        self.assertEqual(targets, ["73/2009:Art133a", "73/2009:Art132(2)", "73/2009:Art7", "73/2009:Art10"])

    def test_thereof_refers_to_previous_regulation(self) -> None:
        refs = find_references("Article 8 of Regulation (EU) No 182/2011, in conjunction with Article 5 thereof, shall apply",
                               "R1307", self.KNOWN)
        self.assertEqual([r["target"] for r in refs], ["182/2011:Art8", "182/2011:Art5"])

    def test_thereof_after_directive_points_to_directive(self) -> None:
        text = ("in accordance with Article 32(6) of Regulation (EU) No 1307/2013 … in accordance with Council Directive "
                "2002/57/EC ( 2 ), and in particular Article 12 thereof, or any other document")
        known = {**self.KNOWN, "1307/2013": "R1307"}
        self.assertEqual([r["target"] for r in find_references(text, "R809", known)],
                         ["R1307:Art32(6)", "2002/57/EC:Art12"])

    def test_that_regulation_without_antecedent_is_not_internal(self) -> None:
        refs = find_references("in accordance with Article 7 of that Regulation", "R1307", self.KNOWN)
        self.assertEqual(refs, [{"target": "unresolved:Art7", "kind": "external", "in_scope": False}])

    def test_no_duplicates(self) -> None:
        refs = find_references("Article 74 ... Article 74", "R1306", self.KNOWN)
        self.assertEqual(len(refs), 1)


if __name__ == "__main__":
    unittest.main()
