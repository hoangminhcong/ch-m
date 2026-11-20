"""
Các kiểm chống ràng buộc rỗng / bịa (bộ CAP), xuất phát từ R1306:Art70(2): hệ thống sinh
'Precedence[…] | A.case:year == 2018' trong khi log chỉ có 2015–2017 và nghĩa vụ là của Nhà nước (lập hệ thống).

  C  Γ kiểm miền giá trị đầy đủ lấy từ KG          (typing_environment.check_value_domain)
  E  Entity Matcher: giá trị dạng năm phải có trong luật (verbalizer_roundtrip, check_year_values)
  B  kiểm rỗng trên log trong vòng lặp             (log_grounding + Declare4Py.count_witness_cases)
  D  phân tích nghĩa vụ, được phép no_constraint   (obligation_gate + CAP_PROFILE)
Cộng sửa lỗi cũ: run_generic_cegis_diagnostic kiểm rỗng mọi loại điều kiện, bỏ nhánh viết cứng Directive.
Log và khoản luật ở đây là GIẢ, nhỏ, chỉ để kiểm hành vi.
"""

import json
import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_cap_generation import CONFIGS, outcome_of, run_clause, schema_for  # noqa: E402
from src.evaluation.experiment_runner import run_generic_cegis_diagnostic  # noqa: E402
from src.evaluation.real_llm_client import run_single_rule_with_real_llm  # noqa: E402
from src.mde.typing_environment import ProcessTypingEnvironment  # noqa: E402
from src.neural.graph_context import clause_only_chunk  # noqa: E402
from src.symbolic.declare4py_verifier import Declare4Py  # noqa: E402
from src.symbolic.domain_profiles import BPIC2017_PROFILE, CAP_PROFILE, CAP_PROFILE_NO_DUTY  # noqa: E402
from src.symbolic.log_grounding import LogGroundingChecker, vacuity_feedback  # noqa: E402
from src.symbolic.obligation_gate import assess_obligation  # noqa: E402
from src.symbolic.verbalizer_roundtrip import verify_generic_numeric_entities  # noqa: E402

REF = "Reference alignment / Main / performed"
INIT = "Entitlement application / Main / initialize"
MAIL = "Payment application / Application / mail income"
GAMMA = {
    "valid_activities": [REF, INIT, MAIL], "activities_by_origin": {},
    "case_attributes": {
        "case:year": {"type": "String", "samples": ["2015", "2016"], "domain": {"values": ["2015", "2016"]}},
        "case:area": {"type": "Float", "samples": [0.0, 576.07], "domain": {"min": 0.0, "max": 576.07}},
        "case:young farmer": {"type": "Boolean", "samples": ["False", "True"], "domain": {"values": ["False", "True"]}},
    },
    "event_attributes": {"time:timestamp": {"type": "Timestamp", "samples": []}},
}
CLAUSE = {"node_id": "R9:Art70(2)", "round": 1,
          "text": "Member States shall ensure that the identification system contains a reference layer "
                  "before the application forms are provided in respect of claim year 2018 at the latest."}
ANALYSIS_OK = {"duty_bearer": "paying_agency_case_processing", "observable_in_log": True, "evidence": "x"}


def _ast(**kw):
    base = {"article_id": "R9:Art70(2)", "template_name": "Precedence", "activation_activity": REF,
            "target_activity": INIT, "activation_attr": None, "activation_op": None, "activation_val": None,
            "extra_conditions": [], "time_min": 0, "time_max": None, "time_unit": "d"}
    return {**base, **kw}


def _engine() -> Declare4Py:
    """3 hồ sơ: c1 (2015) REF→INIT, c2 (2016) INIT, c3 (2016) MAIL. young farmer chỉ ở c2."""
    rows = [("c1", REF, "2016-01-01"), ("c1", INIT, "2016-01-02"), ("c2", INIT, "2017-01-01"),
            ("c3", MAIL, "2017-02-01")]
    events = pd.DataFrame(rows, columns=["case:concept:name", "concept:name", "time:timestamp"])
    cases = pd.DataFrame({"case:concept:name": ["c1", "c2", "c3"], "case:year": ["2015", "2016", "2016"],
                          "case:area": [1.0, 2.0, 3.0], "case:young farmer": [False, True, False]})
    return Declare4Py(events, cases=cases)


