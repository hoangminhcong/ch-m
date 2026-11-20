"""
Kiểm toán đợt 2 (các phần còn lại): tách khoản / dẫn chiếu, phiếu nhãn thật, miền giá trị, thời hạn theo ngày lịch.
Đã duyệt sửa toàn bộ (2026-11-09); test là test hồi quy mang mã phát hiện (docs/AUDIT_CAP_PIPELINE.md, mục 6).
"""

import sys
import unicodedata
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.cap_gold import build_gold_candidates, parse_label_sheet  # noqa: E402
from src.mde.typing_environment import ProcessTypingEnvironment  # noqa: E402
from src.preprocessing.parse_eu_act import find_references  # noqa: E402
from src.symbolic.declare4py_verifier import Declare4Py  # noqa: E402

MAIL = "Payment application / Application / mail income"
GAMMA = {"valid_activities": [MAIL], "activities_by_origin": {},
         "case_attributes": {"case:year": {"type": "String", "samples": [], "domain": {"values": ["2015", "2016"]}},
                             "case:young farmer": {"type": "Boolean", "samples": [],
                                                   "domain": {"values": ["False", "True"]}}},
         "event_attributes": {"time:timestamp": {"type": "Timestamp", "samples": []}}}


def _line(nid: str, obs: str = "Có", cons: str = f"Existence({MAIL})", ref: str = "Không") -> str:
    return (f"{nid}: **Quan sát được:** {obs} · **Ràng buộc mới:** {cons} · **Cần điều tham chiếu:** {ref} · "
            f"**Độ chắc chắn:** Cao · **Lý do:** x")


def _targets(text: str, doc: str):
    return {r["target"] for r in find_references(text, doc)}


class TestReferenceLists(unittest.TestCase):
    def test_single_and_external_still_right(self) -> None:
        self.assertEqual(_targets("as referred to in Article 78 of Regulation (EU) No 1306/2013", "R809"),
                         {"R1306:Art78"})

    def test_lists_and_ranges_expanded(self) -> None:
        """AUDIT F-REFLIST (cao): 137 cụm danh sách/khoảng mất 385 đích; 50 khoản trong phiếu thiếu ngữ cảnh Y."""
        self.assertTrue({"R1306:Art53", "R1306:Art55", "R1306:Art56"}
                        <= _targets("pursuant to Articles 53, 55 and 56", "R1306"))
        self.assertTrue({"R1307:Art43", "R1307:Art44", "R1307:Art45", "R1307:Art46"}
                        <= _targets("referred to in Articles 43 to 46 of Regulation (EU) No 1307/2013", "R1306"))

    def test_list_with_qualifier_attributed_to_named_act(self) -> None:
        """AUDIT F-REFMIS (thấp): cụm chen 'except paragraph 7(e)' làm 3 dẫn chiếu bị gán nhầm thành nội bộ."""
        t = _targets("Article 20, Article 24, Article 30, except paragraph 7(e), and Article 39 of "
                     "Regulation (EU) No 1307/2013 shall apply", "R809")
        self.assertNotIn("R809:Art20", t)
        self.assertIn("R1307:Art20", t)


