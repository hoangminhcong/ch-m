"""
Rà soát kiểm thử 2026-11-20 (vai tester) — mỗi lỗi một test giữ bản sửa:
  1  time_max trên mẫu không có ngữ nghĩa thời hạn → Tầng 1 từ chối (engine / Cypher / bản diễn đạt bỏ qua; N3 bị qua mặt)
  2  chạy tiếp mà đổi giám khảo (file cũ không ghi judge_model) → dừng
  3  --force kèm --only / --limit với lần chạy khác → dừng; --force đủ khoản → được
  4  score_cap so cả model giám khảo giữa các file
  5  dấu code từng khoản; file lẫn phiên bản code → báo
  6  proof trace của Z đối chiếu cả định nghĩa / ghi chú phạm vi có trong prompt
  7  p-value rất nhỏ in '< 0.0001', không in 'p = 0'
  8  thứ bậc mẫu: Precedence(A,B) ⇒ Responded Existence(B,A); thời hạn ở mẫu phủ định đổi chiều mạnh / yếu
  9  (đã HOÀN TÁC) Entity Matcher vẫn kết luận BASELESS ngay khi khoản không có mốc số / ngày / năm nào
  10 llm_rounds = số vòng gọi LLM cho mọi kết cục
  11 phễu / nhãn REVIEW dừng khi gold thuộc bộ dữ liệu khác
  12 nhãn phễu không nói 'sửa đúng'
  13 TN7 chọn gold theo kappa; không in '-0.0'
  14 Tầng 2: activity tự lặp so theo tập thành viên
"""

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.cap_scoring import compare_ast, fmt_p, paired_comparison, paired_p  # noqa: E402
from src.mde.constraint_ast import TIMED_TEMPLATES, UNARY_TEMPLATES, validate_layer1_ast  # noqa: E402

A, B, C = "Doc / Main / create", "Doc / Main / decide", "Pay / Main / begin"


def _ast(**kw):
    base = {"article_id": "R1:Art1", "template_name": "Response", "activation_activity": A, "target_activity": B,
            "activation_attr": None, "activation_op": None, "activation_val": None, "extra_conditions": [],
            "time_min": 0, "time_max": None, "time_unit": "d"}
    return {**base, **kw}


def _unary(tpl, **kw):
    return _ast(template_name=tpl, target_activity=None, **kw)


class TestFix1TimeOnlyOnTimedTemplates(unittest.TestCase):
    def test_untimed_templates_reject_time_max(self) -> None:
        untimed = {"Existence", "Absence", "Init", "Exactly1", "Choice", "Exclusive Choice", "Not Co-Existence",
                   "Not Responded Existence"}
        for tpl in untimed:
            ast = _unary(tpl, time_max=30) if tpl in UNARY_TEMPLATES else _ast(template_name=tpl, time_max=30)
            with self.subTest(tpl=tpl):
                ok, msg = validate_layer1_ast(ast)
                self.assertFalse(ok)
                self.assertIn("no time semantics", str(msg))

    def test_timed_templates_keep_time_max(self) -> None:
        for tpl in TIMED_TEMPLATES:
            with self.subTest(tpl=tpl):
                self.assertTrue(validate_layer1_ast(_ast(template_name=tpl, time_max=30))[0])

    def test_timed_set_matches_engine_window_use(self) -> None:
        """Mẫu được giữ time_max đúng là mẫu engine dùng cửa sổ thời gian: cùng dữ liệu, có / không cửa sổ cho kết
        quả khác nhau."""
        import pandas as pd

        from src.symbolic.declare4py_verifier import Declare4Py
        ev = pd.DataFrame([{"case:concept:name": "c1", "concept:name": A, "time:timestamp": "2017-01-02T10:00:00Z"},
                           {"case:concept:name": "c1", "concept:name": B, "time:timestamp": "2017-03-02T10:00:00Z"}])
        eng = Declare4Py(ev, cases=pd.DataFrame([{"case:concept:name": "c1"}]))

        def state(line):
            c = eng.parse_decl_lines([line])[0]
            return [r.state for _, r, _ in eng.case_results(c)]
        for tpl in ("Response", "Responded Existence", "Precedence", "Not Response"):  # A rồi B, cách 2 tháng
            with self.subTest(tpl=tpl):
                self.assertNotEqual(state(f"{tpl}[{A}, {B}] | | | "), state(f"{tpl}[{A}, {B}] | | | 0,5,d"))

    def test_n3_cannot_be_satisfied_by_ignored_deadline(self) -> None:
        from src.mde.typing_environment import check_layer1_and_layer2
        schema = {"valid_activities": [A, B], "activities_by_origin": {}, "case_attributes": {}, "event_attributes": {}}
        ok, _ = check_layer1_and_layer2(_unary("Existence", time_max=30), schema, {"article_id": "R1:Art1"})
        self.assertFalse(ok)  # không đi tới N3 với một thời hạn mà engine bỏ qua