class TestValueDomainC(unittest.TestCase):
    def setUp(self) -> None:
        self.gamma = ProcessTypingEnvironment(GAMMA)

    def test_equality_outside_observed_values_rejected(self) -> None:
        ok, msg = self.gamma.check_type_conformance("case:year", "==", "2018")
        self.assertFalse(ok)
        self.assertIn("Value Domain Violation", msg)
        self.assertTrue(self.gamma.check_type_conformance("case:year", "==", "2016")[0])
        self.assertTrue(self.gamma.check_type_conformance("year", "==", "2016")[0])  # tên rút gọn
        self.assertTrue(self.gamma.check_type_conformance("case:year", "!=", "2018")[0])  # luôn đúng, không rỗng

    def test_numeric_range(self) -> None:
        self.assertFalse(self.gamma.check_type_conformance("case:area", ">", 600)[0])
        self.assertFalse(self.gamma.check_type_conformance("case:area", ">", 576.07)[0])
        self.assertTrue(self.gamma.check_type_conformance("case:area", ">=", 576.07)[0])
        self.assertFalse(self.gamma.check_type_conformance("case:area", "<", 0)[0])
        self.assertTrue(self.gamma.check_type_conformance("case:area", ">", 10)[0])

    def test_boolean_domain(self) -> None:
        self.assertTrue(self.gamma.check_type_conformance("case:young farmer", "==", True)[0])

    def test_schema_without_domain_unchanged(self) -> None:
        old = {**GAMMA, "case_attributes": {"case:year": {"type": "String", "samples": ["2015"]}}}
        self.assertTrue(ProcessTypingEnvironment(old).check_type_conformance("case:year", "==", "2018")[0])

    def test_feedback_suggests_no_replacement_value(self) -> None:
        _, msg = self.gamma.check_type_conformance("case:year", "==", "2018")
        self.assertIn("Only use values that are stated in the clause", msg)


class TestYearEntitiesE(unittest.TestCase):
    def test_year_must_appear_in_clause(self) -> None:
        bad = _ast(activation_attr="case:year", activation_op="==", activation_val="2017")
        ok, verdict, diag = verify_generic_numeric_entities(bad, CLAUSE, check_year_values=True)
        self.assertEqual((ok, verdict), (False, "THRESHOLD_MISMATCH"))
        self.assertIn("2018", diag)
        good = _ast(activation_attr="case:year", activation_op="==", activation_val="2018")
        self.assertTrue(verify_generic_numeric_entities(good, CLAUSE, check_year_values=True)[0])

    def test_no_year_in_clause_is_baseless(self) -> None:
        bad = _ast(activation_attr="case:year", activation_op="==", activation_val="2016")
        ok, verdict, _ = verify_generic_numeric_entities(bad, {"text": "Checks shall be made."},
                                                         check_year_values=True)
        self.assertEqual((ok, verdict), (False, "BASELESS"))

    def test_off_by_default(self) -> None:
        bad = _ast(activation_attr="case:year", activation_op="==", activation_val="2017")
        self.assertTrue(verify_generic_numeric_entities(bad, CLAUSE)[0])


class TestWitnessB(unittest.TestCase):
    def setUp(self) -> None:
        self.checker = LogGroundingChecker(_engine())

    def test_precedence_counts_target_side(self) -> None:
        self.assertEqual(self.checker.witness_cases(_ast()), 2)  # INIT ở c1, c2
        self.assertEqual(self.checker.witness_cases(_ast(activation_attr="case:year", activation_op="==",
                                                         activation_val="2016")), 1)
        self.assertEqual(self.checker.witness_cases(_ast(activation_attr="case:year", activation_op="==",
                                                         activation_val="2018")), 0)

    def test_combined_conditions_and_unary(self) -> None:
        resp = _ast(template_name="Response", activation_activity=INIT, target_activity=REF,
                    activation_attr="case:young farmer", activation_op="==", activation_val=True,
                    extra_conditions=[{"attr": "case:year", "op": "==", "val": "2015"}])
        self.assertEqual(self.checker.witness_cases(resp), 0)  # young farmer chỉ ở c2 (2016)
        exist = _ast(template_name="Existence", activation_activity=MAIL, target_activity=None)
        self.assertEqual(self.checker.witness_cases(exist), 1)
        self.assertEqual(self.checker.num_cases, 3)

    def test_feedback_wording(self) -> None:
        a = _ast(activation_attr="case:year", activation_op="==", activation_val="2018")
        msg = vacuity_feedback(a, 3, allow_no_constraint=True)
        self.assertIn(f"'{INIT}' with case:year == '2018'", msg)
        self.assertIn("no_constraint", msg)
        self.assertIn("violated by every case",
                      vacuity_feedback(_ast(template_name="Existence", target_activity=None), 3, False))


