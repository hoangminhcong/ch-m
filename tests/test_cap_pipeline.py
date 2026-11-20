"""
Pipeline thực nghiệm bộ CAP (TN5–TN8): ký hiệu phiếu → AST gold, đọc phiếu nhãn, ngữ cảnh đồ thị (cấu hình Y),
chấm điểm, phán quyết từng hồ sơ, và vòng sinh với LLM giả.

Nhãn dùng ở đây là NHÃN GIẢ cho test (khoản luật giả định / Γ thu nhỏ) — không phải gold, không ghi ra data/.
"""

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_cap_generation import outcome_of, run_clause  # noqa: E402
from src.evaluation.cap_conformance import best_gold_match, cohen_kappa, compare_verdicts  # noqa: E402
from src.evaluation.cap_gold import (  # noqa: E402
    approval_blockers,
    build_gold_candidates,
    parse_label_sheet,
    scored_clauses,
)
from src.evaluation.cap_notation import NotationError, notation_to_ast, parse_date  # noqa: E402
from src.evaluation.cap_scoring import (  # noqa: E402
    compare_ast,
    mcnemar_exact,
    paired_comparison,
    score_clause,
    score_config,
    wilson,
)
from src.neural.graph_context import LegalGraphIndex, clause_only_chunk, graph_context_chunk  # noqa: E402

MAIL = "Payment application / Application / mail income"
PAY = "Payment application / Application / begin payment"
GAMMA = {
    "valid_activities": [MAIL, PAY, "Inspection / Inspection(x) / finish"],
    "activities_by_origin": {},
    "case_attributes": {"case:year": {"type": "String", "samples": []},
                        "case:young farmer": {"type": "Boolean", "samples": []},
                        "case:area": {"type": "Float", "samples": []}},
    "event_attributes": {"time:timestamp": {"type": "Timestamp", "samples": []}},
}


def _ast(**kw):
    base = {"article_id": "A", "template_name": "Response", "activation_activity": MAIL, "target_activity": PAY,
            "activation_attr": None, "activation_op": None, "activation_val": None, "extra_conditions": [],
            "time_min": 0, "time_max": None, "time_unit": "d"}
    return {**base, **kw}


class TestNotation(unittest.TestCase):
    def test_date_forms(self) -> None:
        self.assertEqual(parse_date("15/05/năm"), "year-05-15")
        self.assertEqual(parse_date("30/06/năm+1"), "year+1-06-30")
        self.assertEqual(parse_date("1/12/2016"), "2016-12-01")
        with self.assertRaises(NotationError):
            parse_date("31/13/năm")

    def test_existence_with_date(self) -> None:
        a = notation_to_ast(f"Existence({MAIL}) với ngày({MAIL}) <= 15/05/năm", GAMMA, "X")
        self.assertEqual((a["template_name"], a["activation_attr"], a["activation_val"]),
                         ("Existence", "date", "year-05-15"))

    def test_date_range_becomes_two_conditions(self) -> None:
        a = notation_to_ast(f"Existence({PAY}) với ngày({PAY}) trong [01/12/năm, 30/06/năm+1]", GAMMA, "X")
        self.assertEqual(a["activation_op"], ">=")
        self.assertEqual(a["extra_conditions"], [{"attr": "date", "op": "<=", "val": "year+1-06-30"}])

    def test_response_with_deadline_and_case_conditions(self) -> None:
        a = notation_to_ast(f"Response({MAIL} -> {PAY}) ≤ 30 ngày | young farmer = true và area >= 0,3",
                            GAMMA, "X")
        self.assertEqual((a["target_activity"], a["time_max"], a["time_unit"]), (PAY, 30, "d"))
        self.assertEqual((a["activation_attr"], a["activation_val"]), ("case:young farmer", True))
        self.assertEqual(a["extra_conditions"], [{"attr": "case:area", "op": ">=", "val": 0.3}])

    def test_time_units_kept_as_in_law(self) -> None:
        """F-UNITS: tháng lịch, tuần, ngày làm việc giữ đúng đơn vị (không quy đổi — mục 7)."""
        for text, unit in (("≤ 6 tháng", "mo"), ("≤ 8 tuần", "w"), ("≤ 2 ngày làm việc", "wd"),
                           ("trong ≤ 2 working days", "wd"), ("≤ 30 ngày", "d"), ("≤ 3 months", "mo")):
            with self.subTest(text=text):
                a = notation_to_ast(f"Response({MAIL} → {PAY}) {text}", GAMMA, "X")
                self.assertEqual(a["time_unit"], unit)

    def test_precedence_date_on_activation_b(self) -> None:
        a = notation_to_ast(f"Precedence({MAIL} → {PAY}) với ngày({PAY}) trong [01/12/năm, 30/06/năm+1]",
                            GAMMA, "X")
        self.assertEqual((a["activation_attr"], a["extra_conditions"][0]["val"]), ("date", "year+1-06-30"))

    def test_activity_with_parentheses_and_loose_spacing(self) -> None:
        a = notation_to_ast("existence(inspection/Inspection(x)/finish)", GAMMA, "X")
        self.assertEqual(a["activation_activity"], "Inspection / Inspection(x) / finish")

    def test_rejections(self) -> None:
        bad = [f"Response({MAIL} → begin paymnt)",          # activity sai chính tả: không đoán
               f"Response({MAIL} → {PAY}) ≤ 1 tháng ≤ 2 ngày",  # hai thời hạn
               f"Precedence({MAIL} → {PAY}) với ngày({MAIL}) <= 15/05/năm",  # Precedence: ngày phải của B (F-PREC)
               f"Foo({MAIL})",                              # mẫu lạ
               f"Existence({MAIL}) với case:area >= nhiều",  # Float cần số
               f"Existence({MAIL}) với rainfall > 3",        # thuộc tính không có trong Γ
               f"Response({MAIL} → {PAY}) với ngày({PAY}) <= 15/05/năm",  # ngày của target: chưa hỗ trợ
               f"Existence({MAIL} → {PAY})"]                 # unary có target: Tầng 1
        for s in bad:
            with self.subTest(s=s), self.assertRaises(NotationError):
                notation_to_ast(s, GAMMA, "X")


