"""
Test cho M3 Process Graph Builder (TN3): dựng tầng Tiến trình của KG ở mức lược đồ từ event log.
Tầng này đóng vai trò "mô hình miền" (thay sơ đồ UML) cho bước kiểm chứng MDE.
"""

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.process_graph_builder import (  # noqa: E402
    activity_node_id,
    attribute_node_id,
    build_process_graph,
    with_composite_activity,
)
from src.kg.schema import EdgeType, NodeLabel  # noqa: E402

PARQUET_PATH = PROJECT_ROOT / "data" / "interim" / "bpic2017_events.parquet"


def _toy_log() -> pd.DataFrame:
    """2 hồ sơ. C1: Create -> Offer -> Offer -> Accept ; C2: Create -> Deny. (cố ý xáo thứ tự dòng)"""
    rows = [
        ("C1", "O_Create Offer", "2016-01-01 10:00", "Offer", 5000.0, None, "Car", 6000.0),
        ("C1", "A_Create Application", "2016-01-01 09:00", "Application", None, None, "Car", 6000.0),
        ("C2", "A_Create Application", "2016-01-02 09:00", "Application", None, None, "Home", 900.0),
        ("C1", "O_Create Offer", "2016-01-01 11:00", "Offer", 4000.0, 700.0, "Car", 6000.0),
        ("C1", "O_Accepted", "2016-01-03 09:00", "Offer", None, None, "Car", 6000.0),
        ("C2", "A_Denied", "2016-01-02 10:00", "Application", None, None, "Home", 900.0),
    ]
    df = pd.DataFrame(rows, columns=[
        "case:concept:name", "concept:name", "time:timestamp", "EventOrigin",
        "OfferedAmount", "CreditScore", "case:LoanGoal", "case:RequestedAmount",
    ])
    df["time:timestamp"] = pd.to_datetime(df["time:timestamp"], utc=True)
    df["EventID"] = [f"E{i}" for i in range(len(df))]  # cột kỹ thuật, không được thành Attribute
    return df