def _args(**kw):
    base = dict(dataset="cap", model="gpt-oss-120b", provider="cerebras", force=False, only=None, limit=None,
                judge_provider=None, judge_model=None)
    return argparse.Namespace(**{**base, **kw})


DOC = {"model": "gpt-oss-120b", "provider": "cerebras", "predictions": {"c": {}}}


class TestFix2And3Resume(unittest.TestCase):
    def test_adding_judge_on_resume_refused(self) -> None:
        from scripts.run_cap_generation import check_resume
        with self.assertRaisesRegex(SystemExit, "judge_model"):
            check_resume(DOC, _args(judge_provider="groq", judge_model="openai/gpt-oss-20b"))
        check_resume(DOC, _args())  # cùng giám khảo (chính bộ sinh) → được

    def test_partial_force_with_other_provider_refused(self) -> None:
        from scripts.run_cap_generation import check_resume
        for partial in ({"only": ["c"]}, {"limit": 3}):
            with self.subTest(partial=partial), self.assertRaisesRegex(SystemExit, "provider"):
                check_resume(DOC, _args(provider="groq", force=True, **partial))
        check_resume(DOC, _args(provider="groq", force=True))  # --force đủ khoản: chạy lại hết → được

    def test_partial_force_with_changed_data_refused(self) -> None:
        from scripts.run_cap_generation import check_resume
        doc = {**DOC, "inputs": {"clauses": "old"}}
        with self.assertRaisesRegex(SystemExit, "clauses"):
            check_resume(doc, _args(force=True, only=["c"]), {"clauses": "new"})
        check_resume(doc, _args(force=True), {"clauses": "new"})


class TestFix4And5MetaAndCode(unittest.TestCase):
    def test_mixed_judges_refused_by_score_cap(self) -> None:
        from scripts.score_cap import check_predictions
        result = {"configs": {"Y": {"missing_predictions": []}, "N": {"missing_predictions": []}}}
        meta = {"Y": ("cap", "m", "p", None), "N": ("cap", "m", "p", "judge-x")}
        with self.assertRaisesRegex(SystemExit, "giám khảo"):
            check_predictions(result, meta, allow_missing=False, allow_mixed=False)

    def test_prediction_meta_reads_judge(self) -> None:
        from scripts.score_cap import prediction_meta
        with tempfile.TemporaryDirectory() as d:
            Path(d, "predictions_Y.json").write_text(json.dumps({"model": "m", "provider": "p", "judge_model": "j",
                                                                 "predictions": {}}), encoding="utf-8")
            self.assertEqual(prediction_meta(Path(d))["Y"], ("cap", "m", "p", "j"))

    def test_code_mixture_within_file_reported(self) -> None:
        from src.evaluation.run_inputs import input_conflicts
        doc = {"code": {"sha256": "new"}, "inputs_id": "i",
               "predictions": {"a": {"inputs_id": "i", "code_sha": "old"}, "b": {"inputs_id": "i", "code_sha": "new"},
                               "c": {"inputs_id": "i"}}}  # c: sinh trước khi có dấu code → không tính
        self.assertEqual(input_conflicts({"Y": doc})["code_within"], {"Y": 1})