SHEET = (
    "R9:Art1(1): **Quan sát được:** Có · **Ràng buộc mới:** Existence(" + MAIL + ") với ngày(" + MAIL
    + ") <= 15/05/năm · **Cần điều tham chiếu:** Không · **Độ chắc chắn:** Cao · **Lý do:** giả\n"
    "R9:Art1(2): **Quan sát được:** Có · **Ràng buộc mới:** Response(" + MAIL + " → " + PAY + ") ≤ 30 ngày; "
    "Response(" + MAIL + " → " + PAY + ") · **Cần điều tham chiếu:** Có · **Độ chắc chắn:** TB · **Lý do:** giả\n"
    "R9:Art2: **Quan sát được:** Không · **Ràng buộc mới:** — · **Cần điều tham chiếu:** — · **Độ chắc chắn:** Cao"
    " · **Lý do:** định nghĩa\n"
    "R9:Art3: **Quan sát được:** Không chắc · **Ràng buộc mới:** — · **Cần điều tham chiếu:** — · "
    "**Độ chắc chắn:** Thấp · **Lý do:** ?\n"
    "R9:Art4: **Quan sát được:** Có · **Ràng buộc mới:** Response(" + MAIL + " → nope) · "
    "**Cần điều tham chiếu:** Không · **Độ chắc chắn:** Cao · **Lý do:** giả\n"
    "R9:Art5: **Quan sát được:** ___ · **Ràng buộc mới:** ___ · **Cần điều tham chiếu:** ___ · "
    "**Độ chắc chắn:** ___ · **Lý do:** ___\n"
)
CANDS = [
    {"node_id": "R9:Art1(1)", "round": 1, "text": "Applications shall be lodged not later than 15 May."},
    {"node_id": "R9:Art1(2)", "round": 1, "text": "Payment shall follow in accordance with Article 7.",
     "referenced": [{"target": "R9:Art7", "found": True, "text": "within 30 days of the application"}]},
    {"node_id": "R9:Art2", "round": 2, "text": "'farmer' means a natural person."},
    {"node_id": "R9:Art3", "round": 2, "text": "x"},
    {"node_id": "R9:Art4", "round": 2, "text": "x"},
    {"node_id": "R9:Art5", "round": 2, "text": "x"},
]


