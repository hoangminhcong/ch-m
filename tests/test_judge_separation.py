"""Giám khảo Tầng 3 có thể dùng model KHÁC bộ sinh (tránh tự chấm) — 2026-11-20. Mặc định: cùng client như trước."""

import argparse
import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

MAIL = "Payment application / Application / mail income"
PAY = "Payment application / Main / begin payment"
GAMMA = {"valid_activities": [MAIL, PAY], "activities_by_origin": {},
         "case_attributes": {"case:year": {"type": "String", "samples": []}},
         "event_attributes": {"time:timestamp": {"type": "Timestamp", "samples": []}}}
CLAUSE = {"node_id": "R9:Art1(1)", "round": 1, "text": "Payment shall follow the application."}
RULE = {"article_id": "R9:Art1(1)", "template_name": "Response", "activation_activity": MAIL,
        "target_activity": PAY, "activation_attr": None, "activation_op": None, "activation_val": None,
        "extra_conditions": [], "time_min": None, "time_max": None, "time_unit": None}


class Recorder:
    """Ghi lại câu hỏi sinh (danh sách message) và câu hỏi chấm (chuỗi prompt) mà client nhận."""

    def __init__(self, name):
        self.name, self.gen_calls, self.judge_calls = name, 0, 0

    def chat_json(self, msgs, temperature=0.0, **_):
        if isinstance(msgs, list):
            self.gen_calls += 1
            return json.dumps(RULE)
        self.judge_calls += 1
        return {"verdict": "EQUIVALENT", "diagnostic_feedback": "ok"}


def _run(judge=None):
    from src.evaluation.real_llm_client import run_single_rule_with_real_llm
    from src.neural.graph_context import clause_only_chunk
    from src.symbolic.domain_profiles import CAP_PROFILE_NO_DUTY
    gen = Recorder("gen")
    res = run_single_rule_with_real_llm({"rule_id": "t"}, clause_only_chunk(CLAUSE), GAMMA, gen,
                                        profile=CAP_PROFILE_NO_DUTY, **({"judge_llm": judge} if judge else {}))
    return res, gen


class TestJudgeSeparation(unittest.TestCase):
    def test_separate_judge_gets_only_judge_calls(self) -> None:
        judge = Recorder("judge")
        res, gen = _run(judge)
        self.assertEqual(res["trajectory"][-1]["status"], "PASSED")
        self.assertEqual((gen.gen_calls, gen.judge_calls), (1, 0))
        self.assertEqual((judge.gen_calls, judge.judge_calls), (0, 1))

    def test_default_uses_generator_as_judge(self) -> None:
        _, gen = _run()
        self.assertEqual((gen.gen_calls, gen.judge_calls), (1, 1))

    def test_resume_refuses_judge_change(self) -> None:
        from scripts.run_cap_generation import check_resume
        doc = {"model": "gpt-oss-120b", "provider": "cerebras", "judge_model": "other-model", "predictions": {"c": {}}}
        args = argparse.Namespace(dataset="cap", model="gpt-oss-120b", provider="cerebras", force=False,
                                  judge_provider=None, judge_model=None)
        with self.assertRaisesRegex(SystemExit, "judge_model"):
            check_resume(doc, args)

    def test_judge_cache_is_separate(self) -> None:
        from scripts.run_cap_generation import resolve_endpoint
        args = argparse.Namespace(provider="cerebras", base_url=None, model=None, cache_file=None,
                                  out_dir="results/x", config="Y", judge_provider="groq", judge_model=None)
        args = resolve_endpoint(args)
        self.assertTrue(args.judge_cache_file.endswith("llm_cache_Y_judge.json"))
        self.assertNotEqual(args.judge_cache_file, args.cache_file)


if __name__ == "__main__":
    unittest.main()