class TestReferenceExtensions(unittest.TestCase):
    def test_paragraph_ranges_and_points(self) -> None:
        t = _targets("Article 50(6), (7) and (8) and Article 30(1) to (3)(a) of Regulation (EU) No 1307/2013", "R640")
        self.assertEqual(t, {"R1307:Art50(6)", "R1307:Art50(7)", "R1307:Art50(8)",
                             "R1307:Art30(1)", "R1307:Art30(2)", "R1307:Art30(3)"})

    def test_points_inside_list_keep_reading(self) -> None:
        t = _targets("Article 21(1)(a) and (b) and Articles 28 to 31, 33 and 34 of Regulation (EU) No 1305/2013", "R809")
        self.assertEqual(t, {f"1305/2013:Art{n}" for n in ("21(1)", "28", "29", "30", "31", "33", "34")})

    def test_nested_points_do_not_cut_the_list(self) -> None:
        """Nguyên văn R809:Art32(3): '(b)(i)' từng làm danh sách đứt → Art36 bị gán nhầm thành nội bộ R809."""
        t = _targets("in accordance with Articles 21(1)(a), 28, 29 and 34 of Regulation (EU) No 1305/2013 or "
                     "Article 36(a)(iv) and (v), (b)(i), (iii) and (v) of Regulation (EC) No 1698/2005 involving", "R809")
        self.assertIn("1698/2005:Art36", t)
        self.assertNotIn("R809:Art36", t)

    def test_number_followed_by_unit_is_not_an_article(self) -> None:
        self.assertEqual(_targets("as laid down in Article 7 and 30 days after the decision", "R1306"),
                         {"R1306:Art7"})

    def test_paragraph_of_this_and_that_article(self) -> None:
        refs = find_references("the final dates referred to in paragraph 1 of this Article", "R809", {}, "Art13")
        self.assertEqual([r["target"] for r in refs], ["R809:Art13(1)"])
        refs = find_references("paragraphs 2 to 4 shall apply", "R809", {}, "Art13")
        self.assertEqual([r["target"] for r in refs], ["R809:Art13(2)", "R809:Art13(3)", "R809:Art13(4)"])
        refs = find_references("Article 10(1) in conjunction with paragraph 2 of that Article", "R1307", {}, "Art24")
        self.assertEqual([r["target"] for r in refs], ["R1307:Art10(1)", "R1307:Art10(2)"])
        self.assertEqual(find_references("paragraph 2 of Article 10", "R1307", {}, "Art24")[0]["target"],
                         "R1307:Art10")  # 'of Article 10' → dẫn chiếu Article, không phải khoản cùng Điều

    def test_annex_references(self) -> None:
        known = {"1307/2013": "R1307"}
        self.assertEqual({r["target"] for r in find_references("listed in Annexes II and III", "R1307", known)},
                         {"R1307:AnnexII", "R1307:AnnexIII"})
        self.assertEqual(find_references("set out in Annex X to Regulation (EU) No 1307/2013", "R640", known)[0],
                         {"target": "R1307:AnnexX", "kind": "external", "in_scope": True})
        self.assertEqual(find_references("in accordance with the Annex", "R809", known)[0]["target"], "R809:AnnexI")
        # 'the Annex to Regulation (EC) No 21/2004' (nguyên văn R640:Art2(1)) → phụ lục của văn bản NGOÀI bộ
        self.assertEqual(find_references("point A.3 of the Annex to Regulation (EC) No 21/2004 respectively",
                                         "R640", known)[0],
                         {"target": "21/2004:AnnexI", "kind": "external", "in_scope": False})


class TestActivityGroupsAndCaseScope(unittest.TestCase):
    """Rà phiếu nhãn thật (2026-11-10): giấy tờ đổi theo năm → nhóm {A | B}; Existence + điều kiện hồ sơ → cảnh báo."""

    P, G = "Parcel document / Main / initialize", "Geo parcel document / Declared / create"
    PAY = "Payment application / Application / begin payment"

    def setUp(self) -> None:
        self.gamma = {**GAMMA, "valid_activities": [MAIL, self.P, self.G, self.PAY]}

    def test_group_in_gamma_notation_and_scoring(self) -> None:
        from src.evaluation.cap_notation import NotationError, notation_to_ast
        from src.evaluation.cap_scoring import compare_ast
        a = notation_to_ast(f"Precedence({{{self.G} | {self.P}}} → {self.PAY})", self.gamma, "X")
        b = notation_to_ast(f"Precedence({{{self.P}|{self.G}}} -> {self.PAY})", self.gamma, "X")
        self.assertEqual(a["activation_activity"], f"{{{self.G} | {self.P}}}")  # dạng chuẩn, đã sắp xếp
        self.assertEqual(compare_ast(a, b), "EQ")
        self.assertEqual(compare_ast(a, {**b, "activation_activity": self.G}), "MISMATCH")
        with self.assertRaises(NotationError):
            notation_to_ast(f"Precedence({{{self.G} | nope}} → {self.PAY})", self.gamma, "X")
        self.assertFalse(ProcessTypingEnvironment(self.gamma).delta_activity(f"{{{self.G} | nope}}")[0])

    def test_engine_group_covers_both_years(self) -> None:
        ev = pd.DataFrame({"case:concept:name": ["c15", "c15", "c16", "c16"],
                           "concept:name": [self.P, self.PAY, self.G, self.PAY],
                           "time:timestamp": pd.to_datetime(["2015-05-01", "2015-12-01", "2016-05-01", "2016-12-01"],
                                                            utc=True)})
        eng = Declare4Py(ev, timezone="Europe/Berlin")
        states = lambda line: {cid: eng._check_single_trace(t["events"], eng.parse_decl_lines([line])[0], True).state  # noqa: E731
                               for cid, t in eng._trace_index.items()}
        self.assertEqual(states(f"Precedence[{self.G}, {self.PAY}] | | |"), {"c15": "Violated", "c16": "Satisfied"})
        self.assertEqual(states(f"Precedence[{{{self.G} | {self.P}}}, {self.PAY}] | | |"),
                         {"c15": "Satisfied", "c16": "Satisfied"})

    def test_existence_with_case_condition_is_flagged(self) -> None:
        from src.evaluation.cap_gold import case_condition_flags
        base = {"template_name": "Existence", "activation_activity": self.G, "extra_conditions": []}
        self.assertTrue(case_condition_flags({**base, "activation_attr": "case:greening"}))
        self.assertEqual(case_condition_flags({**base, "activation_attr": "date"}), [])  # chỉ ngày: không cảnh báo
        # ngày + điều kiện hồ sơ (như R809:Art71(6) trong phiếu thật) → vẫn cảnh báo
        self.assertTrue(case_condition_flags({**base, "activation_attr": "date", "extra_conditions": [
            {"attr": "case:selected_random", "op": "==", "val": True}]}))
        self.assertEqual(case_condition_flags({**base, "template_name": "Responded Existence",
                                               "activation_attr": "case:greening"}), [])
        self.assertEqual(case_condition_flags({**base, "template_name": "Absence",
                                               "activation_attr": "case:rejected"}), [])