class TestGoldCandidates(unittest.TestCase):
    def setUp(self) -> None:
        self.labels = parse_label_sheet(SHEET)
        self.gold = build_gold_candidates(self.labels, CANDS, GAMMA)
        self.c = self.gold["clauses"]

    def test_parse_fields(self) -> None:
        self.assertEqual(len(self.labels), 6)
        self.assertEqual(self.labels["R9:Art1(2)"]["constraints"][0], f"Response({MAIL} → {PAY}) ≤ 30 ngày")
        self.assertEqual(self.labels["R9:Art5"]["observable"], "blank")

    def test_kinds(self) -> None:
        kinds = {nid: c["kind"] for nid, c in self.c.items()}
        self.assertEqual(kinds, {"R9:Art1(1)": "positive", "R9:Art1(2)": "positive", "R9:Art2": "trap",
                                 "R9:Art3": "uncertain", "R9:Art4": "invalid", "R9:Art5": "unlabeled"})

    def test_tier4_and_number_from_reference_ok(self) -> None:
        self.assertTrue(self.c["R9:Art1(2)"]["tier4"])
        self.assertEqual(len(self.c["R9:Art1(2)"]["gold"]), 2)
        self.assertEqual(self.c["R9:Art1(2)"]["warnings"], [])  # 30 có trong khoản được dẫn chiếu

    def test_number_not_in_text_warns_without_dropping(self) -> None:
        cands = [dict(CANDS[1], referenced=[])] + CANDS[:1] + CANDS[2:]
        c = build_gold_candidates(self.labels, cands, GAMMA)["clauses"]["R9:Art1(2)"]
        self.assertEqual(c["kind"], "positive")
        self.assertTrue(c["warnings"])

    def test_blockers_and_scored_set(self) -> None:
        # 1 khoản invalid + 1 khoản chưa gán nhãn (rà soát 2026-11-18 E-H4: chưa gán nhãn nay cũng chặn duyệt)
        self.assertEqual(len(approval_blockers(self.gold)), 2)
        self.assertEqual(set(scored_clauses(self.gold)), {"R9:Art1(1)", "R9:Art1(2)", "R9:Art2"})

    def test_unknown_clause_rejected(self) -> None:
        with self.assertRaises(KeyError):
            build_gold_candidates(self.labels, CANDS[:2], GAMMA)


class TestCompareAst(unittest.TestCase):
    def test_classes(self) -> None:
        g = _ast(time_max=30)
        self.assertEqual(compare_ast(_ast(time_max=30), g), "EQ")
        self.assertEqual(compare_ast(_ast(time_max=720, time_unit="h"), g), "EQ")  # 720 h = 30 ngày
        self.assertEqual(compare_ast(_ast(time_max=10), g), "STRENGTHENED")
        self.assertEqual(compare_ast(_ast(), g), "WEAKENED")
        self.assertEqual(compare_ast(_ast(template_name="Chain Response", time_max=30), g), "STRENGTHENED")
        self.assertEqual(compare_ast(_ast(template_name="Precedence", time_max=30), g), "REVERSED")
        self.assertEqual(compare_ast(_ast(activation_activity=PAY, target_activity=MAIL, time_max=30), g), "REVERSED")
        self.assertEqual(compare_ast(_ast(target_activity="other", time_max=30), g), "MISMATCH")
        self.assertEqual(compare_ast(_ast(activation_attr="case:area", activation_op=">", activation_val=1,
                                          time_max=30), g), "COND_DIFF")

    def test_calendar_units_exact_for_eq(self) -> None:
        g = _ast(time_max=2, time_unit="mo")
        self.assertEqual(compare_ast(_ast(time_max=2, time_unit="mo"), g), "EQ")
        self.assertEqual(compare_ast(_ast(time_max=60, time_unit="d"), g), "STRENGTHENED")  # 60 ngày < 2 tháng
        self.assertEqual(compare_ast(_ast(time_max=3, time_unit="mo"), g), "WEAKENED")
        self.assertEqual(compare_ast(_ast(time_max=2, time_unit="w"), _ast(time_max=14)), "EQ")  # tuần cố định

    def test_condition_order_and_value_types_ignored(self) -> None:
        a = _ast(activation_attr="date", activation_op=">=", activation_val="year-12-01",
                 extra_conditions=[{"attr": "case:area", "op": ">", "val": 1}])
        b = _ast(activation_attr="case:area", activation_op=">", activation_val="1.0",
                 extra_conditions=[{"attr": "date", "op": ">=", "val": "year-12-01"}])
        self.assertEqual(compare_ast(a, b), "EQ")


