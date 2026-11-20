"""
v1.2 (người dùng duyệt 2026-11-19, docs/V2_DANG_KY_TRUOC.md): sửa các lỗi lõi do agent rà soát xác minh.
  C1  Entity Matcher: số ít / 'calendar months' / 'per cent' / '30-day' / 'ten (10) days' / '1,000 EUR' /
      không gộp 'Article 12 150 hectares' / tiếng Đức 'EUR', '3 der Tage'
  C2  chỉ kết luận BASELESS khi giám khảo / Entity Matcher thật sự trả BASELESS (không dò chuỗi con)
  C3  điều kiện phụ 'A.attr' được chuẩn hoá như điều kiện chính
  C4  ngày làm việc: sự kiện vào cuối tuần → đếm từ thứ Hai
  C5  đơn vị của time_max phải khớp đơn vị trong luật
  C6  time_min được kiểm và được diễn đạt lại; Responded Existence có thời hạn
  C7  phản hồi "một lần" theo ràng buộc (dòng .decl), không theo cả AST (decomposition tự do)
Không gọi API.
"""

import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.symbolic.verbalizer_roundtrip import (  # noqa: E402
    extract_clause_numeric_entities,
    verbalize_declare_ast,
    verify_generic_numeric_entities,
)

A, B = "Payment application / Application / mail income", "Payment application / Application / begin payment"


def _ents(text):
    return set(extract_clause_numeric_entities(text))


def _ast(template="Response", **kw):
    base = {"article_id": "R1:Art1", "template_name": template, "activation_activity": A, "target_activity": B,
            "activation_attr": None, "activation_op": None, "activation_val": None, "extra_conditions": [],
            "time_min": None, "time_max": None, "time_unit": None}
    return {**base, **kw}


class TestEntityForms(unittest.TestCase):
    def test_singular_and_prefixed_units(self) -> None:
        self.assertIn((1.0, "months"), _ents("within 1 month"))
        self.assertIn((1.0, "years"), _ents("within 1 year"))
        self.assertIn((1.0, "days"), _ents("1 working day"))
        self.assertIn((3.0, "months"), _ents("three calendar months"))
        self.assertIn((30.0, "days"), _ents("a 30-day period"))
        self.assertIn((10.0, "days"), _ents("within ten (10) days"))
        self.assertIn((10.0, "%"), _ents("10 per cent of the claims"))

    def test_thousands_and_no_cross_number_merge(self) -> None:
        self.assertIn((1000.0, "EUR"), _ents("up to 1,000 EUR"))
        self.assertNotIn((12150.0, "ha"), _ents("Article 12 150 hectares"))
        self.assertIn((150.0, "ha"), _ents("Article 12 150 hectares"))
        self.assertIn((75000.0, "EUR"), _ents("EUR 75 000"))

    def test_german_eur_and_stopword(self) -> None:
        self.assertIn((1250.0, "EUR"), _ents("Beträge bis 1.250 EUR"))
        self.assertNotIn((3.0, "days"), _ents("binnen 3 der Tage"))


class TestUnitsAndTimeMin(unittest.TestCase):
    CHUNK = {"article_id": "R1:Art1", "text": "The payment shall be made within 14 days. 5 % of the claims."}

    def test_time_unit_must_match_clause(self) -> None:
        ok, _, _ = verify_generic_numeric_entities(_ast(time_max=14, time_unit="d"), self.CHUNK)
        self.assertTrue(ok)
        ok, verdict, _ = verify_generic_numeric_entities(_ast(time_max=14, time_unit="mo"), self.CHUNK)
        self.assertFalse(ok)
        self.assertEqual(verdict, "THRESHOLD_MISMATCH")
        ok, _, _ = verify_generic_numeric_entities(_ast(time_max=5, time_unit="d"), self.CHUNK)
        self.assertFalse(ok)  # 5 chỉ có trong luật dưới dạng '%', không phải thời hạn

    def test_time_min_checked_and_verbalized(self) -> None:
        ok, _, _ = verify_generic_numeric_entities(_ast(time_min=3, time_max=14, time_unit="d"), self.CHUNK)
        self.assertFalse(ok)
        self.assertIn("3", verbalize_declare_ast(_ast(time_min=3, time_max=14, time_unit="d")))
        self.assertIn("14", verbalize_declare_ast(_ast("Responded Existence", time_max=14, time_unit="d")))


class TestLoopFixes(unittest.TestCase):
    def test_baseless_only_on_real_verdict(self) -> None:
        from src.evaluation.real_llm_client import is_baseless_message
        self.assertTrue(is_baseless_message("[Layer 3 Semantic BASELESS]: no basis"))
        self.assertFalse(is_baseless_message("[Layer 3 Semantic REVERSED_ORDER]: not BASELESS, order reversed"))

    def test_once_key_ignores_free_text(self) -> None:
        from src.evaluation.real_llm_client import constraint_key
        a = {**_ast(), "decomposition": None}
        b = {**_ast(), "decomposition": {
            "temporal_direction": "Consequence (Response: Activation A triggers subsequent Target B)",
            "activation_semantics": "câu chữ tự do do LLM viết", "target_semantics": "khác nhau mỗi vòng"}}
        self.assertEqual(constraint_key(a), constraint_key(b))


class TestTypingAndTime(unittest.TestCase):
    def test_extra_condition_prefix_normalised(self) -> None:
        from src.mde.typing_environment import ProcessTypingEnvironment
        from src.mde.constraint_ast import DeclareConstraintAST
        env = ProcessTypingEnvironment({"valid_activities": [A, B], "activities_by_origin": {},
                                        "case_attributes": {"case:y": {"type": "Float", "samples": [1, 2]}},
                                        "event_attributes": {}})
        ast = DeclareConstraintAST.model_validate(_ast(activation_attr="case:y", activation_op=">=", activation_val=1,
                                                       extra_conditions=[{"attr": "A.case:y", "op": "==", "val": 2}]))
        env.validate_ast(ast, {"article_id": "R1:Art1", "text": "t"})
        self.assertEqual(ast.extra_conditions[0].attr, "case:y")

    def test_working_days_from_weekend(self) -> None:
        from src.symbolic.time_windows import parse_time_window, within
        tz = ZoneInfo("Europe/Berlin")
        sat = datetime(2016, 5, 14, 10, tzinfo=tz).timestamp()  # thứ Bảy
        tue = datetime(2016, 5, 17, 10, tzinfo=tz).timestamp()
        wed = datetime(2016, 5, 18, 10, tzinfo=tz).timestamp()
        w = parse_time_window("0,2,wd")
        self.assertTrue(within(sat, tue, w, tz, True))
        self.assertFalse(within(sat, wed, w, tz, True))


if __name__ == "__main__":
    unittest.main()
