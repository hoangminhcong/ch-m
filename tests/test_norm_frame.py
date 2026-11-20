"""
Cấu hình N — khung chuẩn tắc có danh mục đóng (đăng ký trước B6; src/symbolic/norm_frame.py): N1 định dạng, N2 loại
không diễn đạt được → BASELESS theo code, N3 thời hạn đã trích phải có trong ràng buộc, N4 hỗ trợ từ KG (MAPS_TO,
phản hồi một lần). Không truyền `norm` → vòng lặp như trước.
"""

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.symbolic.norm_frame import (  # noqa: E402
    NORM_TYPES, NormFrame, ast_doctypes, frame_error, kg_support, missing_deadline, not_expressible)

MAIL = "Payment application / Application / mail income"
PAY = "Payment application / Main / begin payment"
INSPECT = "Inspection / On-Site / performed"
GAMMA = {"valid_activities": [MAIL, PAY, INSPECT], "activities_by_origin": {},
         "case_attributes": {"case:year": {"type": "String", "samples": []}},
         "event_attributes": {"time:timestamp": {"type": "Timestamp", "samples": []}}}
CLAUSE = {"node_id": "R9:Art1(1)", "round": 1,
          "text": "Payment shall be made within 30 days after the aid application is received."}
FRAME = NormFrame(frozenset({"Payment application"}))


def _analysis(norm_type="deadline", deadline="within 30 days", **kw):
    return {"duty_bearer": "paying_agency_case_processing", "observable_in_log": True,
            "evidence": "Payment shall be made within 30 days", "norm_type": norm_type,
            "action": "Payment shall be made", "deadline": deadline, **kw}


def _rule(act=MAIL, tgt=PAY, time_max=30, analysis=None):
    return {"article_id": "R9:Art1(1)", "obligation_analysis": analysis or _analysis(),
            "template_name": "Response", "activation_activity": act, "target_activity": tgt,
            "activation_attr": None, "activation_op": None, "activation_val": None, "extra_conditions": [],
            "time_min": None, "time_max": time_max, "time_unit": "d" if time_max else None}


class ScriptedLLM:
    def __init__(self, outputs):
        self.outputs, self.feedback, self.calls = list(outputs), [], 0

    def chat_json(self, msgs, temperature=0.0, **_):
        if isinstance(msgs, list):
            if self.calls:
                self.feedback.append(msgs[-1]["content"])
            self.calls += 1
            self.system = msgs[0]["content"]
            return json.dumps(self.outputs.pop(0))
        return {"verdict": "EQUIVALENT", "diagnostic_feedback": "ok"}


def _run(outputs, norm=FRAME):
    from src.evaluation.real_llm_client import run_single_rule_with_real_llm
    from src.neural.graph_context import clause_only_chunk
    from src.symbolic.domain_profiles import CAP_PROFILE_NORM
    llm = ScriptedLLM(outputs)
    res = run_single_rule_with_real_llm({"rule_id": "t"}, clause_only_chunk(CLAUSE), GAMMA, llm,
                                        profile=CAP_PROFILE_NORM, norm=norm)
    return res, [t["status"] for t in res["trajectory"]], llm


class TestFrameRules(unittest.TestCase):
    def test_n1_closed_vocabulary_and_quotes(self) -> None:
        self.assertIsNone(frame_error(_analysis()))
        self.assertIn("norm_type", frame_error(_analysis(norm_type="duty")))
        self.assertIn("action", frame_error(_analysis(action=" ")))
        self.assertIn("deadline", frame_error(_analysis(deadline=3)))

    def test_n2_only_ordering_deadline_prohibition_expressible(self) -> None:
        self.assertEqual({t for t in NORM_TYPES if not not_expressible({"norm_type": t})},
                         {"action_order", "deadline", "prohibition"})

    def test_n3_deadline_needs_time_or_date_condition(self) -> None:
        self.assertIsNotNone(missing_deadline(_analysis(), _rule(time_max=None)))
        self.assertIsNone(missing_deadline(_analysis(), _rule()))
        dated = {**_rule(time_max=None), "activation_attr": "date", "activation_op": "<=", "activation_val": "year-05-15"}
        self.assertIsNone(missing_deadline(_analysis(), dated))
        self.assertIsNone(missing_deadline(_analysis(deadline=None), _rule(time_max=None)))

    def test_n4_doctypes_of_groups_and_support(self) -> None:
        group = "{" + f"{MAIL} | {INSPECT}" + "}"
        self.assertEqual(ast_doctypes(_rule(act=group)), frozenset({"Payment application", "Inspection"}))
        self.assertTrue(kg_support(_rule(), FRAME.clause_doctypes)["supported"])
        self.assertEqual(kg_support(_rule(tgt=INSPECT), FRAME.clause_doctypes)["unsupported"], ["Inspection"])
        self.assertFalse(kg_support(_rule(), frozenset())["supported"])  # khoản không có MAPS_TO → không hỗ trợ


