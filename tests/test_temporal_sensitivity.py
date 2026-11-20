"""A5 / B5 — phân tích độ nhạy theo hiệu lực thời gian (score_cap.temporal_sensitivity): chấm lại CAP sau khi bỏ các
khoản có sửa đổi nội dung 2015–2017 (data/review/cap_temporal_versions.json, scripts/check_cap_versions.py)."""

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.score_cap import TEMPORAL, temporal_sensitivity  # noqa: E402

GOLD = {"status": "approved", "clauses": {
    "T1": {"kind": "trap", "gold": []}, "T2": {"kind": "trap", "gold": []}, "T3": {"kind": "trap", "gold": []}}}
PREDS = {"Y": {"T1": {"outcome": "BASELESS"}, "T2": {"outcome": "RULE", "ast": {}}, "T3": {"outcome": "BASELESS"}},
         "X": {"T1": {"outcome": "BASELESS"}, "T2": {"outcome": "BASELESS"}, "T3": {"outcome": "BASELESS"}}}


class TestTemporalSensitivity(unittest.TestCase):
    def test_amended_clauses_are_left_out_of_every_config_and_pair(self) -> None:
        sens = temporal_sensitivity(GOLD, PREDS, ["T2", "R9:Art1"])
        self.assertEqual(sens["excluded"], ["T2"])  # chỉ khoản có trong gold
        self.assertEqual(sens["n_scored"], 2)
        self.assertEqual(sens["overall"]["Y"]["correct"], 2)
        self.assertEqual(sens["paired"]["TN6 X vs Y (mọi khoản)"]["n"], 2)

    def test_gold_not_modified(self) -> None:
        temporal_sensitivity(GOLD, PREDS, ["T2"])
        self.assertIn("T2", GOLD["clauses"])

    def test_version_file_lists_only_sheet_clauses(self) -> None:
        if not TEMPORAL.exists():
            self.skipTest("chưa chạy check_cap_versions.py")
        data = json.loads(TEMPORAL.read_text(encoding="utf-8"))
        sheet = {c["node_id"] for c in json.loads(
            (PROJECT_ROOT / "data" / "review" / "cap_item_candidates.json").read_text(encoding="utf-8"))}
        self.assertLessEqual(set(data["amended"]) | set(data["digits_only"]), sheet)
        for rec in data["amended"].values():
            self.assertLessEqual(set(rec["years"]), {2015, 2016, 2017})


if __name__ == "__main__":
    unittest.main()
