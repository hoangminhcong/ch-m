"""
v2 (docs/V2_DANG_KY_TRUOC.md mục 3–4): các kiểm dựa trên hồ sơ tầng Tiến trình, chạy trong vòng lặp sinh khi bật.
  - gợi ý nhóm activity theo năm (cùng bước / loại giấy tờ thay thế theo năm);
  - thuộc tính event phải có trên activity mang điều kiện (HAS_ATTRIBUTE);
  - vi phạm hàng loạt (> 20% số hồ sơ có kích hoạt) → phản hồi kèm ≤ 2 hồ sơ phản ví dụ;
  - ghi chú activity cho giám khảo Tầng 3.
Log nhỏ tổng hợp; không gọi API, không đọc gold.
"""

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.symbolic.declare4py_verifier import Declare4Py  # noqa: E402
from src.symbolic.process_checks import (  # noqa: E402
    MASS_VIOLATION_THRESHOLD,
    MassViolationChecker,
    activity_notes,
    event_attribute_error,
    year_group_feedback,
)

PARCEL = "Parcel document / Main / initialize"
GEO = "Geo parcel document / Declared / create"
MAIL = "Payment application / Application / mail income"
PAY = "Payment application / Application / begin payment"


def _act(doctype, years, same_step=(), attrs=("note",), **kw):
    return {"doctype": doctype, "subprocess": "", "action": "", "years": list(years), "case_count": 1,
            "case_ratio": 0.5, "roles": {"automated": 1.0, "staff": 0.0, "unknown": 0.0},
            "predecessors": [], "successors": [], "event_attributes": list(attrs), "same_step": list(same_step), **kw}


PROFILE = {"years": [2015, 2016, 2017], "num_cases": 4,
           "doctype_years": {"Parcel document": [2015], "Geo parcel document": [2016, 2017],
                             "Payment application": [2015, 2016, 2017]},
           "doctype_replacements": {"Parcel document": ["Geo parcel document"],
                                    "Geo parcel document": ["Parcel document"]},
           "activities": {PARCEL: _act("Parcel document", [2015]), GEO: _act("Geo parcel document", [2016, 2017]),
                          MAIL: _act("Payment application", [2015, 2016, 2017], attrs=("note", "success")),
                          PAY: _act("Payment application", [2015, 2016, 2017], attrs=("note",))}}


def _ast(template="Existence", a=GEO, b=None, **kw):
    return {"article_id": "R9:Art1(1)", "template_name": template, "activation_activity": a, "target_activity": b,
            "activation_attr": None, "activation_op": None, "activation_val": None, "extra_conditions": [],
            "time_min": None, "time_max": None, "time_unit": None, **kw}


class TestYearGroupFeedback(unittest.TestCase):
    def test_partial_year_activity_with_replacement_gets_hint(self) -> None:
        msg = year_group_feedback(_ast(a=GEO), PROFILE)
        self.assertIn("2016, 2017", msg)
        self.assertIn("Parcel document", msg)
        self.assertIn("{", msg)  # nhắc cú pháp nhóm

    def test_group_covering_all_years_is_silent(self) -> None:
        self.assertIsNone(year_group_feedback(_ast(a="{" + f"{GEO} | {PARCEL}" + "}"), PROFILE))

    def test_all_year_activity_is_silent(self) -> None:
        self.assertIsNone(year_group_feedback(_ast("Response", MAIL, PAY), PROFILE))

    def test_partial_without_replacement_is_silent(self) -> None:
        """Activity chỉ có ở một phần các năm nhưng không có gì thay thế: có thể đúng là luật chỉ áp năm đó."""
        prof = {**PROFILE, "doctype_replacements": {}}
        self.assertIsNone(year_group_feedback(_ast(a=GEO), prof))

    def test_target_side_checked_too(self) -> None:
        self.assertIsNotNone(year_group_feedback(_ast("Response", MAIL, PARCEL), PROFILE))


class TestYearScopedClauses(unittest.TestCase):
    """Rà soát 2026-11-18 HIGH-3: khoản chỉ áp năm 2016 không được gợi ý mở rộng sang 2015/2017."""

    def test_no_year_hint_when_activity_covers_clause_years(self) -> None:
        self.assertIsNone(year_group_feedback(_ast(a=GEO), PROFILE, years=[2016]))
        self.assertIsNotNone(year_group_feedback(_ast(a=GEO), PROFILE, years=[2015, 2016]))
        self.assertIsNotNone(year_group_feedback(_ast(a=GEO), PROFILE))  # không có years: như cũ

    def test_notes_restricted_to_clause_years(self) -> None:
        notes = activity_notes(_ast(a=MAIL), PROFILE, years=[2016])
        self.assertIn("recorded in years 2016;", notes)
        self.assertNotIn("2015", notes)


