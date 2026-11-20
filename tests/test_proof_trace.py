"""
Proof trace (src/evaluation/proof_trace.py): kiểm dẫn chứng của LLM (nguyên văn / gần nguyên văn / không có căn cứ),
truy vết đủ các bước từ KG và đầu ra hệ thống, HTML được escape, và không đọc gold.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.proof_trace import build_traces, evidence_check, render_html, summarize  # noqa: E402

LAW = ("It shall be paid upon activation of payment entitlements in respect of those hectares held by the farmer "
       "concerned or, in Member States applying Article 36 of this Regulation, upon declaration of those eligible "
       "hectares by the farmer concerned. The on-the-spot checks shall also cover all non-agricultural land.")


class TestEvidenceCheck(unittest.TestCase):
    def test_verbatim_with_ellipsis_and_typographic_variants(self) -> None:
        ev = evidence_check("It shall be paid upon activation ... cover all non‑agricultural land", [LAW])
        self.assertEqual((ev["level"], ev["fragments"], ev["found"]), ("verbatim", 2, 2))

    def test_near_verbatim_when_llm_shortens_sentence(self) -> None:
        # trường hợp thật R1307:Art48(3): LLM bỏ 'in Member States applying Article 36 …'
        ev = evidence_check("or upon declaration of those eligible hectares by the farmer concerned", [LAW])
        self.assertEqual(ev["level"], "near")
        self.assertGreaterEqual(ev["coverage"], 0.8)

    def test_unsupported_when_text_not_in_law(self) -> None:
        ev = evidence_check("the applicant must submit the claim before 15 May of the year", [LAW])
        self.assertEqual(ev["level"], "unsupported")

    def test_short_or_missing_evidence_not_judged(self) -> None:
        self.assertEqual(evidence_check("and", [LAW])["level"], "none")
        self.assertEqual(evidence_check(None, [LAW])["level"], "none")


GRAPH = {"nodes": [{"id": "R1:Art1(1)", "label": "Paragraph", "props": {"text": "1. Farmers <shall> apply."}},
                   {"id": "R1:Art2", "label": "Paragraph", "props": {"text": "Definition of farmer."}}],
         "edges": []}
PRED = {"model": "m", "predictions": {
    "R1:Art1(1)": {"outcome": "RULE", "context_refs": ["R1:Art2"], "skipped_refs": ["1305/2013:Art2"],
                   "obligation_analysis": {"duty_bearer": "farmer", "observable_in_log": True,
                                           "evidence": "Farmers <shall> apply."},
                   "ast": {"article_id": "R1:Art1(1)", "template_name": "Existence", "activation_activity": "A"},
                   "trajectory": [{"round": 1, "status": "FAILED_L1_L2", "error": "unknown activity"},
                                  {"round": 2, "status": "PASSED", "error": None}],
                   "roundtrip_msg": "Roundtrip check passed.",
                   "grounding": {"witness_cases": 10, "num_cases": 20, "vacuous": False},
                   "process_checks": {"mass_violation": {"activated": 10, "violated": 1, "ratio": 0.1,
                                                         "mass_violation": False, "examples": ["c1"]}}},
    "R1:Art2": {"outcome": "BASELESS", "ast": None}}}


class TestTraces(unittest.TestCase):
    def setUp(self) -> None:
        self.findings = [{"a": "R1:Art1(1)", "b": "R9:Art9", "kind": "IMPLIES", "note": "n"}]
        self.traces = build_traces(PRED, GRAPH, self.findings)

    def test_only_rules_and_every_step_present(self) -> None:
        self.assertEqual([t["clause"] for t in self.traces], ["R1:Art1(1)"])
        t = self.traces[0]
        self.assertEqual(t["clause_text"], "1. Farmers <shall> apply.")
        self.assertEqual(t["context_refs"], [{"target": "R1:Art2", "text": "Definition of farmer."}])
        self.assertEqual([r["status"] for r in t["rounds"]], ["FAILED_L1_L2", "PASSED"])
        self.assertTrue(t["decl"].startswith("Existence[A]"))
        self.assertEqual(t["mass_violation"]["violated"], 1)
        self.assertEqual(t["evidence"]["level"], "verbatim")
        self.assertEqual(len(t["set_findings"]), 1)

    def test_html_is_escaped_and_summary_counts(self) -> None:
        summary = summarize(self.traces, self.findings)
        self.assertEqual((summary["rules"], summary["evidence_verbatim"]), (1, 1))
        page = render_html(self.traces, "T <x>", summary)
        self.assertIn("Farmers &lt;shall&gt; apply.", page)
        self.assertNotIn("<shall>", page)
        self.assertIn("T &lt;x&gt;", page)

    def test_module_never_reads_gold(self) -> None:
        src = (PROJECT_ROOT / "src" / "evaluation" / "proof_trace.py").read_text(encoding="utf-8")
        self.assertNotIn("cap_gold", src)
        self.assertNotIn("gold_approved", src)


if __name__ == "__main__":
    unittest.main()