class TestScoring(unittest.TestCase):
    def setUp(self) -> None:
        self.gold = {"P1": {"kind": "positive", "tier4": True, "gold": [_ast(time_max=30), _ast()]},
                     "P2": {"kind": "positive", "tier4": False, "gold": [_ast()]},
                     "T1": {"kind": "trap", "tier4": False, "gold": []}}

    def test_score_clause(self) -> None:
        self.assertEqual(score_clause(self.gold["P1"], {"outcome": "RULE", "ast": _ast()}), "EQ")  # gold thứ 2
        self.assertEqual(score_clause(self.gold["P1"], {"outcome": "BASELESS"}), "MISSED_AS_BASELESS")
        self.assertEqual(score_clause(self.gold["P2"], None), "FAILED")
        self.assertEqual(score_clause(self.gold["T1"], {"outcome": "BASELESS"}), "TRAP_DETECTED")
        self.assertEqual(score_clause(self.gold["T1"], {"outcome": "RULE", "ast": _ast()}), "TRAP_FALSE_RULE")

    def test_config_and_paired(self) -> None:
        x = score_config(self.gold, {"P1": {"outcome": "BASELESS"}, "P2": {"outcome": "RULE", "ast": _ast()},
                                     "T1": {"outcome": "RULE", "ast": _ast()}})
        y = score_config(self.gold, {"P1": {"outcome": "RULE", "ast": _ast(time_max=30)},
                                     "P2": {"outcome": "RULE", "ast": _ast()}, "T1": {"outcome": "BASELESS"}})
        self.assertEqual((x["overall"]["correct"], y["overall"]["correct"]), (1, 3))
        self.assertEqual((x["tier4"]["correct"], y["tier4"]["correct"]), (0, 1))
        pc = paired_comparison(x, y)
        self.assertEqual((pc["only_a"], pc["only_b"]), ([], ["P1", "T1"]))
        self.assertEqual(pc["p_value"], 0.5)

    def test_statistics(self) -> None:
        lo, hi = wilson(8, 10)
        self.assertAlmostEqual(lo, 0.4902, places=3)
        self.assertAlmostEqual(hi, 0.9433, places=3)
        self.assertEqual(mcnemar_exact(0, 0), 1.0)
        self.assertAlmostEqual(mcnemar_exact(0, 6), 0.03125)


class TestGraphContext(unittest.TestCase):
    GRAPH = {"nodes": [{"id": "R1:Art1(1)", "label": "Paragraph", "props": {"text": "Clause."}},
                       {"id": "R2:Art5", "label": "Article", "props": {"text": "whole"}},
                       {"id": "R2:Art5(2)", "label": "Paragraph", "props": {"text": "second"}},
                       {"id": "R2:Art5(1)", "label": "Paragraph", "props": {"text": "first"}},
                       {"id": "R2:Art6(1)", "label": "Paragraph", "props": {"text": "x" * 5000}}],
             "edges": [{"source": "R2:Art5", "target": "R2:Art5(2)", "type": "HAS_PARAGRAPH", "props": {}},
                       {"source": "R2:Art5", "target": "R2:Art5(1)", "type": "HAS_PARAGRAPH", "props": {}},
                       {"source": "R1:Art1(1)", "target": "R2:Art5", "type": "REFERS_TO", "props": {"in_scope": True}},
                       {"source": "R1:Art1(1)", "target": "1305/2013:Art2", "type": "REFERS_TO",
                        "props": {"in_scope": False}},
                       {"source": "R1:Art1(1)", "target": "R2:Art6(1)", "type": "REFERS_TO", "props": {"in_scope": True}}]}

    def test_article_expanded_in_order_external_skipped_long_truncated(self) -> None:
        chunk = {"node_id": "R1:Art1(1)", "text": "Clause."}
        y = graph_context_chunk(chunk, LegalGraphIndex(self.GRAPH))
        self.assertIn("[R2:Art5] first\nsecond", y["text"])
        self.assertEqual(y["context_refs"], ["R2:Art5", "R2:Art6(1)"])
        self.assertEqual(y["skipped_refs"], ["1305/2013:Art2"])
        self.assertEqual(y["truncated_chars"], 2000)
        self.assertEqual(clause_only_chunk(chunk)["text"], "Clause.")

    def test_v12_placeholder_skipped_and_paragraph_of_cited_article_not_repeated(self) -> None:
        """v1.2 (rà soát M2): node giữ chỗ không text / in_scope=False bị bỏ; khoản của Điều đã dẫn chiếu không lặp."""
        graph = {"nodes": self.GRAPH["nodes"] + [
                     {"id": "R2:Art99", "label": "Article", "props": {"number": "99", "in_scope": False}},
                     {"id": "R2:Art7", "label": "Article", "props": {"text": "  "}}],
                 "edges": self.GRAPH["edges"][:2] + [
                     {"source": "R1:Art1(1)", "target": t, "type": "REFERS_TO", "props": {"in_scope": True}}
                     for t in ("R2:Art5(1)", "R2:Art99", "R2:Art5", "R2:Art7")]}
        y = graph_context_chunk({"node_id": "R1:Art1(1)", "text": "Clause."}, LegalGraphIndex(graph))
        self.assertEqual(y["context_refs"], ["R2:Art5"])
        self.assertEqual(y["skipped_refs"], ["R2:Art99", "R2:Art7"])
        self.assertEqual(y["text"].count("first"), 1)