class TestAnnexInGraph(unittest.TestCase):
    def test_annex_node_edge_and_context(self) -> None:
        from src.kg.regulation_graph_builder import build_regulation_graph
        from src.neural.graph_context import LegalGraphIndex, graph_context_chunk
        chunk = {"node_id": "R1307:Art41(4)", "doc_id": "R1307", "article_title": "t", "has_numeric_bound": True,
                 "text": "the average size set out in Annex VIII", "refs": find_references(
                     "the average size set out in Annex VIII", "R1307", {"1307/2013": "R1307"})}
        annex = {"node_id": "R1307:AnnexVIII", "doc_id": "R1307", "article_title": "Average size",
                 "text": "Belgium 29 Bulgaria 6", "has_numeric_bound": False, "kind": "annex", "refs": []}
        g = build_regulation_graph([chunk], [annex]).to_dict()
        labels = {n["id"]: n["label"] for n in g["nodes"]}
        self.assertEqual(labels["R1307:AnnexVIII"], "Annex")
        ctx = graph_context_chunk(chunk, LegalGraphIndex(g))
        self.assertEqual(ctx["context_refs"], ["R1307:AnnexVIII"])
        self.assertIn("Belgium 29", ctx["text"])


class TestLabelSheetRobustness(unittest.TestCase):
    CANDS = [{"node_id": "R1:Art1", "round": 1, "text": "x"}, {"node_id": "R1:Art2", "round": 1, "text": "x"}]

    def test_nfd_text_is_read(self) -> None:
        """AUDIT F-SHEET (cao): tiếng Việt dạng tổ hợp (NFD) → dòng bị bỏ qua IM LẶNG, khoản thành 'Chưa điền'."""
        self.assertIn("R1:Art1", parse_label_sheet(unicodedata.normalize("NFD", _line("R1:Art1"))))

    def test_malformed_line_is_reported(self) -> None:
        """AUDIT F-SHEET: dòng có mã khoản nhưng sai định dạng (VD '|' thay '·') phải BÁO LỖI, không bỏ qua."""
        with self.assertRaises(ValueError):
            parse_label_sheet(_line("R1:Art1").replace(" · ", " | "))

    def test_tier4_answer_with_explanation(self) -> None:
        """AUDIT F-SHEET (cao): 'Có (ngày lấy từ …)' ở câu (3) → Tier 4 bị đánh Không IM LẶNG."""
        labels = parse_label_sheet(_line("R1:Art1", ref="Có (ngày 15/5 lấy từ R809:Art13)") + "\n"
                                   + _line("R1:Art2", obs="Không", cons="—", ref="—"))
        self.assertTrue(build_gold_candidates(labels, self.CANDS, GAMMA)["clauses"]["R1:Art1"]["tier4"])

    def test_duplicate_line_is_reported(self) -> None:
        """AUDIT F-SHEET: hai dòng cùng khoản → dòng sau đè dòng trước IM LẶNG."""
        with self.assertRaises(ValueError):
            parse_label_sheet(_line("R1:Art1") + "\n" + _line("R1:Art1", obs="Không", cons="—", ref="—"))

    def test_trailing_punctuation_and_unsure_variants(self) -> None:
        """AUDIT F-SHEET (thấp): 'Có.' và 'Không chắc chắn' bị coi là giá trị lạ (có báo lỗi)."""
        self.assertEqual(parse_label_sheet(_line("R1:Art1", obs="Có."))["R1:Art1"]["observable"], "yes")
        self.assertEqual(parse_label_sheet(_line("R1:Art1", obs="Không chắc chắn", cons="—", ref="—"))
                         ["R1:Art1"]["observable"], "unsure")


