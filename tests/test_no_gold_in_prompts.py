"""
Test chống rò rỉ đáp án vào PROMPT gửi cho LLM (sinh ràng buộc và trọng tài Tầng 3).

LLM chỉ được thấy: văn bản luật + lược đồ quy trình + ví dụ trung lập. Không được thấy
mô tả gold (`description`) của rule, cũng không được thấy ví dụ trích từ chính bộ đề.
"""

import json
import sys
import unittest
from pathlib import Path
from typing import Any, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.real_llm_client import run_single_rule_with_real_llm  # noqa: E402
from src.symbolic.verbalizer_roundtrip import check_roundtrip_fidelity  # noqa: E402

SCHEMA_PATH = PROJECT_ROOT / "data" / "processed" / "process_schema.json"
GOLD_MARKER = "GOLDMARKER_7731 A_Pending <= 90 ngay"
# Cụm từ chỉ có thể đến từ chính các câu của bộ đề (R03, R09, R12, R15, R18, R25, R26)
BENCHMARK_SPECIFIC = [
    "750", "real estate", "mortgage", "W_Call after offers", "A_Accepted",
    "O_Refused", "Article 14(1)", "14 days", "10,000", "10000",
]
FICTIONAL_CHUNK = {
    "article_id": "Article 99(1)",
    "article_title": "Fictional",
    "text": "1. The lender shall inform the borrower before signing.",
}
AST = {
    "article_id": "Article 99(1)", "template_name": "Precedence",
    "activation_activity": "Inform", "target_activity": "Sign",
    "activation_attr": None, "activation_op": None, "activation_val": None,
    "time_min": None, "time_max": None, "time_unit": None,
}


class RecordingLLM:
    """LLM giả: ghi lại mọi prompt; trả AST hợp lệ khi được hỏi sinh, 'EQUIVALENT' khi được hỏi chấm."""

    def __init__(self, ast: dict) -> None:
        self.ast = ast
        self.prompts: List[str] = []

    def chat_json(self, prompt_or_messages: Any, temperature: float = 0.0, **_: Any) -> Any:
        if isinstance(prompt_or_messages, list):
            self.prompts.extend(m["content"] for m in prompt_or_messages)
            return json.dumps(self.ast)
        self.prompts.append(prompt_or_messages)
        return {"verdict": "EQUIVALENT", "diagnostic_feedback": "ok"}

    def all_text(self) -> str:
        return "\n".join(self.prompts)


class TestJudgePrompt(unittest.TestCase):
    def setUp(self) -> None:
        self.llm = RecordingLLM(AST)
        check_roundtrip_fidelity(AST, FICTIONAL_CHUNK, self.llm)
        self.prompt = self.llm.all_text()

    def test_judge_prompt_has_clause_and_candidate(self) -> None:
        self.assertIn(FICTIONAL_CHUNK["text"], self.prompt)
        self.assertIn("Inform", self.prompt)

    def test_judge_prompt_has_no_benchmark_specific_examples(self) -> None:
        found = [p for p in BENCHMARK_SPECIFIC if p.lower() in self.prompt.lower()]
        self.assertEqual(found, [])

    def test_judge_does_not_accept_gold_description(self) -> None:
        with self.assertRaises(TypeError):
            check_roundtrip_fidelity(AST, FICTIONAL_CHUNK, self.llm, rule_meta={"description": GOLD_MARKER})


from src.datasets import skip_unless_bpic2017  # noqa: E402  (bộ BPIC2017 đang tạm vô hiệu)


@skip_unless_bpic2017
@unittest.skipUnless(SCHEMA_PATH.exists(), "cần data/processed/process_schema.json")
class TestGenerationPrompt(unittest.TestCase):
    def setUp(self) -> None:
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        chunk = {"article_id": "Article 8(1)", "article_title": "Creditworthiness",
                 "text": "1. Member States shall ensure that, before the conclusion of the credit "
                         "agreement, the creditor assesses the consumer's creditworthiness."}
        ast = {**AST, "article_id": "Article 8(1)",
               "activation_activity": "W_Validate application", "target_activity": "O_Accepted"}
        self.llm = RecordingLLM(ast)
        rule_item = {"rule_id": "R99", "description": GOLD_MARKER, "is_trap": False}
        self.result = run_single_rule_with_real_llm(rule_item, chunk, schema, self.llm, max_retry=1)

    def test_runs_end_to_end(self) -> None:
        self.assertIsNotNone(self.result["final_ast"])

    def test_no_gold_description_in_any_prompt(self) -> None:
        self.assertNotIn("GOLDMARKER_7731", self.llm.all_text())

    def test_few_shot_examples_do_not_mirror_benchmark_rules(self) -> None:
        few_shot = self.llm.prompts[1:5]  # 2 cặp ví dụ user/assistant sau system prompt
        found = [p for p in ("10,000", "10000", "OfferedAmount") if p in "\n".join(few_shot)]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