class TestEventAttribute(unittest.TestCase):
    def test_condition_on_attribute_missing_on_activity(self) -> None:
        err = event_attribute_error(_ast(a=PAY, activation_attr="success", activation_op="==",
                                         activation_val=True), PROFILE)
        self.assertIn("success", err)

    def test_condition_on_present_or_case_attribute_ok(self) -> None:
        self.assertIsNone(event_attribute_error(_ast(a=MAIL, activation_attr="success", activation_op="==",
                                                     activation_val=True), PROFILE))
        self.assertIsNone(event_attribute_error(_ast(a=PAY, activation_attr="case:year", activation_op="==",
                                                     activation_val=2016), PROFILE))
        self.assertIsNone(event_attribute_error(
            _ast(a=PAY, extra_conditions=[{"attr": "date", "op": "<=", "val": "year-05-15"}]), PROFILE))

    def test_precedence_condition_checked_on_target(self) -> None:
        ast = _ast("Precedence", PAY, MAIL, activation_attr="success", activation_op="==", activation_val=True)
        self.assertIsNone(event_attribute_error(ast, PROFILE))


def _engine() -> Declare4Py:
    rows = []
    for case, seq in (("c1", [MAIL, PAY]), ("c2", [MAIL]), ("c3", [MAIL]), ("c4", [MAIL])):
        for i, act in enumerate(seq):
            rows.append({"case:concept:name": case, "concept:name": act,
                         "time:timestamp": pd.Timestamp(f"2016-03-0{i + 1}", tz="UTC")})
    cases = pd.DataFrame({"case:concept:name": ["c1", "c2", "c3", "c4"], "case:year": [2016] * 4})
    return Declare4Py(pd.DataFrame(rows), cases=cases, timezone="Europe/Berlin", calendar_periods=True)


class TestMassViolation(unittest.TestCase):
    def test_threshold_is_preregistered_value(self) -> None:
        self.assertEqual(MASS_VIOLATION_THRESHOLD, 0.20)

    def test_mass_violation_detected_with_counterexamples(self) -> None:
        checker = MassViolationChecker(_engine())
        rec = checker.assess(_ast("Response", MAIL, PAY))
        self.assertEqual((rec["activated"], rec["violated"]), (4, 3))
        self.assertTrue(rec["mass_violation"])
        self.assertEqual([e["case"] for e in rec["examples"]], ["c2", "c3"])
        msg = checker.feedback(_ast("Response", MAIL, PAY), rec)
        self.assertIn("3 of 4", msg)
        self.assertIn("c2", msg)
        self.assertIn(MAIL, msg)

    def test_rarely_violated_rule_passes(self) -> None:
        rec = MassViolationChecker(_engine()).assess(_ast("Existence", MAIL))
        self.assertEqual(rec["violated"], 0)
        self.assertFalse(rec["mass_violation"])

    def test_never_activated_not_flagged(self) -> None:
        """0 hồ sơ kích hoạt là việc của kiểm rỗng B, không phải vi phạm hàng loạt."""
        rec = MassViolationChecker(_engine()).assess(_ast("Response", PAY, MAIL, activation_attr="case:year",
                                                          activation_op="==", activation_val=2099))
        self.assertEqual(rec["activated"], 0)
        self.assertFalse(rec["mass_violation"])


class TestActivityNotes(unittest.TestCase):
    def test_notes_describe_each_activity(self) -> None:
        notes = activity_notes(_ast("Response", MAIL, GEO), PROFILE)
        self.assertIn(MAIL, notes)
        self.assertIn("Geo parcel document", notes)
        self.assertIn("2016, 2017", notes)
        self.assertIn("automated", notes)

    def test_ontology_meaning_used_only_when_approved(self) -> None:
        onto = {"status": "approved", "doctypes": {"Geo parcel document": {"meaning": "parcel declaration"}}}
        self.assertIn("parcel declaration", activity_notes(_ast(a=GEO), PROFILE, onto))
        self.assertNotIn("parcel declaration", activity_notes(_ast(a=GEO), PROFILE, {**onto, "status": "draft"}))


