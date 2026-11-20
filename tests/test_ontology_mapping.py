"""
v2 (docs/V2_DANG_KY_TRUOC.md thành phần 6, 9, 10): ontology loại giấy tờ (người duyệt) → MAPS_TO khoản luật → loại
giấy tờ qua thuật ngữ pháp lý → dòng gợi ý trong câu hỏi sinh. Ontology chưa duyệt thì KHÔNG được dùng.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.ontology_mapping import doctype_mentions, generation_hint, load_ontology  # noqa: E402

ONTO = {"status": "approved", "doctypes": {
    "Payment application": {"meaning": "yearly aid application", "legal_terms": ["aid application", "payment claim"]},
    "Geo parcel document": {"meaning": "parcel declaration", "legal_terms": ["agricultural parcel"]},
    "Inspection": {"meaning": "on-the-spot checks", "legal_terms": ["on-the-spot check"]}}}


class TestOntologyMapping(unittest.TestCase):
    def test_mentions_by_legal_terms_plural_and_case(self) -> None:
        text = "Aid applications shall list all agricultural parcels of the holding."
        self.assertEqual(doctype_mentions(text, ONTO), ["Geo parcel document", "Payment application"])
        self.assertEqual(doctype_mentions("The Commission shall report.", ONTO), [])

    def test_hint_names_doctypes_and_keeps_all_activities_allowed(self) -> None:
        hint = generation_hint("On-the-spot checks shall cover 5% of beneficiaries.", ONTO)
        self.assertIn("'Inspection' (on-the-spot checks)", hint)
        self.assertIn("remain allowed", hint)
        self.assertEqual(generation_hint("The Commission shall report.", ONTO), "")

    def test_unapproved_ontology_not_loaded(self) -> None:
        tmp = Path(tempfile.mkdtemp()) / "o.json"
        tmp.write_text(json.dumps({**ONTO, "status": "draft"}), encoding="utf-8")
        self.assertIsNone(load_ontology(tmp))
        tmp.write_text(json.dumps(ONTO), encoding="utf-8")
        self.assertEqual(load_ontology(tmp)["status"], "approved")
        self.assertIsNone(load_ontology(tmp.with_name("missing.json")))

    def test_german_terms_used_for_german_clauses(self) -> None:
        onto = {**ONTO, "doctypes": {**ONTO["doctypes"], "Payment application": {
            **ONTO["doctypes"]["Payment application"], "legal_terms_de": ["Sammelantrag", "Sammelantrags"]}}}
        self.assertEqual(doctype_mentions("Der Sammelantrag ist bis zum 15. Mai zu stellen.", onto),
                         ["Payment application"])
        self.assertEqual(doctype_mentions("Änderungen des Sammelantrags", onto), ["Payment application"])

    def test_no_ontology_no_hint(self) -> None:
        self.assertEqual(generation_hint("Aid applications shall be lodged.", None), "")


if __name__ == "__main__":
    unittest.main()