class TestProcessGraphToy(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = build_process_graph(_toy_log())
        self.nodes = self.graph.node_index()

    def test_graph_is_referentially_valid(self) -> None:
        self.assertEqual(self.graph.validate(), [])

    def test_one_activity_node_per_activity_with_counts(self) -> None:
        acts = self.graph.nodes_with_label(NodeLabel.ACTIVITY)
        self.assertEqual(len(acts), 4)
        offer = self.nodes[activity_node_id("O_Create Offer")].props
        self.assertEqual(offer["event_count"], 2)
        self.assertEqual(offer["case_count"], 1)
        self.assertAlmostEqual(offer["case_ratio"], 0.5)
        self.assertEqual(offer["origin"], "Offer")

    def test_directly_follows_respects_time_order_within_case(self) -> None:
        df_edges = {(e.source, e.target): e.props["count"]
                    for e in self.graph.edges_of_type(EdgeType.DIRECTLY_FOLLOWS)}
        create, offer = activity_node_id("A_Create Application"), activity_node_id("O_Create Offer")
        self.assertEqual(df_edges[(create, offer)], 1)
        self.assertEqual(df_edges[(offer, offer)], 1)  # vòng lặp: 2 offer liên tiếp
        self.assertEqual(df_edges[(offer, activity_node_id("O_Accepted"))], 1)
        self.assertEqual(df_edges[(create, activity_node_id("A_Denied"))], 1)
        self.assertEqual(len(df_edges), 4)  # không có cạnh nối giữa hai hồ sơ khác nhau

    def test_attribute_nodes_skip_technical_columns(self) -> None:
        names = {n.props["name"] for n in self.graph.nodes_with_label(NodeLabel.ATTRIBUTE)}
        self.assertEqual(names, {"OfferedAmount", "CreditScore", "case:LoanGoal", "case:RequestedAmount"})
        self.assertNotIn(attribute_node_id("EventID"), self.nodes)

    def test_attribute_level_type_and_range(self) -> None:
        amount = self.nodes[attribute_node_id("OfferedAmount")].props
        self.assertEqual(amount["level"], "event")
        self.assertEqual(amount["type"], "number")
        self.assertEqual((amount["min"], amount["max"]), (4000.0, 5000.0))
        goal = self.nodes[attribute_node_id("case:LoanGoal")].props
        self.assertEqual(goal["level"], "case")
        self.assertEqual(goal["type"], "string")
        self.assertEqual(sorted(goal["values"]), ["Car", "Home"])

    def test_has_attribute_records_where_value_is_present(self) -> None:
        has = {(e.source, e.target): e.props
               for e in self.graph.edges_of_type(EdgeType.HAS_ATTRIBUTE)}
        offer = activity_node_id("O_Create Offer")
        self.assertEqual(has[(offer, attribute_node_id("OfferedAmount"))]["non_null_ratio"], 1.0)
        self.assertEqual(has[(offer, attribute_node_id("CreditScore"))]["non_null_ratio"], 0.5)
        # A_Denied không mang OfferedAmount -> không có cạnh
        self.assertNotIn((activity_node_id("A_Denied"), attribute_node_id("OfferedAmount")), has)
        # thuộc tính mức hồ sơ không tạo cạnh HAS_ATTRIBUTE (có ở mọi activity)
        self.assertFalse(any(t == attribute_node_id("case:LoanGoal") for _, t in has))

    def test_missing_required_column_raises(self) -> None:
        with self.assertRaises(KeyError):
            build_process_graph(_toy_log().drop(columns=["time:timestamp"]))


from src.datasets import skip_unless_bpic2017  # noqa: E402  (bộ BPIC2017 đang tạm vô hiệu)


@skip_unless_bpic2017
@unittest.skipUnless(PARQUET_PATH.exists(), "cần data/interim/bpic2017_events.parquet")
class TestProcessGraphRealLog(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = build_process_graph(pd.read_parquet(PARQUET_PATH))
        cls.nodes = cls.graph.node_index()

    def test_has_26_activities(self) -> None:
        self.assertEqual(len(self.graph.nodes_with_label(NodeLabel.ACTIVITY)), 26)

    def test_every_case_starts_with_create_application(self) -> None:
        props = self.nodes[activity_node_id("A_Create Application")].props
        self.assertEqual(props["case_count"], 31509)

    def test_real_graph_is_valid(self) -> None:
        self.assertEqual(self.graph.validate(), [])


class TestSplitLog(unittest.TestCase):
    """BPIC2018: tên activity ghép 'loại giấy tờ / tiểu quy trình / hành động'; bảng hồ sơ tách riêng."""

    def setUp(self) -> None:
        ts = pd.to_datetime(["2015-05-01", "2015-05-02", "2015-05-03"], utc=True)
        self.events = pd.DataFrame({
            "case:concept:name": ["C1", "C1", "C2"],
            "concept:name": ["begin editing", "begin editing", "mail income"],
            "time:timestamp": ts,
            "doctype": ["Payment application", "Parcel document", "Payment application"],
            "subprocess": ["Application", "Main", None],
            "activity": ["begin editing", "begin editing", "mail income"],
            "success": [True, True, False],
        })
        self.cases = pd.DataFrame({
            "case:concept:name": ["C1", "C2"],
            "case:young farmer": [True, False],
            "case:area": [12.5, None],
        })

    def test_composite_activity_names(self) -> None:
        df = with_composite_activity(self.events)
        self.assertEqual(list(df["concept:name"]), [
            "Payment application / Application / begin editing",
            "Parcel document / Main / begin editing",
            "Payment application / mail income",
        ])

    def test_composite_drops_part_columns_and_keeps_input(self) -> None:
        df = with_composite_activity(self.events)
        self.assertFalse({"doctype", "subprocess", "activity"} & set(df.columns))
        self.assertIn("doctype", self.events.columns)  # không sửa bảng gốc

    def test_case_attributes_from_separate_table(self) -> None:
        g = build_process_graph(with_composite_activity(self.events), cases=self.cases)
        area = g.node_index()[attribute_node_id("case:area")].props
        self.assertEqual(area["level"], "case")
        self.assertEqual(area["non_null_ratio"], 0.5)  # tính trên 2 hồ sơ, không phải 3 event
        self.assertIn(attribute_node_id("case:young farmer"), g.node_index())
        self.assertNotIn(attribute_node_id("case:concept:name"), g.node_index())

    def test_without_cases_behaviour_unchanged(self) -> None:
        g = build_process_graph(with_composite_activity(self.events))
        self.assertNotIn(attribute_node_id("case:area"), g.node_index())


if __name__ == "__main__":
    unittest.main()