class TestObligationD(unittest.TestCase):
    def test_states(self) -> None:
        no = assess_obligation({"obligation_analysis": {"duty_bearer": "member_state_rules_or_systems",
                                                        "observable_in_log": False, "evidence": "e"},
                                "no_constraint": True})
        self.assertTrue(no.no_constraint)
        self.assertIsNone(assess_obligation({"template_name": "Existence"}).analysis)
        self.assertIn("Missing", assess_obligation({"template_name": "Existence"}).error)
        bad = assess_obligation({"obligation_analysis": {"duty_bearer": "king", "observable_in_log": True}})
        self.assertIn("duty_bearer", bad.error)
        clash = assess_obligation({"obligation_analysis": {**ANALYSIS_OK, "observable_in_log": True},
                                   "no_constraint": True})
        self.assertIsNotNone(clash.error)
        incons = assess_obligation(json.dumps({"obligation_analysis": {**ANALYSIS_OK, "duty_bearer": "commission"},
                                               **_ast()}))
        self.assertIn("inconsistency", incons.inconsistent)
        self.assertIsNone(assess_obligation("not json").error)  # để Tầng 1 báo lỗi JSON

    def test_profiles(self) -> None:
        self.assertTrue(CAP_PROFILE.abstain_enabled)
        self.assertFalse(CAP_PROFILE_NO_DUTY.abstain_enabled or BPIC2017_PROFILE.abstain_enabled)
        self.assertIn("obligation_analysis", CAP_PROFILE.generator_system)
        self.assertNotIn("obligation_analysis", CAP_PROFILE_NO_DUTY.generator_system)
        self.assertIn("set up or maintain systems", CAP_PROFILE.judge_context)


class ScriptedLLM:
    """Trả lần lượt các câu trả lời sinh; giám khảo luôn EQUIVALENT. Ghi lại phản hồi gửi cho LLM."""

    def __init__(self, outputs):
        self.outputs, self.feedback, self.calls = list(outputs), [], 0

    def chat_json(self, msgs, temperature=0.0, **_):
        if isinstance(msgs, list):
            if self.calls:  # từ lần gọi thứ hai, tin nhắn cuối là phản hồi của vòng lặp
                self.feedback.append(msgs[-1]["content"])
            self.calls += 1
            return json.dumps(self.outputs.pop(0))
        return {"verdict": "EQUIVALENT", "diagnostic_feedback": "ok"}


def _gen(**kw):
    return {"obligation_analysis": ANALYSIS_OK, **_ast(**kw)}


class TestLoopIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.checker = LogGroundingChecker(_engine())
        self.chunk = clause_only_chunk(CLAUSE)

    def _run(self, outputs, **kw):
        llm = ScriptedLLM(outputs)
        res = run_single_rule_with_real_llm({"rule_id": "t"}, self.chunk, GAMMA, llm, profile=CAP_PROFILE,
                                            grounding=self.checker, check_year_values=True, **kw)
        return res, [t["status"] for t in res["trajectory"]], llm

    def test_the_art70_case_is_caught_then_declined(self) -> None:
        res, statuses, llm = self._run([
            _gen(activation_attr="case:year", activation_op="==", activation_val="2018"),   # C: không có trong log
            _gen(activation_attr="case:year", activation_op="==", activation_val="2016"),   # E: không có trong luật
            {"article_id": "R9:Art70(2)", "no_constraint": True,
             "obligation_analysis": {"duty_bearer": "member_state_rules_or_systems", "observable_in_log": False,
                                     "evidence": "Member States shall ensure"}},
        ])
        self.assertEqual(statuses, ["FAILED_L1_L2", "FAILED_L3_ROUNDTRIP", "DECLINED_NO_OBLIGATION"])
        self.assertIn("Value Domain Violation", llm.feedback[0])
        self.assertIn("2018", llm.feedback[1])
        self.assertEqual(outcome_of(res), "BASELESS")
        self.assertEqual(res["obligation_analysis"]["duty_bearer"], "member_state_rules_or_systems")

    def test_vacuity_feedback_once_then_accept_with_flag(self) -> None:
        empty = _gen(template_name="Response", activation_activity=MAIL, target_activity=REF,
                     activation_attr="case:young farmer", activation_op="==", activation_val=True)
        res, statuses, llm = self._run([empty, empty])
        self.assertEqual(statuses, ["FAILED_VACUITY", "PASSED"])
        self.assertIn("[Log-grounded Vacuity]", llm.feedback[0])
        self.assertEqual(res["grounding"], {"witness_cases": 0, "num_cases": 3, "vacuous": True})
        grounded = _gen(template_name="Response", activation_activity=INIT, target_activity=REF,
                        activation_attr="case:young farmer", activation_op="==", activation_val=True)
        res, statuses, _ = self._run([grounded])
        self.assertEqual((statuses, res["grounding"]["vacuous"]), (["PASSED"], False))

    def test_duty_inconsistency_warned_once(self) -> None:
        clash = {**_gen(), "obligation_analysis": {**ANALYSIS_OK, "duty_bearer": "commission"}}
        res, statuses, _ = self._run([clash, clash])
        self.assertEqual(statuses, ["FAILED_OBLIGATION_CONSISTENCY", "PASSED"])
        self.assertEqual(outcome_of(res), "RULE")

    def test_missing_analysis_gets_feedback(self) -> None:
        _, statuses, llm = self._run([_ast(), _gen()])
        self.assertEqual(statuses, ["FAILED_OBLIGATION_ANALYSIS", "PASSED"])
        self.assertIn("obligation_analysis", llm.feedback[0])

    def test_default_profile_runs_no_new_checks(self) -> None:
        llm = ScriptedLLM([_ast(activation_attr="case:year", activation_op="==", activation_val="2016")])
        old_gamma = {**GAMMA, "case_attributes": {k: {"type": v["type"], "samples": v["samples"]}
                                                  for k, v in GAMMA["case_attributes"].items()}}
        res = run_single_rule_with_real_llm({"rule_id": "t"}, self.chunk, old_gamma, llm)
        self.assertEqual([t["status"] for t in res["trajectory"]], ["PASSED"])
        self.assertIsNone(res["grounding"])
        self.assertIsNone(res["obligation_analysis"])


class TestGenerationConfigs(unittest.TestCase):
    def test_ablation_switches(self) -> None:
        self.assertNotIn("domain", schema_for(GAMMA, "Y-noDomain")["case_attributes"]["case:year"])
        self.assertIn("domain", schema_for(GAMMA, "Y")["case_attributes"]["case:year"])
        self.assertEqual({c for c, v in CONFIGS.items() if not v["vacuity"]}, {"Y-noVac"})
        self.assertEqual({c for c, v in CONFIGS.items() if not v["duty"]}, {"Y-noDuty"})

    def test_noduty_config_uses_old_prompt(self) -> None:
        llm = ScriptedLLM([_ast()])  # không có obligation_analysis: hợp lệ khi tắt D
        rec = run_clause(CLAUSE, clause_only_chunk(CLAUSE), GAMMA, llm, "Y-noDuty")
        self.assertEqual(rec["outcome"], "RULE")
        self.assertIsNone(rec["obligation_analysis"])


class TestLegacyDiagnosticFixed(unittest.TestCase):
    """Bước 4 của run_generic_cegis_diagnostic (client kiểm thử BPIC2017) trước chỉ kiểm ngưỡng số."""

    LOG = pd.DataFrame({"case:concept:name": ["a", "a", "b"], "concept:name": [REF, INIT, INIT],
                        "case:year": ["2015", "2015", "2016"]})

    def test_string_condition_vacuity_detected(self) -> None:
        res = run_generic_cegis_diagnostic(_ast(activation_attr="case:year", activation_op="==",
                                                activation_val="2018"), {"text": "x"}, log_df=self.LOG)
        self.assertIn("[Diagnostic Vacuity]", res["diagnostic_feedback"])
        ok = run_generic_cegis_diagnostic(_ast(activation_attr="case:year", activation_op="==",
                                               activation_val="2016"), {"text": "x"}, log_df=self.LOG)
        self.assertEqual(ok["verdict"], "EQUIVALENT")

    def test_hardcoded_directive_branch_removed(self) -> None:
        src = (PROJECT_ROOT / "src" / "evaluation" / "experiment_runner.py").read_text(encoding="utf-8")
        self.assertNotIn("in clause_lower and not entities", src)

    def test_docstring_no_longer_overclaims(self) -> None:
        src = (PROJECT_ROOT / "src" / "evaluation" / "real_llm_client.py").read_text(encoding="utf-8")
        self.assertNotIn("Tầng 3 (Roundtrip & Vacuity) để đưa vào bài báo", src)


if __name__ == "__main__":
    unittest.main()