class TestLoopWithNormFrame(unittest.TestCase):
    def test_supported_rule_passes_and_records_kg_support(self) -> None:
        res, statuses, llm = _run([_rule()])
        self.assertEqual(statuses, ["PASSED"])
        self.assertTrue(res["norm_checks"]["kg_support"]["supported"])
        self.assertIn('"norm_type"', llm.system)

    def test_n2_declines_even_when_constraint_given(self) -> None:
        res, statuses, _ = _run([_rule(analysis=_analysis(norm_type="content_requirement", deadline=None))])
        self.assertEqual(statuses, ["DECLINED_NORM_TYPE"])
        self.assertIsNone(res["final_ast"])
        from scripts.run_cap_generation import outcome_of
        self.assertEqual(outcome_of(res), "BASELESS")

    def test_n1_bad_frame_gets_feedback(self) -> None:
        _, statuses, llm = _run([_rule(analysis=_analysis(norm_type="duty")), _rule()])
        self.assertEqual(statuses, ["FAILED_NORM_FRAME", "PASSED"])
        self.assertIn("norm_type", llm.feedback[0])

    def test_n3_dropped_deadline_is_sent_back(self) -> None:
        _, statuses, llm = _run([_rule(time_max=None), _rule()])
        self.assertEqual(statuses, ["FAILED_NORM_DEADLINE", "PASSED"])
        self.assertIn("within 30 days", llm.feedback[0])

    def test_n4_feedback_once_then_accept_with_flag(self) -> None:
        off = _rule(tgt=INSPECT)
        res, statuses, llm = _run([off, off])
        self.assertEqual(statuses, ["FAILED_KG_SUPPORT", "PASSED"])
        self.assertIn("'Payment application'", llm.feedback[0])
        self.assertFalse(res["norm_checks"]["kg_support"]["supported"])

    def test_without_norm_no_new_keys_or_statuses(self) -> None:
        res, statuses, _ = _run([_rule(tgt=INSPECT, analysis=_analysis(norm_type="calculation"))], norm=None)
        self.assertEqual(statuses, ["PASSED"])
        self.assertNotIn("norm_checks", res)


class TestConfigN(unittest.TestCase):
    def test_config_profile_inputs_and_funnel(self) -> None:
        from scripts.run_cap_generation import CONFIGS, input_paths, profile_for
        from src.evaluation.verification_funnel import LAYER_OF
        self.assertTrue(CONFIGS["N"]["norm"])
        self.assertEqual(profile_for("N").name, "cap-norm")
        self.assertEqual(profile_for("N", "de").name, "cap-norm-de")
        self.assertEqual(profile_for("Y").name, "cap")  # prompt Y không đổi
        self.assertIn("mapping_graph", input_paths("N"))  # MAPS_TO đọc từ KG cầu nối (một nguồn duy nhất)
        self.assertNotIn("mapping_graph", input_paths("Y"))
        self.assertIn("mapping_graph", input_paths("Z"))
        for s in ("FAILED_NORM_FRAME", "DECLINED_NORM_TYPE", "FAILED_NORM_DEADLINE", "FAILED_KG_SUPPORT"):
            self.assertIn(s, LAYER_OF)

    def test_norm_prompt_extends_y_prompt_only(self) -> None:
        from src.symbolic.domain_profiles import CAP_PROFILE, CAP_PROFILE_NORM
        self.assertTrue(CAP_PROFILE_NORM.generator_system.startswith(CAP_PROFILE.generator_system))
        self.assertEqual(len(CAP_PROFILE_NORM.examples), len(CAP_PROFILE.examples) + 1)


class TestN1QuotesMustBeReal(unittest.TestCase):
    """N1 (bổ sung 2026-11-20): action / deadline phải là trích dẫn thật của văn bản đưa cho LLM."""

    def test_quote_check(self) -> None:
        from src.symbolic.norm_frame import quote_error
        text = [CLAUSE["text"]]
        self.assertIsNone(quote_error(_analysis(), text))
        self.assertIn("action", quote_error(_analysis(action="The authority must inspect every parcel"), text))
        self.assertIn("deadline", quote_error(_analysis(deadline="no later than 15 May each year"), text))
        self.assertIsNone(quote_error(_analysis(deadline="by 1 May"), text))  # quá ngắn để kết luận → không xét

    def test_loop_sends_back_fabricated_quote(self) -> None:
        fake = _rule(analysis=_analysis(action="The authority must inspect every parcel"))
        _, statuses, llm = _run([fake, _rule()])
        self.assertEqual(statuses, ["FAILED_NORM_FRAME", "PASSED"])
        self.assertIn("not a quote", llm.feedback[0])


class TestN5TemplateMatchesNormType(unittest.TestCase):
    def test_every_template_fits_some_expressible_norm_type(self) -> None:
        from src.mde.constraint_ast import BINARY_TEMPLATES, UNARY_TEMPLATES
        from src.symbolic.norm_frame import EXPRESSIBLE, TEMPLATES_BY_NORM
        self.assertEqual(set(TEMPLATES_BY_NORM), set(EXPRESSIBLE))
        covered = set().union(*TEMPLATES_BY_NORM.values())
        self.assertEqual(covered, UNARY_TEMPLATES | BINARY_TEMPLATES)

    def test_prohibition_rejects_positive_order_template(self) -> None:
        from src.symbolic.norm_frame import template_error
        self.assertIn("prohibition", template_error(_analysis(norm_type="prohibition", deadline=None), _rule()))
        self.assertIsNone(template_error(_analysis(norm_type="deadline"), _rule()))
        self.assertIsNone(template_error(None, _rule()))

    def test_loop_sends_template_feedback_then_passes(self) -> None:
        wrong = _rule(analysis=_analysis(norm_type="prohibition", deadline=None), time_max=None)
        _, statuses, llm = _run([wrong, _rule()])
        self.assertEqual(statuses, ["FAILED_NORM_TEMPLATE", "PASSED"])
        self.assertIn("Not Co-Existence", llm.feedback[0])


if __name__ == "__main__":
    unittest.main()
