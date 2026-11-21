"""
Chạy thử main() của các script dòng lệnh (2026-11-20 — trước đó độ phủ scripts/ chỉ 31%): cổng kiểm KG, chấm, phễu,
xuất ràng buộc, KG đầy đủ, proof trace, nhãn REVIEW (không nạp log), báo cáo HTML, và thứ tự bước của run_pipeline.
Dùng KG / Γ / gold THẬT trong data/ (bỏ qua nếu chưa dựng) và một thư mục dự đoán GIẢ trong thư mục tạm.
Không gọi API, không đụng results/.
"""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

PROCESSED = PROJECT_ROOT / "data" / "processed"
REVIEW = PROJECT_ROOT / "data" / "review"
NEEDED = [PROCESSED / "gamma_bpic2018.json", PROCESSED / "cap_legal_graph.json", PROCESSED / "cap_mapping_graph.json",
          PROCESSED / "bpic2018_process_graph.json", REVIEW / "cap_gold_approved.json",
          REVIEW / "cap_item_candidates.json"]


def _call(main, argv, *args):
    """Gọi main() với sys.argv giả; trả (mã thoát, stdout)."""
    out = io.StringIO()
    with mock.patch.object(sys, "argv", ["prog", *argv]), contextlib.redirect_stdout(out), \
            mock.patch.object(sys.stdout, "reconfigure", create=True):
        try:
            code = main(*args)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue()


@unittest.skipUnless(all(p.exists() for p in NEEDED), "chưa dựng KG / gold / phiếu CAP")
class TestCliSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dir = Path(tempfile.mkdtemp())
        gamma = json.loads((PROCESSED / "gamma_bpic2018.json").read_text(encoding="utf-8"))
        a, b = sorted(gamma["valid_activities"])[:2]
        sheet = json.loads((REVIEW / "cap_item_candidates.json").read_text(encoding="utf-8"))
        rule_clause = sheet[0]["node_id"]
        ast = {"article_id": rule_clause, "template_name": "Response", "activation_activity": a, "target_activity": b,
               "activation_attr": None, "activation_op": None, "activation_val": None, "extra_conditions": [],
               "time_min": None, "time_max": None, "time_unit": None}
        for cfg in ("X", "Y"):
            # cùng các trường như một dòng thật của run_cap_generation.run_clause
            preds = {c["node_id"]: {"node_id": c["node_id"], "round": c.get("round"), "outcome": "BASELESS",
                                    "ast": None, "rounds_needed": 0, "roundtrip_msg": None, "grounding": None,
                                    "obligation_analysis": None,
                                    "trajectory": [{"round": 1, "status": "DECLINED_NO_OBLIGATION"}],
                                    "context_refs": [], "skipped_refs": [], "truncated_chars": 0,
                                    "context_chars": len(c["text"]), "seconds": 0.0} for c in sheet}
            if cfg == "Y":
                preds[rule_clause] = {**preds[rule_clause], "outcome": "RULE", "ast": ast,
                                      "obligation_analysis": {"evidence": sheet[0]["text"][:40]},
                                      "trajectory": [{"round": 1, "status": "PASSED"}]}
            summary = {o: sum(p["outcome"] == o for p in preds.values()) for o in ("RULE", "BASELESS", "FAILED")}
            (cls.dir / f"predictions_{cfg}.json").write_text(json.dumps(
                {"config": cfg, "model": "m", "provider": "p", "predictions": preds, "summary": summary}),
                encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_01_pre_stage_gates_pass_on_current_data(self) -> None:
        import scripts.build_gamma_from_kg as gamma
        import scripts.build_mapping_graph as bridge
        import scripts.check_kg_metamodel as meta
        self.assertEqual(_call(meta.main, [], [])[0], 0)
        self.assertEqual(_call(gamma.main, ["--check"])[0], 0)
        self.assertEqual(_call(bridge.main, ["--check"])[0], 0)

    def test_02_post_stage_scripts_produce_their_files(self) -> None:
        import scripts.build_cap_report as report
        import scripts.build_full_kg as full_kg
        import scripts.build_proof_traces as proof
        import scripts.check_outputs as outputs
        import scripts.export_verified_constraints as export
        import scripts.review_flags as review
        import scripts.score_cap as score
        import scripts.verification_funnel as funnel
        d = str(self.dir)
        steps = [(score.main, ["--pred-dir", d], "scores.json"),
                 (funnel.main, ["--pred-dir", d], "verification_funnel.json"),
                 (export.main, ["--pred-dir", d, "--config", "Y"], "verified_constraints_Y.json"),
                 (full_kg.main, ["--pred-dir", d, "--config", "Y"], "kg_full_Y.json"),
                 (proof.main, ["--pred-dir", d, "--config", "Y"], "proof_traces_Y.json"),
                 (review.main, ["--pred-dir", d, "--configs", "Y", "--no-log"], "review_flags_Y.json"),
                 (report.main, ["--dir", d], "report.html"),
                 (outputs.main, ["--pred-dir", d], "output_invariants.json")]  # T2: 0 vi phạm trên đầu ra thật
        for main, argv, produced in steps:
            with self.subTest(step=produced):
                code, out = _call(main, argv)
                self.assertEqual(code, 0, out[-500:])
                self.assertTrue((self.dir / produced).exists())
        scores = json.loads((self.dir / "scores.json").read_text(encoding="utf-8"))
        self.assertEqual(scores["configs"]["Y"]["positive"]["n"], scores["configs"]["X"]["positive"]["n"])
        html = (self.dir / "report.html").read_text(encoding="utf-8")
        for heading in ("D. Kiểm chứng và giải thích", "E. Độ tin cậy của số liệu", "Phễu kiểm chứng", "Nhãn REVIEW"):
            self.assertIn(heading, html)
        kg = json.loads((self.dir / "kg_full_Y.json").read_text(encoding="utf-8"))
        self.assertEqual(kg["meta"]["layers"]["constraint"], 1)

    def test_03_run_pipeline_post_runs_steps_in_order_and_stops_on_failure(self) -> None:
        import scripts.run_pipeline as pipeline
        calls = []
        with mock.patch.object(pipeline, "_run", side_effect=lambda step, args: calls.append(Path(args[0]).name)):
            code, _ = _call(pipeline.main, ["post", "--pred-dir", str(self.dir), "--configs", "Y", "--conformance"])
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["score_cap.py", "verification_funnel.py", "export_verified_constraints.py",
                                 "build_full_kg.py", "build_proof_traces.py", "review_flags.py",
                                 "run_cap_conformance.py", "build_cap_report.py", "check_outputs.py"])

        def failing(step, args):
            if Path(args[0]).name == "verification_funnel.py":
                raise SystemExit("DỪNG")
            calls.append(Path(args[0]).name)

        calls.clear()
        with mock.patch.object(pipeline, "_run", side_effect=failing):
            code, _ = _call(pipeline.main, ["post", "--pred-dir", str(self.dir)])
        self.assertNotEqual(code, 0)
        self.assertEqual(calls, ["score_cap.py"])  # các bước sau không chạy


if __name__ == "__main__":
    unittest.main()
