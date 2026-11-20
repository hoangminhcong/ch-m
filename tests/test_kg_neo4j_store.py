"""
Test cho T1.4 – Neo4jKGStore: ghi KnowledgeGraph vào Neo4j bằng truy vấn tham số + UNWIND theo lô.
Dùng driver giả để kiểm tra câu truy vấn sinh ra mà không cần Neo4j thật.
"""

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.kg.neo4j_store import Neo4jKGStore  # noqa: E402
from src.kg.schema import EdgeType, KGEdge, KGNode, KnowledgeGraph, NodeLabel  # noqa: E402


class FakeSession:
    def __init__(self, log: List[Tuple[str, Dict[str, Any]]]) -> None:
        self.log = log

    def run(self, query: str, **params: Any) -> None:
        self.log.append((query, params))

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


class FakeDriver:
    def __init__(self) -> None:
        self.log: List[Tuple[str, Dict[str, Any]]] = []

    def session(self, **_: Any) -> FakeSession:
        return FakeSession(self.log)


def _graph(n_paragraphs: int = 3) -> KnowledgeGraph:
    nodes = [KGNode("Art14", NodeLabel.ARTICLE, {"number": 14, "title": "Right of withdrawal"})]
    edges = []
    for i in range(1, n_paragraphs + 1):
        nodes.append(KGNode(f"Art14({i})", NodeLabel.PARAGRAPH, {"text": f"p{i}", "note": None}))
        edges.append(KGEdge("Art14", f"Art14({i})", EdgeType.HAS_PARAGRAPH))
    return KnowledgeGraph().merge(nodes, edges)


class TestNeo4jKGStore(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = FakeDriver()
        self.store = Neo4jKGStore(self.driver, batch_size=2)

    def test_creates_uniqueness_constraint(self) -> None:
        self.store.ensure_constraints()
        self.assertTrue(any("REQUIRE n.id IS UNIQUE" in q for q, _ in self.driver.log))

    def test_writes_nodes_with_shared_kg_label_and_parameters(self) -> None:
        self.store.write_graph(_graph(1))
        node_queries = [(q, p) for q, p in self.driver.log if "MERGE (n:KG" in q]
        self.assertTrue(any(":Article" in q for q, _ in node_queries))
        rows = [r for _, p in node_queries for r in p["rows"]]
        self.assertIn({"id": "Art14", "props": {"number": 14, "title": "Right of withdrawal"}}, rows)

    def test_drops_none_properties(self) -> None:
        self.store.write_graph(_graph(1))
        rows = [r for q, p in self.driver.log if ":Paragraph" in q for r in p["rows"]]
        self.assertEqual(rows[0]["props"], {"text": "p1"})

    def test_batches_rows(self) -> None:
        self.store.write_graph(_graph(3))
        para_batches = [p["rows"] for q, p in self.driver.log if ":Paragraph" in q]
        self.assertEqual([len(b) for b in para_batches], [2, 1])

    def test_writes_edges_by_type_after_nodes(self) -> None:
        self.store.write_graph(_graph(2))
        queries = [q for q, _ in self.driver.log]
        edge_idx = next(i for i, q in enumerate(queries) if ":HAS_PARAGRAPH" in q)
        last_node_idx = max(i for i, q in enumerate(queries) if "MERGE (n:KG" in q)
        self.assertGreater(edge_idx, last_node_idx)

    def test_rejects_unknown_label_to_prevent_cypher_injection(self) -> None:
        bad = KnowledgeGraph().merge([KGNode("x", "Article) DETACH DELETE (m", {})], [])
        with self.assertRaises(ValueError):
            self.store.write_graph(bad)

    def test_rejects_unknown_edge_type(self) -> None:
        bad = KnowledgeGraph().merge(
            [KGNode("a", NodeLabel.ARTICLE), KGNode("b", NodeLabel.ARTICLE)],
            [KGEdge("a", "b", "HACK]->() DELETE x//")],
        )
        with self.assertRaises(ValueError):
            self.store.write_graph(bad)


if __name__ == "__main__":
    unittest.main()
