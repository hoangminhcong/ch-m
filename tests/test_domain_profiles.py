"""
Hồ sơ miền (domain profile) cho prompt sinh ràng buộc và prompt trọng tài Tầng 3.

- BPIC2017 (mặc định): prompt phải GIỐNG HỆT từng byte bản trước khi có profile
  (fixture tests/fixtures/bpic2017_prompts_snapshot.json chụp từ code cũ) — giữ kết quả TN5/TN6 và cache LLM.
- CAP: ngữ cảnh luật nông nghiệp EU, cú pháp extra_conditions / date; ví dụ few-shot là miền giả định
  (thư viện), không trùng câu nào trong phiếu CAP; không rò mô tả gold.
"""

import json
import sys
import unittest
from pathlib import Path
from typing import Any, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.real_llm_client import run_single_rule_with_real_llm  # noqa: E402
from src.mde.typing_environment import check_layer1_and_layer2  # noqa: E402
from src.symbolic.domain_profiles import BPIC2017_PROFILE, CAP_PROFILE  # noqa: E402
from src.symbolic.obligation_gate import assess_obligation  # noqa: E402
from src.symbolic.verbalizer_roundtrip import (  # noqa: E402
    check_roundtrip_fidelity,
    verify_generic_numeric_entities,
)

SNAPSHOT = PROJECT_ROOT / "tests" / "fixtures" / "bpic2017_prompts_snapshot.json"
SCHEMA_2017 = PROJECT_ROOT / "data" / "processed" / "process_schema.json"
GOLD_MARKER = "GOLDMARKER_5519"
MAIL = "Payment application / Application / mail income"
CAP_SCHEMA = {
    "valid_activities": [MAIL, "Payment application / Application / begin payment"],
    "activities_by_origin": {"Payment application": [MAIL, "Payment application / Application / begin payment"]},
    "case_attributes": {
        "case:year": {"type": "String", "samples": ["2015", "2016"]},
        "case:young farmer": {"type": "Boolean", "samples": ["False", "True"]},
        "case:area": {"type": "Float", "samples": [0.0, 576.07]},
    },
    "event_attributes": {"time:timestamp": {"type": "Timestamp", "samples": []},
                         "success": {"type": "Boolean", "samples": ["False", "True"]}},
}
CAP_CHUNK = {"article_id": "R809:Art13(1)", "article_title": "Final date for submission",
             "text": "1. Member States shall fix the final dates by which the single application shall be "
                     "submitted. The final dates shall not be later than 15 May each year."}
CAP_AST = {"article_id": "R809:Art13(1)", "template_name": "Existence", "activation_activity": MAIL,
           "target_activity": None, "activation_attr": "date", "activation_op": "<=",
           "activation_val": "year-05-15", "extra_conditions": [], "time_min": None, "time_max": None,
           "time_unit": None}
# Cụm từ chỉ có thể đến từ phiếu CAP / log BPIC2018 — không được xuất hiện trong ví dụ few-shot
CAP_SPECIFIC = ["May", "December", "June", "young farmer", "hectare", "Payment application",
                "R1306", "R1307", "R640", "R809", "single application", "paying agency"]


class RecordingLLM:
    def __init__(self, ast: dict) -> None:
        self.ast = ast
        self.calls: List[Any] = []

    def chat_json(self, prompt_or_messages: Any, temperature: float = 0.0, **_: Any) -> Any:
        self.calls.append(prompt_or_messages)
        if isinstance(prompt_or_messages, list):
            return json.dumps(self.ast)
        return {"verdict": "EQUIVALENT", "diagnostic_feedback": "ok"}

    def text(self) -> str:
        return "\n".join(m["content"] if isinstance(m, dict) else str(m)
                         for c in self.calls for m in (c if isinstance(c, list) else [c]))


from src.datasets import skip_unless_bpic2017  # noqa: E402  (bộ BPIC2017 đang tạm vô hiệu)


@skip_unless_bpic2017
@unittest.skipUnless(SNAPSHOT.exists() and SCHEMA_2017.exists(), "cần fixture snapshot và process_schema.json")
class TestBPIC2017PromptsByteIdentical(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA_2017.read_text(encoding="utf-8"))

    def _calls(self, ast: dict, **kw: Any) -> List[Any]:
        llm = RecordingLLM(ast)
        run_single_rule_with_real_llm({"rule_id": "R99"}, self.snap["chunk"], self.schema, llm, max_retry=1, **kw)
        return llm.calls

    def test_default_profile_unchanged(self) -> None:
        for run in self.snap["runs"]:
            with self.subTest(template=run["ast"]["template_name"]):
                self.assertEqual(self._calls(run["ast"]), run["calls"])

    def test_explicit_bpic2017_profile_unchanged(self) -> None:
        for run in self.snap["runs"]:
            self.assertEqual(self._calls(run["ast"], profile=BPIC2017_PROFILE), run["calls"])