GAMMA = {"valid_activities": [MAIL, PAY, GEO, PARCEL], "activities_by_origin": {},
         "case_attributes": {"case:year": {"type": "String", "samples": []}},
         "event_attributes": {"time:timestamp": {"type": "Timestamp", "samples": []}}}
CLAUSE = {"node_id": "R9:Art1(1)", "round": 1, "text": "Payment shall follow the application."}


class ScriptedLLM:
    """Sinh: trả lần lượt; giám khảo: EQUIVALENT và ghi lại prompt (kiểm ghi chú activity)."""

    def __init__(self, outputs):
        self.outputs, self.feedback, self.judge_prompts, self.calls = list(outputs), [], [], 0

    def chat_json(self, msgs, temperature=0.0, **_):
        import json
        if isinstance(msgs, list):
            if self.calls:
                self.feedback.append(msgs[-1]["content"])
            self.calls += 1
            self.first_query = self.first_query if self.calls > 1 else msgs[-1]["content"]
            return json.dumps(self.outputs.pop(0))
        self.judge_prompts.append(msgs)
        return {"verdict": "EQUIVALENT", "diagnostic_feedback": "ok"}


class TestLoopV2(unittest.TestCase):
    def _run(self, outputs, process, hint=""):
        from src.evaluation.real_llm_client import run_single_rule_with_real_llm
        from src.neural.graph_context import clause_only_chunk
        from src.symbolic.domain_profiles import CAP_PROFILE_NO_DUTY
        llm = ScriptedLLM(outputs)
        res = run_single_rule_with_real_llm({"rule_id": "t"}, clause_only_chunk(CLAUSE), GAMMA, llm,
                                            profile=CAP_PROFILE_NO_DUTY, process=process, generation_hint=hint)
        return res, [t["status"] for t in res["trajectory"]], llm

    def test_mass_violation_feedback_once_then_accept_with_flag(self) -> None:
        from src.symbolic.process_checks import ProcessV2
        rule = _ast("Response", MAIL, PAY, time_min=0, time_unit="d")
        res, statuses, llm = self._run([rule, rule], ProcessV2(PROFILE, MassViolationChecker(_engine())))
        self.assertEqual(statuses, ["FAILED_MASS_VIOLATION", "PASSED"])
        self.assertIn("[Log-grounded Mass Violation]", llm.feedback[0])
        self.assertEqual(res["process_checks"]["mass_violation"]["ratio"], 0.75)
        self.assertIn("Process model notes", llm.judge_prompts[0])

    def test_year_hint_then_group_passes(self) -> None:
        from src.symbolic.process_checks import ProcessV2
        group = "{" + f"{GEO} | {PARCEL}" + "}"
        res, statuses, llm = self._run([_ast(a=GEO), _ast(a=group)], ProcessV2(PROFILE))
        self.assertEqual(statuses, ["FAILED_YEAR_COVERAGE", "PASSED"])
        self.assertIn("[Year Coverage]", llm.feedback[0])

    def test_generation_hint_appended_to_final_query_only(self) -> None:
        from src.symbolic.process_checks import ProcessV2
        _, _, llm = self._run([_ast(a=MAIL)], ProcessV2(PROFILE), hint="Knowledge-graph note: X.")
        self.assertTrue(llm.first_query.endswith("Knowledge-graph note: X."))
        self.assertNotIn("Knowledge-graph note", llm.judge_prompts[0])

    def test_record_reflects_last_round_only(self) -> None:
        """Rà soát MEDIUM-3: vòng 1 bị vi phạm hàng loạt, vòng 2 đổi luật → bản ghi là của luật cuối."""
        from src.symbolic.process_checks import ProcessV2
        bad = _ast("Response", MAIL, PAY, time_min=0, time_unit="d")
        good = _ast("Existence", MAIL)
        res, statuses, _ = self._run([bad, good], ProcessV2(PROFILE, MassViolationChecker(_engine())))
        self.assertEqual(statuses, ["FAILED_MASS_VIOLATION", "PASSED"])
        self.assertEqual(res["process_checks"]["mass_violation"]["violated"], 0)

    def test_year_scoped_clause_gets_no_cross_year_hint(self) -> None:
        from src.evaluation.real_llm_client import run_single_rule_with_real_llm
        from src.neural.graph_context import clause_only_chunk
        from src.symbolic.domain_profiles import CAP_PROFILE_NO_DUTY
        from src.symbolic.process_checks import ProcessV2
        llm = ScriptedLLM([_ast(a=GEO)])
        res = run_single_rule_with_real_llm({"rule_id": "t"}, clause_only_chunk({**CLAUSE, "years": [2016]}), GAMMA,
                                            llm, profile=CAP_PROFILE_NO_DUTY, process=ProcessV2(PROFILE))
        self.assertEqual([t["status"] for t in res["trajectory"]], ["PASSED"])
        self.assertIn("recorded in years 2016;", llm.judge_prompts[0])

    def test_without_process_v1_result_unchanged(self) -> None:
        res, statuses, llm = self._run([_ast("Response", MAIL, PAY, time_min=0, time_unit="d")], None)
        self.assertEqual(statuses, ["PASSED"])
        self.assertNotIn("process_checks", res)
        self.assertNotIn("Process model notes", llm.judge_prompts[0])


