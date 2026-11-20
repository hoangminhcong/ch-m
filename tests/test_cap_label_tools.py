"""
Công cụ gán nhãn CAP bằng nhiều AI (HUONG_DAN_GAN_NHAN_CAP.md, mục 10): chia đợt phiếu và đối chiếu nhãn giữa các AI.
Nhãn ở đây là NHÃN GIẢ cho test.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.compare_cap_labels import compare, render_draft, render_report  # noqa: E402
from scripts.split_cap_sheet import make_batches, render_batch, render_clause  # noqa: E402
from src.evaluation.cap_gold import parse_label_sheet  # noqa: E402

MAIL = "Payment application / Application / mail income"
PAY = "Payment application / Application / begin payment"
GAMMA = {"valid_activities": [MAIL, PAY], "activities_by_origin": {},
         "case_attributes": {"case:area": {"type": "Float", "samples": []}},
         "event_attributes": {"time:timestamp": {"type": "Timestamp", "samples": []}}}


def _rec(nid: str, text: str = "x", refs=()):
    return {"node_id": nid, "doc_id": "R809", "article_title": "t", "text": text, "has_numeric_bound": False,
            "round": 1, "referenced": list(refs)}


def _line(nid, obs="Có", cons=f"Existence({MAIL})", ref="Không", conf="Cao"):
    return (f"{nid}: **Quan sát được:** {obs} · **Ràng buộc mới:** {cons} · **Cần điều tham chiếu:** {ref} · "
            f"**Độ chắc chắn:** {conf} · **Lý do:** r")


class TestSplit(unittest.TestCase):
    def test_limits_by_items_and_size(self) -> None:
        recs = [_rec(f"R809:Art{i}") for i in range(1, 8)] + [_rec("R809:Art99", "y" * 5000)]
        batches = make_batches(recs, max_items=3, max_bytes=3000)
        self.assertEqual([len(b) for b in batches], [3, 3, 1, 1])  # khoản dài đứng riêng
        self.assertEqual([r["node_id"] for b in batches for r in b], [r["node_id"] for r in recs])  # giữ thứ tự

    def test_batch_has_answer_template_and_clause_blocks(self) -> None:
        ref = {"target": "R1307:Art4(1)", "kind": "external", "in_scope": True, "found": True, "text": "def"}
        page = render_batch([_rec("R809:Art1", refs=[ref]), _rec("R809:Art2")], 1, 5)
        self.assertIn("đợt 1/5", page)
        self.assertEqual(len(parse_label_sheet(page)), 2)  # mẫu trả lời đọc được ngay
        self.assertIn("Khoản được dẫn chiếu: <b>R1307:Art4(1)</b>", render_clause(_rec("R809:Art1", refs=[ref])))


class TestCompare(unittest.TestCase):
    ORDER = ["R1:Art1", "R1:Art2", "R1:Art3", "R1:Art4", "R1:Art5"]

    def setUp(self) -> None:
        a = "\n".join([_line("R1:Art1"),
                       _line("R1:Art2", cons=f"Response({MAIL} → {PAY}) ≤ 30 ngày | case:area > 1"),
                       _line("R1:Art3", obs="Không", cons="—", ref="—"),
                       _line("R1:Art4", ref="Có (ngày lấy từ Điều 5)"),
                       _line("R1:Art5", cons=f"Existence({MAIL})")])
        b = "\n".join([_line("R1:Art1", conf="TB"),  # khác độ chắc chắn: không tính bất đồng
                       _line("R1:Art2", cons=f"Response({MAIL} -> {PAY}) | area > 1,0 trong ≤ 30 days"),  # cùng nghĩa
                       _line("R1:Art3", obs="Có", cons=f"Existence({PAY})"),  # khác câu (1)
                       _line("R1:Art4", ref="Không"),  # khác Tier 4
                       _line("R1:Art5", cons="Existence(mail incom)")])  # ký hiệu lỗi → bất đồng
        self.res = compare({"claude": parse_label_sheet(a), "gemini": parse_label_sheet(b)}, self.ORDER, GAMMA,
                           spot_min=1, spot_frac=0.1)

    def test_semantic_constraint_match(self) -> None:
        self.assertEqual(self.res["agreed"], ["R1:Art1", "R1:Art2"])
        self.assertEqual(self.res["disagreed"], ["R1:Art3", "R1:Art4", "R1:Art5"])

    def test_statistics_and_spot_check(self) -> None:
        self.assertEqual(self.res["observable_agreement"], 0.8)
        self.assertEqual(len(self.res["spot_check"]), 1)
        self.assertTrue(set(self.res["spot_check"]) <= set(self.res["agreed"]))
        self.assertIn("claude vs gemini", self.res["kappa_observable"])

    def test_draft_is_readable_and_marks_review_items(self) -> None:
        draft = render_draft(self.res, self.ORDER)
        parsed = parse_label_sheet(draft)  # file nháp phải đọc được bằng bộ đọc phiếu
        self.assertEqual(parsed["R1:Art2"]["observable"], "yes")
        self.assertEqual(parsed["R1:Art3"]["observable"], "blank")  # bất đồng → người điền
        self.assertIn("# CẦN NGƯỜI QUYẾT (R1:Art5)", draft)
        self.assertIn(f"# KIỂM NGẪU NHIÊN ({self.res['spot_check'][0]})", draft)

    def test_report_shows_each_ai_and_notation_errors(self) -> None:
        md = render_report(self.res, {n: "law text" for n in self.ORDER})
        self.assertIn("### R1:Art5", md)
        self.assertIn("**gemini**", md)
        self.assertIn("⚠ LỖI: Existence(mail incom)", md)


if __name__ == "__main__":
    unittest.main()