CAP_ANALYSIS = {"duty_bearer": "applicant", "observable_in_log": True,
                "evidence": "single application shall be submitted"}


class TestCAPGenerationPrompt(unittest.TestCase):
    def setUp(self) -> None:
        # CAP_PROFILE bật kiểm D: câu trả lời phải có obligation_analysis trước ràng buộc
        self.llm = RecordingLLM({"article_id": CAP_AST["article_id"], "obligation_analysis": CAP_ANALYSIS,
                                 **{k: v for k, v in CAP_AST.items() if k != "article_id"}})
        rule_item = {"rule_id": "C01", "description": GOLD_MARKER}
        self.result = run_single_rule_with_real_llm(rule_item, CAP_CHUNK, CAP_SCHEMA, self.llm, max_retry=1,
                                                    profile=CAP_PROFILE)
        self.messages = self.llm.calls[0]

    def test_runs_end_to_end(self) -> None:
        self.assertEqual(self.result["trajectory"][-1]["status"], "PASSED", self.result["trajectory"])

    def test_system_prompt_describes_cap_and_new_syntax(self) -> None:
        system = self.messages[0]["content"]
        self.assertIn("Common Agricultural Policy", system)
        self.assertIn("extra_conditions", system)
        self.assertIn("year-MM-DD", system)
        self.assertNotIn("2008/48/EC", system)

    def test_query_lists_attribute_types(self) -> None:
        query = self.messages[-1]["content"]
        self.assertIn("Regulation Clause (R809:Art13(1))", query)
        self.assertIn("case:young farmer (Boolean)", query)
        self.assertIn(MAIL, query)

    def test_no_gold_in_any_prompt(self) -> None:
        self.assertNotIn(GOLD_MARKER, self.llm.text())

    def test_few_shot_examples_do_not_mirror_cap_sheet(self) -> None:
        few_shot = "\n".join(m["content"] for m in self.messages[1:-1])
        self.assertEqual([p for p in CAP_SPECIFIC if p in few_shot], [])


class TestCAPFewShotExamplesAreValid(unittest.TestCase):
    """Ví dụ few-shot phải tự qua Tầng 1–2 và Entity Matcher (không dạy LLM một mẫu sai)."""

    def test_each_example_passes_layers(self) -> None:
        for ex in CAP_PROFILE.examples:
            with self.subTest(clause=ex.clause_id):
                decision = assess_obligation(dict(ex.answer))
                self.assertIsNone(decision.error, decision.error)
                self.assertIsNone(decision.inconsistent, decision.inconsistent)
                if decision.no_constraint:  # ví dụ "không có nghĩa vụ quan sát được": không có AST để kiểm tầng
                    continue
                schema = {"valid_activities": list(ex.activities), "activities_by_origin": {},
                          "case_attributes": {a: {"type": t, "samples": []} for a, t in ex.case_attributes},
                          "event_attributes": {a: {"type": t, "samples": []} for a, t in ex.event_attributes}}
                chunk = {"article_id": ex.clause_id, "text": ex.clause_text}
                ok, res = check_layer1_and_layer2(dict(ex.answer), schema, chunk)
                self.assertTrue(ok, res)
                ok_num, _, diag = verify_generic_numeric_entities(dict(ex.answer), chunk)
                self.assertTrue(ok_num, diag)


class TestCAPJudgePrompt(unittest.TestCase):
    def setUp(self) -> None:
        self.llm = RecordingLLM(CAP_AST)
        self.ok, _ = check_roundtrip_fidelity(CAP_AST, CAP_CHUNK, self.llm, profile=CAP_PROFILE)
        self.prompt = self.llm.calls[-1]

    def test_cap_context_not_consumer_credit(self) -> None:
        self.assertTrue(self.ok)
        self.assertIn("Common Agricultural Policy", self.prompt)
        self.assertNotIn("2008/48/EC", self.prompt)
        self.assertNotIn("credit case", self.prompt)

    def test_back_translation_uses_cap_case_noun(self) -> None:
        self.assertIn("in the application case", self.prompt)
        self.assertIn("date <= year-05-15", self.prompt)


if __name__ == "__main__":
    unittest.main()