class TestZAblations(unittest.TestCase):
    def test_each_ablation_turns_off_exactly_one_group(self) -> None:
        from scripts.run_cap_generation import CONFIGS, V2_PARTS
        z = CONFIGS["Z"]
        self.assertTrue(all(z[p] for p in V2_PARTS))
        for name, part in (("Z-noLegal", "v2_legal"), ("Z-noProcess", "v2_process"), ("Z-noMass", "v2_mass"),
                           ("Z-noNotes", "v2_notes"), ("Z-noHint", "v2_hint")):
            with self.subTest(name=name):
                cfg = CONFIGS[name]
                self.assertEqual({p for p in V2_PARTS if not cfg[p]}, {part})
                self.assertEqual({k: v for k, v in cfg.items() if not k.startswith("v2")},
                                 {k: v for k, v in z.items() if not k.startswith("v2")})

    def test_process_flags_respected_in_loop(self) -> None:
        from src.symbolic.process_checks import ProcessV2
        rule = _ast("Response", MAIL, PAY, time_min=0, time_unit="d")
        no_mass = ProcessV2(PROFILE, MassViolationChecker(_engine()), check_mass=False)
        res, statuses, _ = TestLoopV2()._run([rule], no_mass)
        self.assertEqual(statuses, ["PASSED"])
        no_year = ProcessV2(PROFILE, check_year=False)
        _, statuses, _ = TestLoopV2()._run([_ast(a=GEO)], no_year)
        self.assertEqual(statuses, ["PASSED"])
        no_notes = ProcessV2(PROFILE, judge_notes=False)
        _, _, llm = TestLoopV2()._run([_ast(a=MAIL)], no_notes)
        self.assertNotIn("Process model notes", llm.judge_prompts[0])


class TestConfigZ(unittest.TestCase):
    def test_z_rows_carry_v2_fields_and_v1_rows_do_not(self) -> None:
        from scripts.run_cap_generation import CONFIGS, run_clause
        from src.neural.graph_context import clause_only_chunk
        from src.symbolic.process_checks import ProcessV2
        self.assertTrue(CONFIGS["Z"]["v2"] and CONFIGS["Z"]["graph"])
        # R = đường cơ sở RAG của đăng ký bổ sung B4 (2026-11-19) — không thuộc v1, nhưng cũng không bật v2
        # N = khung chuẩn tắc của đăng ký bổ sung B6 (2026-11-20) — cũng không thuộc v1, không bật v2
        v1 = [k for k in CONFIGS if not k.startswith("Z") and k not in ("R", "N")]
        self.assertEqual(set(v1), {"X", "Y", "Y-noL12", "Y-noL3", "Y-retry1", "Y-noVac", "Y-noDomain", "Y-noDuty"})
        self.assertFalse(any(CONFIGS[k].get("v2") for k in [*v1, "R"]))  # v1 đóng băng: không cấu hình v1 nào bật v2
        gen = {"obligation_analysis": {"duty_bearer": "applicant", "observable_in_log": True,
                                       "evidence": "Payment shall follow the application."}, **_ast(a=MAIL)}
        z = run_clause(CLAUSE, clause_only_chunk(CLAUSE), GAMMA, ScriptedLLM([gen]), "Z", None, ProcessV2(PROFILE))
        self.assertIn("process_checks", z)
        self.assertEqual(z["doctype_hint"], False)
        y = run_clause(CLAUSE, clause_only_chunk(CLAUSE), GAMMA, ScriptedLLM([gen]), "Y", None, ProcessV2(PROFILE))
        self.assertNotIn("process_checks", y)


if __name__ == "__main__":
    unittest.main()