class TestFix6PromptExtras(unittest.TestCase):
    def test_definition_quote_is_supported(self) -> None:
        from src.evaluation.proof_trace import build_traces
        quote = "a natural or legal person whose holding is situated within the territory"
        graph = {"nodes": [{"id": "R1:Art1", "label": "Paragraph", "props": {"text": "Farmers shall declare parcels."}}],
                 "edges": [], "scope_notes": {},
                 "definitions": {"R1:Art1": [{"term": "farmer", "source": "R1:Art4", "definition": quote}]}}
        pred = {"outcome": "RULE", "ast": _ast(), "definitions": ["farmer"],
                "obligation_analysis": {"evidence": quote}, "trajectory": []}
        trace = build_traces({"predictions": {"R1:Art1": pred}}, graph)[0]
        self.assertEqual(trace["evidence"]["level"], "verbatim")
        self.assertEqual(trace["prompt_extras"], 1)
        y_pred = {k: v for k, v in pred.items() if k != "definitions"}  # Y: prompt không có định nghĩa
        self.assertEqual(build_traces({"predictions": {"R1:Art1": y_pred}}, graph)[0]["evidence"]["level"],
                         "unsupported")


class TestFix7PValue(unittest.TestCase):
    def test_tiny_p_not_printed_as_zero(self) -> None:
        pc = paired_comparison({"per_clause": {str(i): "TRAP_DETECTED" for i in range(40)}},
                               {"per_clause": {str(i): "TRAP_FALSE_RULE" for i in range(40)}})
        self.assertEqual(pc["p_value"], 0.0)  # khoá cũ giữ nguyên (tương thích)
        self.assertGreater(pc["p_exact"], 0.0)
        self.assertEqual(paired_p(pc), "< 0.0001")
        self.assertEqual(fmt_p(0.5), "0.5000")
        self.assertEqual(paired_p({"p_value": 0.0238}), "0.0238")  # file cũ chưa có p_exact


class TestFix8Hierarchy(unittest.TestCase):
    def test_precedence_implies_responded_existence_reversed(self) -> None:
        prec = _ast(template_name="Precedence")  # B chỉ khi trước đó có A
        re_ba = _ast(template_name="Responded Existence", activation_activity=B, target_activity=A)
        re_ab = _ast(template_name="Responded Existence")
        self.assertEqual(compare_ast(re_ba, prec), "WEAKENED")
        self.assertEqual(compare_ast(prec, re_ba), "STRENGTHENED")
        self.assertEqual(compare_ast(re_ab, prec), "MISMATCH")  # trước đây: WEAKENED (sai chiều)

    def test_negative_template_deadline_direction(self) -> None:
        no_time, five = _ast(template_name="Not Response"), _ast(template_name="Not Response", time_max=5)
        self.assertEqual(compare_ast(five, no_time), "WEAKENED")  # cấm trong 5 ngày < cấm mãi mãi
        self.assertEqual(compare_ast(no_time, five), "STRENGTHENED")
        self.assertEqual(compare_ast(_ast(time_max=5), _ast()), "STRENGTHENED")  # khẳng định: như cũ
        self.assertEqual(compare_ast(_ast(template_name="Not Response", time_max=3), five), "WEAKENED")


class TestFix9EntityMatcherBaselessKept(unittest.TestCase):
    """Lỗi 9 đã sửa rồi HOÀN TÁC (người dùng: "hoàn tác lỗi 9"): phát lại cache v1.2 cho thấy cả 4 khoản bị đổi đều là
    bẫy / không chấm và hành vi cũ (BASELESS ngay) là đúng ở cả 4. Test giữ quyết định này."""
    CHUNK = {"article_id": "R1:Art1", "text": "Member States shall verify the applications."}

    def test_number_without_any_anchor_is_baseless_for_every_profile(self) -> None:
        from src.evaluation.real_llm_client import is_baseless_message
        from src.symbolic.domain_profiles import BPIC2017_PROFILE, CAP_PROFILE, CAP_PROFILE_NO_DUTY, CAP_PROFILE_NORM
        from src.symbolic.verbalizer_roundtrip import check_roundtrip_fidelity
        judge = mock.Mock()
        for prof in (CAP_PROFILE, CAP_PROFILE_NO_DUTY, CAP_PROFILE_NORM, BPIC2017_PROFILE):
            with self.subTest(profile=prof.name):
                ok, msg = check_roundtrip_fidelity(_ast(time_max=30), self.CHUNK, judge, profile=prof)
                self.assertFalse(ok)
                self.assertTrue(is_baseless_message(msg))
        judge.chat_json.assert_not_called()  # Entity Matcher kết luận trước giám khảo