class TestValueDomainNormalization(unittest.TestCase):
    def test_equivalent_spellings_not_rejected(self) -> None:
        """AUDIT F-DOMVAL (trung bình): kiểm C chặn oan 2016.0 (năm dạng số) và 'true' (chữ thường)."""
        g = ProcessTypingEnvironment(GAMMA)
        self.assertTrue(g.check_type_conformance("case:year", "==", 2016.0)[0])
        self.assertTrue(g.check_type_conformance("case:young farmer", "==", "true")[0])


class TestCalendarDayPeriods(unittest.TestCase):
    def test_days_counted_by_calendar_date(self) -> None:
        """
        AUDIT F-DAYS (thấp–trung bình): Quy định (EEC, Euratom) 1182/71 — thời hạn theo ngày/tuần/tháng tính theo
        NGÀY LỊCH, hết hạn cuối ngày cuối cùng. Engine tính 'n ngày' = n×24 giờ: sự kiện 'mail income' chỉ có ngày
        (00:00 giờ Đức), xử lý lúc 10:00 ngày hôm sau bị coi là trễ hạn '1 ngày'.
        """
        self.assertEqual(self._state(["2016-05-04 22:00", "2016-05-06 08:00"], "0,1,d"), "Satisfied")
        self.assertEqual(self._state(["2016-05-04 22:00", "2016-05-07 08:00"], "0,1,d"), "Violated")
        # mặc định (BPIC2017) giữ n×24 giờ
        self.assertEqual(self._state(["2016-05-04 22:00", "2016-05-06 08:00"], "0,1,d", calendar=False), "Violated")

    def test_weekend_rollover_and_month_end(self) -> None:
        # A thứ Năm 12/5/2016 → hạn 2 ngày = thứ Bảy 14/5 → lùi sang thứ Hai 16/5 (Quy định 1182/71 Điều 3(4))
        self.assertEqual(self._state(["2016-05-12 08:00", "2016-05-16 15:00"], "0,2,d"), "Satisfied")
        self.assertEqual(self._state(["2016-05-12 08:00", "2016-05-17 08:00"], "0,2,d"), "Violated")
        # 31/1 + 1 tháng = 29/2/2016 (năm nhuận, cuối tháng) — thứ Hai
        self.assertEqual(self._state(["2016-01-31 08:00", "2016-02-29 20:00"], "0,1,mo"), "Satisfied")
        self.assertEqual(self._state(["2016-01-31 08:00", "2016-03-01 08:00"], "0,1,mo"), "Violated")
        self.assertEqual(self._state(["2016-05-02 08:00", "2016-05-16 20:00"], "0,2,w"), "Satisfied")
        # 23:30 UTC = 01:30 ngày 17/5 giờ Đức → đã quá hạn (ngày lịch tính theo giờ địa phương)
        self.assertEqual(self._state(["2016-05-02 08:00", "2016-05-16 23:30"], "0,2,w"), "Violated")

    @staticmethod
    def _state(times, window: str, calendar: bool = True) -> str:
        """Hai sự kiện A, B (giờ UTC) → trạng thái Response[A, B] với cửa sổ cho trước, giờ Đức."""
        ev = pd.DataFrame({"case:concept:name": ["c", "c"], "concept:name": ["A", "B"],
                           "time:timestamp": pd.to_datetime(times, utc=True)})
        eng = Declare4Py(ev, timezone="Europe/Berlin", calendar_periods=calendar)
        c = eng.parse_decl_lines([f"Response[A, B] | | | {window}"])[0]
        return eng._check_single_trace(eng._trace_index["c"]["events"], c, True).state


if __name__ == "__main__":
    unittest.main()
