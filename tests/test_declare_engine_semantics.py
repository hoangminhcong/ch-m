"""
Ngữ nghĩa chuẩn của engine DECLARE NSAI (sửa theo kết quả TN4).

- Mọi template khớp chuẩn (pm4py / LTLf) trên MỌI hồ sơ độ dài 1..4 trên {A, B, C}.
- Hồ sơ không kích hoạt KHÔNG bao giờ bị gắn 'Violated', ở cả hai chế độ consider_vacuity.
- Hỗ trợ nhóm activity '{X | Y}' (VD hai kênh gửi đề nghị vay O_Sent).
- Template lạ phải báo lỗi, không âm thầm xử lý như Choice.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import get_args

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.declare_engine_validation import (  # noqa: E402
    REFERENCE,
    compare_template,
    exhaustive_log,
    log_from_sequences,
    vacuity_mislabels,
)
from src.mde.constraint_ast import TemplateLiteral  # noqa: E402
from src.symbolic.declare4py_verifier import Declare4Py  # noqa: E402


def _run(sequences, decl_line, vacuity=True):
    engine = Declare4Py(log_from_sequences(sequences))
    with tempfile.NamedTemporaryFile("w", suffix=".decl", delete=False, encoding="utf-8") as f:
        f.write(decl_line + "\n")
        path = f.name
    try:
        engine.parse_decl_model(path)
        res = engine.conformance_checking(consider_vacuity=vacuity)
    finally:
        os.unlink(path)
    return {cid: next(iter(r.values())).state for (_, cid), r in res.items()}


class TestAllTemplatesMatchStandard(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.df = exhaustive_log(["A", "B", "C"], max_len=4)

    def test_every_template_agrees_on_every_trace(self) -> None:
        for template in get_args(TemplateLiteral):
            acts = ["A", "B"] if REFERENCE[template][2] == 2 else ["A"]
            with self.subTest(template=template):
                result = compare_template(self.df, template, acts)
                self.assertEqual(result["n_disagree"], 0, result["examples"])

    def test_non_activated_traces_never_violated(self) -> None:
        for template in get_args(TemplateLiteral):
            acts = ["A", "B"] if REFERENCE[template][2] == 2 else ["A"]
            with self.subTest(template=template):
                self.assertEqual(vacuity_mislabels(self.df, template, acts), 0)


class TestActivityGroups(unittest.TestCase):
    SEQS = [["X", "B"], ["Y", "B"], ["C", "B"], ["C"]]

    def test_precedence_with_group(self) -> None:
        states = _run(self.SEQS, "Precedence[{X | Y}, B] | | |")
        self.assertEqual(states["X|B"], "Satisfied")
        self.assertEqual(states["Y|B"], "Satisfied")
        self.assertEqual(states["C|B"], "Violated")
        self.assertEqual(states["C"], "Vacuously Satisfied")

    def test_response_with_group(self) -> None:
        states = _run([["A", "X"], ["A", "Y"], ["A", "C"]], "Response[A, {X | Y}] | | |")
        self.assertEqual(states["A|X"], "Satisfied")
        self.assertEqual(states["A|Y"], "Satisfied")
        self.assertEqual(states["A|C"], "Violated")

    def test_activity_names_with_parentheses(self) -> None:
        seqs = [["O_Sent (online only)", "O_Accepted"], ["O_Accepted"]]
        line = "Precedence[{O_Sent (mail and online) | O_Sent (online only)}, O_Accepted] | | |"
        states = _run(seqs, line)
        self.assertEqual(states["O_Sent (online only)|O_Accepted"], "Satisfied")
        self.assertEqual(states["O_Accepted"], "Violated")


class TestUnknownTemplate(unittest.TestCase):
    def test_unknown_template_raises(self) -> None:
        with self.assertRaises(ValueError):
            _run([["A", "B"]], "Succesion[A, B] | | |")


if __name__ == "__main__":
    unittest.main()
