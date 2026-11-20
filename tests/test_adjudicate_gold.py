"""
Test cho scripts/adjudicate_gold.py: đọc nhãn của người gán và áp 3 điều chỉnh đã thống nhất
(gộp câu trùng, O_Sent gồm cả hai kênh, câu bẫy xét chính ràng buộc trong gold).
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.adjudicate_gold import (  # noqa: E402
    adjudicate,
    extract_constraint,
    parse_labels,
    parse_partb_labels,
)

RAW = """R01: **Quyết định:** SỬA · **Độ chắc chắn:** Cao · **Lý do:** abc. Ràng buộc mới: Precedence(W_Validate application → O_Accepted) (proxy: x).

R04: **Quyết định:** SỬA · **Độ chắc chắn:** Cao · **Lý do:** abc. Ràng buộc mới: Precedence(O_Sent (mail and online) → O_Accepted) (proxy: y).

R08: **Quyết định:** SỬA · **Độ chắc chắn:** TB · **Lý do:** abc. Ràng buộc mới: Precedence(W_Validate application → O_Accepted) (proxy: z).

R13: **Quyết định:** LOẠI · **Độ chắc chắn:** Cao · **Lý do:** phạm vi.

R22: **Quyết định:** BẪY · **Độ chắc chắn:** Cao · **Lý do:** thấu chi.

