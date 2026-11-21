"""
T1–T3 (kiểm thử 2026-11-20) thành phép kiểm thường trực:
  T1 scripts/check_derived_data.py   dữ liệu phái sinh = dựng lại từ nguồn (run_pipeline pre)
  T2 src/evaluation/output_invariants.py   bất biến trên mọi đầu ra (run_pipeline post, bước cuối)
  T3 src/evaluation/replay.py   phát lại cache bằng code hiện tại (run_pipeline replay)
Mỗi phép kiểm phải BẮT được lỗi nó nhắm tới (dữ liệu hỏng có chủ đích) và im lặng trên dữ liệu đúng.
"""

import copy
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation import output_invariants as inv  # noqa: E402
from src.evaluation.replay import compare_predictions, run_command  # noqa: E402

PROCESSED = PROJECT_ROOT / "data" / "processed"
A, B = "Doc / Main / create", "Doc / Main / decide"
GAMMA = {"valid_activities": [A, B], "activities_by_origin": {}, "case_attributes": {}, "event_attributes": {}}
AST = {"article_id": "R1:Art1", "template_name": "Response", "activation_activity": A, "target_activity": B,
       "activation_attr": None, "activation_op": None, "activation_val": None, "extra_conditions": [],
       "time_min": 0, "time_max": None, "time_unit": "d"}
CANDS = {"R1:Art1": {"node_id": "R1:Art1"}, "R1:Art2": {"node_id": "R1:Art2"}}


def _doc():
    return {"summary": {"RULE": 1, "BASELESS": 1, "FAILED": 0, "ERROR": 0},
            "predictions": {
                "R1:Art1": {"outcome": "RULE", "ast": dict(AST), "llm_rounds": 2,
                            "trajectory": [{"round": 1, "status": "FAILED_L1_L2"}, {"round": 2, "status": "PASSED"}]},
                "R1:Art2": {"outcome": "BASELESS", "ast": None, "llm_rounds": 1,
                            "trajectory": [{"round": 1, "status": "DECLINED_NO_OBLIGATION"}]}}}


@unittest.skipUnless((PROCESSED / "cap_chunks.json").exists(), "chưa dựng dữ liệu CAP")
class TestT1DerivedData(unittest.TestCase):
    def test_legal_graphs_on_disk_match_rebuild(self) -> None:
        from scripts.check_derived_data import check_legal
        rows = check_legal()
        self.assertTrue(rows)
        for r in rows:
            with self.subTest(file=r["file"]):
                self.assertNotEqual(r["same"], False, r)

    def test_compare_reports_stale_keys(self) -> None:
        from scripts.check_derived_data import compare
        r = compare("x.json", {"nodes": [1, 2], "edges": []}, {"nodes": [1], "edges": []})
        self.assertEqual((r["same"], r["differing_keys"]), (False, ["nodes"]))
        self.assertTrue(compare("x.json", {"a": 1}, {"a": 1})["same"])


