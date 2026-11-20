"""A2 — dấu dữ liệu đầu vào (src/evaluation/run_inputs.py) và các cổng dùng nó: chạy tiếp khi dữ liệu đã đổi
(run_cap_generation.check_resume) và chấm khi dự đoán lẫn phiên bản dữ liệu (score_cap.check_inputs)."""

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_cap_generation import CONFIGS, check_resume, input_paths  # noqa: E402
from scripts.score_cap import check_inputs  # noqa: E402
from src.evaluation.run_inputs import (  # noqa: E402
    MISSING, changed_inputs, fingerprint, input_conflicts, inputs_id)


class TestFingerprint(unittest.TestCase):
    def test_content_change_changes_digest_and_id(self) -> None:
        d = Path(tempfile.mkdtemp())
        (d / "a.json").write_text("1", encoding="utf-8")
        before = fingerprint({"clauses": d / "a.json", "graph": d / "none.json"})
        self.assertEqual(before["graph"], MISSING)
        (d / "a.json").write_text("2", encoding="utf-8")
        after = fingerprint({"clauses": d / "a.json", "graph": d / "none.json"})
        self.assertEqual(changed_inputs(before, after), ["clauses"])
        self.assertNotEqual(inputs_id(before), inputs_id(after))

    def test_only_common_inputs_are_compared(self) -> None:
        self.assertEqual(changed_inputs({"a": "1", "b": "2"}, {"a": "1", "c": "9"}), [])


class TestInputPaths(unittest.TestCase):
    def test_every_config_reads_clauses_and_gamma(self) -> None:
        for cfg in CONFIGS:
            self.assertLessEqual({"clauses", "gamma"}, set(input_paths(cfg)), cfg)

    def test_switches_decide_inputs(self) -> None:
        self.assertNotIn("legal_graph", input_paths("X"))
        self.assertNotIn("log_events", input_paths("Y-noVac"))
        self.assertEqual(set(input_paths("Y")), set(input_paths("R")))  # cùng file → cùng tên, so được
        self.assertIn("legal_graph_v2", input_paths("Z"))
        self.assertIn("legal_graph", input_paths("Z-noLegal"))
        self.assertIn("ontology", input_paths("Z"))


def _doc(file_inputs, row_ids):
    doc = {"predictions": {f"c{i}": ({"inputs_id": r} if r else {}) for i, r in enumerate(row_ids)}}
    if file_inputs is not None:
        doc.update(inputs=file_inputs, inputs_id=inputs_id(file_inputs))
    return doc


class TestInputConflicts(unittest.TestCase):
    A = {"clauses": "aaa", "gamma": "ggg"}
    B = {"clauses": "bbb", "gamma": "ggg"}

    def test_consistent_files(self) -> None:
        ia = inputs_id(self.A)
        found = input_conflicts({"Y": _doc(self.A, [ia, ia]), "R": _doc(self.A, [ia])})
        self.assertEqual((found["within"], found["across"], found["unstamped"]), ({}, {}, {}))

    def test_rows_from_older_data_inside_one_file(self) -> None:
        found = input_conflicts({"Y": _doc(self.B, [inputs_id(self.A), inputs_id(self.B), inputs_id(self.B)])})
        self.assertEqual(found["within"], {"Y": 1})

    def test_two_configs_read_different_versions_of_same_input(self) -> None:
        found = input_conflicts({"X": _doc(self.A, []), "Y": _doc(self.B, [])})
        self.assertEqual(set(found["across"]), {"clauses"})

    def test_rows_without_stamp_are_reported_not_judged(self) -> None:
        found = input_conflicts({"Y": _doc(None, [None, None])})
        self.assertEqual((found["unstamped"], found["within"]), ({"Y": 2}, {}))


class TestResumeGate(unittest.TestCase):
    def _args(self, **kw) -> argparse.Namespace:
        base = dict(dataset="cap", model="gpt-oss-120b", provider="cerebras", force=False)
        return argparse.Namespace(**{**base, **kw})

    def test_changed_data_blocks_resume_unless_force(self) -> None:
        doc = {"model": "gpt-oss-120b", "provider": "cerebras", "predictions": {"c": {}},
               "inputs": {"clauses": "old", "gamma": "g"}}
        with self.assertRaisesRegex(SystemExit, "clauses"):
            check_resume(doc, self._args(), {"clauses": "new", "gamma": "g"})
        check_resume(doc, self._args(force=True), {"clauses": "new", "gamma": "g"})
        check_resume(doc, self._args(), {"clauses": "old", "gamma": "g"})

    def test_file_without_stamp_can_resume(self) -> None:
        doc = {"model": "gpt-oss-120b", "provider": "cerebras", "predictions": {"c": {}}}
        check_resume(doc, self._args(), {"clauses": "new"})


class TestScoreGate(unittest.TestCase):
    def test_mixed_data_versions_stop_scoring_unless_allowed(self) -> None:
        d = Path(tempfile.mkdtemp())
        a, b = {"clauses": "aaa"}, {"clauses": "bbb"}
        (d / "predictions_X.json").write_text(json.dumps(_doc(a, [inputs_id(a)])), encoding="utf-8")
        (d / "predictions_Y.json").write_text(json.dumps(_doc(b, [inputs_id(b)])), encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "phiên bản dữ liệu"):
            check_inputs(d, allow_mixed=False)
        self.assertEqual(set(check_inputs(d, allow_mixed=True)["across"]), {"clauses"})


if __name__ == "__main__":
    unittest.main()