class TestConformanceMetrics(unittest.TestCase):
    def test_compare_verdicts(self) -> None:
        g = ["Violated", "Violated", "Satisfied", "Vacuously Satisfied"]
        p = ["Violated", "Satisfied", "Violated", "Vacuously Satisfied"]
        r = compare_verdicts(g, p)
        self.assertEqual((r["tp"], r["fp"], r["fn"], r["tn"]), (1, 1, 1, 1))
        self.assertEqual((r["agreement"], r["precision"], r["recall"], r["kappa"]), (0.5, 0.5, 0.5, 0.0))
        self.assertTrue(compare_verdicts(g, ["Vacuously Satisfied"] * 4)["vacuous"])
        self.assertEqual(cohen_kappa(5, 0, 0, 5), 1.0)

    def test_best_gold_match(self) -> None:
        states = {"g1": ["Violated", "Satisfied"], "g2": ["Satisfied", "Satisfied"], "p": ["Satisfied", "Satisfied"]}
        self.assertEqual(best_gold_match(["g1", "g2"], "p", states)["gold_line"], "g2")


class FakeLLM:
    def __init__(self, gen, verdict="EQUIVALENT"):
        self.gen, self.verdict = gen, verdict

    def chat_json(self, msgs, temperature=0.0, **_):
        if isinstance(msgs, list):
            return json.dumps(self.gen)
        return {"verdict": self.verdict, "diagnostic_feedback": "fake"}


class TestGenerationLoop(unittest.TestCase):
    CHUNK = {"node_id": "R9:Art1(1)", "round": 1, "text": "Applications shall be lodged not later than 15 May."}
    GEN = {"article_id": "R9:Art1(1)",
           "obligation_analysis": {"duty_bearer": "applicant", "observable_in_log": True,
                                   "evidence": "Applications shall be lodged"},
           "template_name": "Existence", "activation_activity": MAIL,
           "activation_attr": "date", "activation_op": "<=", "activation_val": "year-05-15"}

    def test_rule_and_baseless_outcomes(self) -> None:
        ctx = clause_only_chunk(self.CHUNK)
        rec = run_clause(self.CHUNK, ctx, GAMMA, FakeLLM(self.GEN), "X")
        self.assertEqual(rec["outcome"], "RULE")
        self.assertEqual(rec["ast"]["activation_val"], "year-05-15")
        rec = run_clause(self.CHUNK, ctx, GAMMA, FakeLLM(self.GEN, verdict="BASELESS"), "X")
        self.assertEqual((rec["outcome"], rec["ast"]), ("BASELESS", None))

    def test_failed_after_retries(self) -> None:
        bad = dict(self.GEN, activation_activity="nope")
        rec = run_clause(self.CHUNK, clause_only_chunk(self.CHUNK), GAMMA, FakeLLM(bad), "Y-retry1")
        self.assertEqual((rec["outcome"], rec["rounds_needed"]), ("FAILED", 1))
        self.assertEqual(outcome_of({"final_ast": None, "trajectory": []}), "FAILED")

    def test_generation_never_reads_gold(self) -> None:
        src = (PROJECT_ROOT / "scripts" / "run_cap_generation.py").read_text(encoding="utf-8")
        self.assertNotIn("cap_gold", src)
        self.assertNotIn("labels", src.lower().replace("phiếu nhãn", ""))


if __name__ == "__main__":
    unittest.main()