class TestT2Invariants(unittest.TestCase):
    def test_consistent_file_has_no_violation(self) -> None:
        self.assertEqual(inv.check_prediction_file("Y", _doc(), GAMMA, CANDS), [])

    def test_each_corruption_is_caught(self) -> None:
        def corrupt(fn):
            d = _doc()
            fn(d)
            return inv.check_prediction_file("Y", d, GAMMA, CANDS)
        cases = {
            "summary": lambda d: d["summary"].update(RULE=2),
            "RULE không PASSED": lambda d: d["predictions"]["R1:Art1"]["trajectory"][-1].update(status="FAILED_VACUITY"),
            "BASELESS có AST": lambda d: d["predictions"]["R1:Art2"].update(ast=dict(AST)),
            "llm_rounds": lambda d: d["predictions"]["R1:Art1"].update(llm_rounds=5),
            "vòng không liên tục": lambda d: d["predictions"]["R1:Art1"]["trajectory"][0].update(round=3),
            "AST không qua Tầng 1–2": lambda d: d["predictions"]["R1:Art1"]["ast"].update(target_activity="ghost"),
            "khoản ngoài phiếu": lambda d: d["predictions"].update({"R9:Art9": d["predictions"]["R1:Art2"]}),
        }
        for name, fn in cases.items():
            with self.subTest(corruption=name):
                self.assertTrue(corrupt(fn), name)

    def test_l1_l2_ablation_not_rechecked(self) -> None:
        d = _doc()
        d["predictions"]["R1:Art1"]["ast"]["target_activity"] = "ghost"  # Y-noL12: luật sai Γ là kết quả hợp lệ
        self.assertEqual(inv.check_prediction_file("Y-noL12", d, GAMMA, CANDS, l1_l2_enabled=False), [])

    def test_scores_and_pvalues_rechecked(self) -> None:
        gold = {"R1:Art1": {"kind": "trap", "tier4": False, "gold": []},
                "R1:Art2": {"kind": "trap", "tier4": False, "gold": []}}
        preds = _doc()["predictions"]
        good = {"configs": {"Y": {"per_clause": {"R1:Art1": "TRAP_FALSE_RULE", "R1:Art2": "TRAP_DETECTED"},
                                  "positive": {"classes": {}, "correct": 0}, "trap": {"correct": 1},
                                  "overall": {"correct": 1, "n": 2}}},
                "paired": {"a vs b": {"n": 2, "both": 0, "only_a": ["x"], "only_b": [], "p_value": 1.0}}}
        self.assertEqual(inv.check_scores(good, {"Y": preds}, gold), [])
        bad = copy.deepcopy(good)
        bad["configs"]["Y"]["per_clause"]["R1:Art2"] = "TRAP_FALSE_RULE"
        bad["paired"]["a vs b"]["p_value"] = 0.03
        self.assertEqual(len(inv.check_scores(bad, {"Y": preds}, gold)), 2)

    def test_kg_and_conformance_sums(self) -> None:
        kg = {"nodes": [{"id": "a"}, {"id": "a"}], "edges": [{"source": "a", "target": "ghost"}],
              "meta": {"layers": {"constraint": 0}}}
        self.assertEqual(len(inv._check_kg("Y", kg, 1)), 3)  # cạnh treo, trùng id, sai số ràng buộc
        conf = {"cases": 10, "clauses": {"c": {"pred": {"Y": {"tp": 1, "fp": 1, "fn": 1, "tn": 1}}}}}
        self.assertEqual(len(inv.check_conformance(conf)), 1)


class TestT3Replay(unittest.TestCase):
    def test_identical_changed_and_error(self) -> None:
        orig = {"a": {"outcome": "RULE", "ast": {"x": 1}, "trajectory": [{"status": "PASSED"}]},
                "b": {"outcome": "BASELESS", "ast": None, "trajectory": [{"status": "DETECTED_BASELESS_TRAP"}]},
                "c": {"outcome": "ERROR", "error": "quota"},
                "d": {"outcome": "RULE", "ast": {"x": 2}, "trajectory": [{"status": "PASSED"}]}}
        rep = {"a": copy.deepcopy(orig["a"]),
               "b": {"outcome": "RULE", "ast": {"x": 3}, "trajectory": [{"status": "FAILED_L3_ROUNDTRIP"},
                                                                         {"status": "PASSED"}]},
               "c": {"outcome": "ERROR", "error": "cache miss"},
               "d": {"outcome": "ERROR", "error": "LookupError: cache miss"}}
        r = compare_predictions(orig, rep)
        self.assertEqual((r["identical"], r["compared"], r["skipped_error"]), (1, 3, ["c"]))
        self.assertEqual({d["clause"]: d["kind"] for d in r["differences"]}, {"b": "changed", "d": "replay_error"})

    def test_command_reproduces_run_identity(self) -> None:
        doc = {"provider": "cerebras", "model": "gpt-oss-120b", "dataset": "de", "judge_provider": "groq",
               "judge_model": "openai/gpt-oss-20b"}
        cmd = run_command("py", "gen.py", "Y", doc, "/tmp/x", only=["R1:Art1"])
        for part in (["--cache-only", "--force"], ["--dataset", "de"], ["--judge-model", "openai/gpt-oss-20b"],
                     ["--only", "R1:Art1"], ["--model", "gpt-oss-120b"]):
            with self.subTest(part=part):
                i = cmd.index(part[0])
                self.assertEqual(cmd[i:i + len(part)], part)
        self.assertNotIn("--judge-provider", run_command("py", "gen.py", "Y", {"provider": "p", "model": "m"}, "o"))


if __name__ == "__main__":
    unittest.main()
