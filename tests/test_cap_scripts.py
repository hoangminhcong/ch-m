"""
Kiểm toán bước 4 — độ phủ các script tạo số liệu CAP (trước đây chỉ được thử tay): score_cap, run_cap_conformance,
build_cap_report, run_cap_generation. Dữ liệu GIẢ trong thư mục tạm; không nạp log, không gọi API.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import scripts.build_cap_report as report  # noqa: E402
import scripts.run_cap_conformance as conf  # noqa: E402
import scripts.run_cap_generation as gen  # noqa: E402
import scripts.score_cap as score  # noqa: E402

MAIL = "Payment application / Application / mail income"
PAY = "Payment application / Application / begin payment"


def _ast(**kw):
    base = {"article_id": "x", "template_name": "Response", "activation_activity": MAIL, "target_activity": PAY,
            "activation_attr": None, "activation_op": None, "activation_val": None, "extra_conditions": [],
            "time_min": 0, "time_max": None, "time_unit": "d"}
    return {**base, **kw}


GOLD = {"status": "approved", "source": {"labels_file": "FAKE"},
        "clauses": {"P1": {"kind": "positive", "tier4": True, "gold": [_ast(time_max=30)], "round": 1},
                    "P2": {"kind": "positive", "tier4": False, "gold": [_ast()], "round": 2},
                    "T1": {"kind": "trap", "tier4": False, "gold": [], "round": 1},
                    "U1": {"kind": "uncertain", "tier4": False, "gold": [], "round": 2}}}


def _pred(nid, outcome, ast=None, **kw):
    return {"node_id": nid, "round": 1, "outcome": outcome, "ast": ast, "rounds_needed": 0, "context_refs": [],
            "skipped_refs": [], "truncated_chars": 0, "context_chars": 10, "trajectory": [{"status": "PASSED"}], **kw}


class TestScoreCap(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "gold.json").write_text(json.dumps(GOLD), encoding="utf-8")
        y = {"P1": _pred("P1", "RULE", _ast(time_max=30)), "P2": _pred("P2", "RULE", _ast()),
             "T1": _pred("T1", "BASELESS"), "U1": _pred("U1", "ERROR")}
        x = {"P1": _pred("P1", "RULE", _ast()), "P2": _pred("P2", "FAILED"), "T1": _pred("T1", "RULE", _ast())}
        for name, p in (("Y", y), ("X", x)):
            (self.dir / f"predictions_{name}.json").write_text(json.dumps({"model": "FAKE", "predictions": p}),
                                                               encoding="utf-8")

    def test_errors_excluded_and_scores(self) -> None:
        preds = score.load_predictions(self.dir)
        self.assertNotIn("U1", preds["Y"])
        res = score.score_all(score.load_gold(self.dir / "gold.json", False), preds)
        self.assertEqual(res["n_scored"], 3)
        self.assertEqual(res["configs"]["Y"]["overall"]["correct"], 3)
        self.assertEqual(res["configs"]["X"]["overall"]["correct"], 0)
        self.assertEqual(res["paired"]["TN6 X vs Y (Tier 4)"]["only_b"], ["P1"])

    def test_baseline_and_balanced_rate(self) -> None:
        """
        Khi gần như mọi khoản là bẫy, 'đúng tổng' bị hệ thống lười (luôn BASELESS) thắng. Báo cáo phải có mức chuẩn
        đó và tỉ lệ cân bằng = trung bình(tỉ lệ đúng positive, tỉ lệ đúng bẫy) để không thổi phồng kết quả.
        """
        res = score.score_all(GOLD, score.load_predictions(self.dir))
        base = res["baselines"]["always-BASELESS"]
        self.assertEqual((base["overall"]["correct"], base["positive"]["correct"], base["trap"]["correct"]), (1, 0, 1))
        self.assertEqual(base["balanced"], 0.5)
        self.assertEqual(res["configs"]["Y"]["balanced"], 1.0)
        self.assertEqual(res["configs"]["X"]["balanced"], 0.0)
        self.assertIn("Y vs luôn BASELESS", res["paired"])
        page = report.build(self._write_scores(res))
        self.assertIn("Mức chuẩn: luôn BASELESS", page)
        self.assertIn("Tỉ lệ cân bằng", page)

    def test_balanced_undefined_without_both_kinds(self) -> None:
        only_traps = {k: v for k, v in GOLD["clauses"].items() if v["kind"] != "positive"}
        s = score.score_config(only_traps, {})
        self.assertIsNone(s["balanced"])

    def _write_scores(self, res) -> Path:
        (self.dir / "scores.json").write_text(json.dumps(res), encoding="utf-8")
        return self.dir

    def test_error_predictions_block_scoring(self) -> None:
        """F-CACHE: khoản ERROR (lỗi hạ tầng) không được âm thầm tính FAILED."""
        self.assertEqual(score.prediction_errors(self.dir), {"Y": ["U1"]})
        with self.assertRaises(SystemExit):
            score.refuse_on_errors(self.dir, allow_errors=False)
        score.refuse_on_errors(self.dir, allow_errors=True)

    def test_unapproved_gold_refused(self) -> None:
        (self.dir / "cand.json").write_text(json.dumps({**GOLD, "status": "candidate"}), encoding="utf-8")
        with self.assertRaises(SystemExit):
            score.load_gold(self.dir / "cand.json", False)
        self.assertEqual(score.load_gold(self.dir / "cand.json", True)["status"], "candidate")

    def test_report_builds_all_sections(self) -> None:
        res = score.score_all(GOLD, score.load_predictions(self.dir))
        (self.dir / "scores.json").write_text(json.dumps(res), encoding="utf-8")
        page = report.build(self.dir)
        for part in ("A. Kết quả sinh", "B. Độ chính xác", "Các kiểm đã can thiệp", "McNemar"):
            self.assertIn(part, page)
        self.assertNotIn("Chưa có gold đã duyệt", page)


class TestConformanceScript(unittest.TestCase):
    def test_collect_and_evaluate_without_engine(self) -> None:
        preds = {"Y": {"P1": _pred("P1", "RULE", _ast(time_max=30)), "P2": _pred("P2", "BASELESS")}}
        plan = conf.collect_lines(GOLD, preds)
        self.assertEqual(set(plan), {"P1", "P2"})
        self.assertEqual(plan["P2"]["pred"], {})
        line = plan["P1"]["gold"][0]
        self.assertEqual(plan["P1"]["pred"]["Y"], line)
        states = {line: ["Violated", "Satisfied", "Vacuously Satisfied"], plan["P2"]["gold"][0]: ["Satisfied"] * 3}
        out = conf.evaluate(plan, states)
        self.assertEqual(out["P1"]["pred"]["Y"]["kappa"], 1.0)
        self.assertEqual(out["P1"]["gold"][0]["violated"], 1)

    def test_year_scoped_clause_only_judged_on_its_years(self) -> None:
        """Tập Đức: khoản có 'years' → chỉ so phán quyết trên hồ sơ của các năm đó; khoản CAP (không years) như cũ."""
        preds = {"Y": {"P1": _pred("P1", "RULE", _ast(time_max=30))}}
        plan = conf.collect_lines(GOLD, preds, years_of={"P1": [2015]})
        self.assertEqual(plan["P1"]["years"], [2015])
        self.assertIsNone(conf.collect_lines(GOLD, preds)["P1"]["years"])
        line = plan["P1"]["gold"][0]
        states = {line: ["Violated", "Satisfied", "Violated"], plan["P2"]["gold"][0]: ["Satisfied"] * 3}
        out = conf.evaluate(plan, states, case_years=[2015, 2015, 2016])
        self.assertEqual((out["P1"]["gold"][0]["cases"], out["P1"]["gold"][0]["violated"]), (2, 1))
        self.assertEqual(out["P2"]["gold"][0]["cases"], 3)

    def test_activity_group_checked_member_by_member(self) -> None:
        """
        Gold dùng nhóm '{A | B}' (engine hỗ trợ: một bước ghi bằng activity khác nhau theo năm). Bước kiểm tên
        trước đây coi cả chuỗi '{A | B}' là MỘT activity → báo 'không có trong log' và dừng, không ghi
        conformance.json. Đúng: tách nhóm, chỉ báo thành viên thật sự không có trong log.
        """
        known = {"A", "B", "C"}
        lines = ["Precedence[{A | B}, C] |  | |", "Existence[A] |  | |"]
        self.assertEqual(conf.unknown_activities(lines, known), set())
        self.assertEqual(conf.unknown_activities(["Response[{A | Z}, C] |  | |"], known), {"Z"})


class TestGenerationScriptHelpers(unittest.TestCase):
    def test_select_and_summary(self) -> None:
        chunks = [{"node_id": "a"}, {"node_id": "b"}, {"node_id": "c"}]
        args = type("A", (), {"only": ["b", "c"], "limit": 1})()
        self.assertEqual(gen._select(chunks, args), [{"node_id": "b"}])
        with self.assertRaises(SystemExit):
            gen._select(chunks, type("A", (), {"only": ["zz"], "limit": None})())
        self.assertEqual(gen._summary({"a": {"outcome": "RULE"}, "b": {"outcome": "ERROR"}})["ERROR"], 1)

    def test_outcome_mapping(self) -> None:
        self.assertEqual(gen.outcome_of({"final_ast": None, "trajectory": [{"status": "DECLINED_NO_OBLIGATION"}]}),
                         "BASELESS")
        self.assertEqual(gen.outcome_of({"final_ast": {}, "trajectory": [{"status": "DETECTED_BASELESS_TRAP"}]}),
                         "BASELESS")
        self.assertEqual(gen.outcome_of({"final_ast": {}, "trajectory": [{"status": "PASSED"}]}), "RULE")


if __name__ == "__main__":
    unittest.main()