class TestFix10LlmRounds(unittest.TestCase):
    def test_row_counts_llm_rounds_for_every_outcome(self) -> None:
        import scripts.run_cap_generation as gen
        traj = [{"round": 1, "status": "FAILED_L1_L2"}, {"round": 2, "status": "FAILED_L1_L2"}]
        fake = {"final_ast": None, "rounds_needed": 2, "trajectory": traj, "roundtrip_ok": False, "roundtrip_msg": "x"}
        ctx = {"text": "t", "context_refs": [], "skipped_refs": [], "truncated_chars": 0}
        gamma = {"case_attributes": {}, "event_attributes": {}, "valid_activities": []}
        with mock.patch.object(gen, "run_single_rule_with_real_llm", return_value=fake):
            row = gen.run_clause({"node_id": "R1:Art1"}, ctx, gamma, None, "X")
        self.assertEqual((row["outcome"], row["llm_rounds"]), ("FAILED", 2))


class TestFix11GoldMatchesDataset(unittest.TestCase):
    def test_foreign_gold_refused(self) -> None:
        from src.evaluation.cap_gold import check_gold_matches
        with self.assertRaisesRegex(SystemExit, "--gold"):
            check_gold_matches(["R1:Art1", "R1:Art2"], ["DE-InVeKoSV:§7(1)", "DE-InVeKoSV:§8"], "cap_gold.json")
        check_gold_matches(["R1:Art1", "R1:Art2"], ["R1:Art1", "R1:Art2"], "cap_gold.json")
        check_gold_matches([], ["x"], "g")  # không có gold → không xét


class TestFix12And13Labels(unittest.TestCase):
    def test_funnel_label_does_not_claim_correctness(self) -> None:
        from src.evaluation.verification_funnel import markdown_table
        row = {"rounds_by_status": {}, "llm_rounds": 0, "rejected_rounds": 0, "rules_fixed_after_rejection": 0,
               "final_rules_not_passed": 0}
        self.assertNotIn("sửa đúng", markdown_table({"Y": row}))

    def test_best_gold_by_kappa_and_no_negative_zero(self) -> None:
        from src.evaluation.cap_conformance import best_gold_match, cohen_kappa
        v, s = "Violated", "Satisfied"
        # agreement: g_rare 0,85 > g_like 0,80; kappa: g_like 0,545 > g_rare 0,348 → phải chọn g_like
        states = {"g_rare": [v] + [s] * 19, "g_like": [v] * 8 + [s] * 12, "p": [v] * 4 + [s] * 16}
        self.assertEqual(best_gold_match(["g_rare", "g_like"], "p", states)["gold_line"], "g_like")
        self.assertEqual(str(cohen_kappa(0, 4, 1, 43804)), "0.0")  # ca thật TN7 (X, R1307:Art32(1)) từng in '-0.0'


class TestFix14SelfLoopBySet(unittest.TestCase):
    def test_overlapping_groups_rejected(self) -> None:
        from src.mde.typing_environment import check_layer1_and_layer2
        schema = {"valid_activities": [A, B, C], "activities_by_origin": {}, "case_attributes": {},
                  "event_attributes": {}}
        chunk = {"article_id": "R1:Art1"}
        for act, tgt in ((f"{{{A} | {B}}}", f"{{{B} | {A}}}"), (f"{{{A} | {B}}}", f"{{{B} | {C}}}"), (A, A)):
            with self.subTest(act=act, tgt=tgt):
                ok, msg = check_layer1_and_layer2(_ast(activation_activity=act, target_activity=tgt), schema, chunk)
                self.assertFalse(ok)
                self.assertIn("Self-Loop", str(msg))
        self.assertTrue(check_layer1_and_layer2(_ast(activation_activity=f"{{{A} | {C}}}"), schema, chunk)[0])


if __name__ == "__main__":
    unittest.main()