R26: **Quyết định:** SỬA · **Độ chắc chắn:** TB · **Lý do:** vẫn viết được ràng buộc hợp lệ Precedence(W_Validate application → O_Accepted).
"""
RULES = {
    "R01": {"article_id": "Article 8(1)", "is_trap": False},
    "R04": {"article_id": "Article 5(1)", "is_trap": False},
    "R08": {"article_id": "Article 8(1)", "is_trap": False},
    "R13": {"article_id": "Article 2(2)", "is_trap": False},
    "R22": {"article_id": "Article 18(2)", "is_trap": False},
    "R26": {"article_id": "Article 8(1)", "is_trap": True},
}


def setUpModule() -> None:
    """Bộ BPIC2017 đang tạm vô hiệu (src/datasets.py); mở lại: $env:NSAI_ENABLE_BPIC2017 = "1"."""
    from src.datasets import skip_module_unless_bpic2017

    skip_module_unless_bpic2017()


class TestParse(unittest.TestCase):
    def setUp(self) -> None:
        self.labels = parse_labels(RAW)

    def test_reads_every_rule(self) -> None:
        self.assertEqual(sorted(self.labels), ["R01", "R04", "R08", "R13", "R22", "R26"])

    def test_reads_decision_and_confidence(self) -> None:
        self.assertEqual(self.labels["R08"]["decision"], "SỬA")
        self.assertEqual(self.labels["R08"]["confidence"], "TB")
        self.assertEqual(self.labels["R22"]["decision"], "BẪY")

    def test_constraint_keeps_parentheses_inside_activity_names(self) -> None:
        self.assertEqual(self.labels["R04"]["constraint"], "Precedence(O_Sent (mail and online) → O_Accepted)")

    def test_constraint_only_from_explicit_marker(self) -> None:
        self.assertIsNone(self.labels["R26"]["constraint"])
        self.assertIsNone(self.labels["R13"]["constraint"])

    def test_extract_constraint_balanced(self) -> None:
        self.assertEqual(extract_constraint("x Ràng buộc mới: Absence(A (b)) (proxy)"), "Absence(A (b))")


class TestAdjudicate(unittest.TestCase):
    def setUp(self) -> None:
        self.result = adjudicate(parse_labels(RAW), RULES)
        self.final = self.result["rules"]

    def test_original_labels_are_preserved(self) -> None:
        self.assertEqual(self.final["R26"]["annotator"]["decision"], "SỬA")

    def test_trap_rule_judged_on_its_own_constraint(self) -> None:
        self.assertEqual(self.final["R26"]["final_decision"], "GIỮ")
        self.assertTrue(any("A3" in a for a in self.final["R26"]["adjustments"]))

    def test_o_sent_covers_both_channels(self) -> None:
        self.assertIn("O_Sent (online only)", self.final["R04"]["final_constraint"])
        self.assertTrue(any("A2" in a for a in self.final["R04"]["adjustments"]))

    def test_duplicates_merged_into_one_item(self) -> None:
        positives = [i for i in self.result["items"] if i["kind"] == "positive"]
        self.assertEqual(len(positives), 2)
        art8 = next(i for i in positives if i["article_id"] == "Article 8(1)")
        self.assertEqual(art8["source_rules"], ["R01", "R08"])

    def test_traps_and_exclusions(self) -> None:
        traps = sorted(r for i in self.result["items"] if i["kind"] == "trap" for r in i["source_rules"])
        self.assertEqual(traps, ["R22", "R26"])
        self.assertEqual(self.result["excluded"], ["R13"])


# ---------------------------------------------------------------- Phần B (61 khoản) + A4..A6
RAW_B = """Art5(1): **Quan sát được:** Có · **Ràng buộc mới:** Precedence(O_Sent (mail and online) → O_Accepted); Existence(O_Create Offer) với OfferedAmount > 0 · **Cần điều tham chiếu:** Không · **Độ chắc chắn:** Cao · **Lý do:** proxy.
Art5(6): **Quan sát được:** Không · **Ràng buộc mới:** — · **Cần điều tham chiếu:** — · **Độ chắc chắn:** Cao · **Lý do:** không biết nội dung cuộc gọi.
Art8(1): **Quan sát được:** Có · **Ràng buộc mới:** Precedence(W_Validate application → O_Accepted) · **Cần điều tham chiếu:** — · **Độ chắc chắn:** Cao · **Lý do:** proxy.
Art8(2): **Quan sát được:** Có · **Ràng buộc mới:** Precedence(W_Validate application → O_Accepted) · **Cần điều tham chiếu:** — · **Độ chắc chắn:** Trung bình · **Lý do:** Limit raise.
Art14(1): **Quan sát được:** Không · **Ràng buộc mới:** — · **Cần điều tham chiếu:** — · **Độ chắc chắn:** Cao · **Lý do:** không có sự kiện.
"""
RAW_A_WITH_R12 = RAW + """
R12: **Quyết định:** SỬA · **Độ chắc chắn:** TB · **Lý do:** abc. Ràng buộc mới: Precedence(W_Call after offers → O_Accepted) (proxy).
"""
RULES_WITH_R12 = {**RULES, "R12": {"article_id": "Article 5(6)", "is_trap": False}}
TEXTS = {"Art5(1)": "In good time before the consumer is bound (Directive 2002/65/EC) ...",
         "Art8(2)": "if the parties agree to change the total amount of credit ..."}


class TestParsePartB(unittest.TestCase):
    def setUp(self) -> None:
        self.b = parse_partb_labels(RAW_B)

    def test_reads_every_paragraph(self) -> None:
        self.assertEqual(sorted(self.b), ["Art14(1)", "Art5(1)", "Art5(6)", "Art8(1)", "Art8(2)"])

    def test_observable_and_confidence(self) -> None:
        self.assertTrue(self.b["Art8(2)"]["observable"])
        self.assertFalse(self.b["Art5(6)"]["observable"])
        self.assertEqual(self.b["Art8(2)"]["confidence"], "Trung bình")

    def test_splits_constraints_on_semicolon(self) -> None:
        self.assertEqual(self.b["Art5(1)"]["constraints"], [
            "Precedence(O_Sent (mail and online) → O_Accepted)",
            "Existence(O_Create Offer) với OfferedAmount > 0",
        ])
        self.assertEqual(self.b["Art5(6)"]["constraints"], [])


class TestPartBAdjustments(unittest.TestCase):
    def setUp(self) -> None:
        self.result = adjudicate(parse_labels(RAW_A_WITH_R12), RULES_WITH_R12,
                                 partb=parse_partb_labels(RAW_B), paragraph_texts=TEXTS)
        self.positives = {i["article_id"]: i for i in self.result["items"] if i["kind"] == "positive"}

    def test_a4_self_conflict_resolved_by_higher_confidence(self) -> None:
        r12 = self.result["rules"]["R12"]
        self.assertEqual(r12["annotator"]["decision"], "SỬA")      # nhãn gốc giữ nguyên
        self.assertEqual(r12["final_decision"], "BẪY")
        self.assertEqual(r12["kind"], "trap")
        self.assertTrue(any(a.startswith("A4") for a in r12["adjustments"]))
        self.assertNotIn("Article 5(6)", self.positives)

    def test_a5_threshold_not_in_law_is_dropped(self) -> None:
        dropped = self.result["dropped_constraints"]
        self.assertEqual([d["constraint"] for d in dropped], ["Existence(O_Create Offer) với OfferedAmount > 0"])
        self.assertTrue(dropped[0]["reason"].startswith("A5"))

    def test_partb_constraint_already_covered_is_not_duplicated(self) -> None:
        self.assertEqual(self.positives["Article 5(1)"]["source_rules"], ["R04"])

    def test_a6_new_paragraph_gets_scope_condition(self) -> None:
        art82 = self.positives["Article 8(2)"]
        self.assertEqual(art82["source_rules"], ["PartB:Art8(2)"])
        self.assertIn('case:ApplicationType == "Limit raise"', art82["constraint"])
        self.assertTrue(any(a.startswith("A6") for a in art82["adjustments"]))
        self.assertEqual(art82["confidence"], "Trung bình")

    def test_without_partb_behaviour_unchanged(self) -> None:
        old = adjudicate(parse_labels(RAW_A_WITH_R12), RULES_WITH_R12)
        self.assertEqual(old["rules"]["R12"]["final_decision"], "SỬA")


if __name__ == "__main__":
    unittest.main()
