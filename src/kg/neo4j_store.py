"""
T1.4 – Ghi KnowledgeGraph vào Neo4j.

- Mọi node mang nhãn chung `:KG` + nhãn riêng (VD `:KG:Paragraph`), khoá duy nhất `id`.
- Dùng truy vấn tham số + UNWIND theo lô (nhanh, an toàn) thay vì ghép chuỗi Cypher.
- Nhãn node / kiểu cạnh không thể truyền bằng tham số trong Cypher, nên chỉ chấp nhận
  các giá trị khai báo trong schema (chống Cypher injection).
"""

import os
from typing import Any, Dict, Iterable, Iterator, List, Sequence, TypeVar

from .schema import EdgeType, KGEdge, KGNode, KnowledgeGraph, NodeLabel

T = TypeVar("T")

ALLOWED_LABELS = frozenset(v for k, v in vars(NodeLabel).items() if k.isupper())
ALLOWED_EDGE_TYPES = frozenset(v for k, v in vars(EdgeType).items() if k.isupper())
DEFAULT_BATCH_SIZE = 1000
_PRIMITIVES = (str, int, float, bool)


def _chunks(items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _clean_props(props: Dict[str, Any]) -> Dict[str, Any]:
    """Bỏ giá trị None; Neo4j chỉ lưu được kiểu nguyên thuỷ hoặc list kiểu nguyên thuỷ."""
    cleaned: Dict[str, Any] = {}
    for key, value in props.items():
        if value is None:
            continue
        is_list = isinstance(value, list) and all(isinstance(v, _PRIMITIVES) for v in value)
        if not (isinstance(value, _PRIMITIVES) or is_list):
            raise ValueError(f"Thuộc tính '{key}' có kiểu {type(value).__name__} không lưu được vào Neo4j")
        cleaned[key] = value
    return cleaned


def _group(items: Iterable[T], key_of: Any, allowed: frozenset, kind: str) -> Dict[str, List[T]]:
    groups: Dict[str, List[T]] = {}
    for item in items:
        key = key_of(item)
        if key not in allowed:
            raise ValueError(f"{kind} không hợp lệ: {key!r}. Cho phép: {sorted(allowed)}")
        groups.setdefault(key, []).append(item)
    return groups


class Neo4jKGStore:
    def __init__(self, driver: Any, batch_size: int = DEFAULT_BATCH_SIZE, database: str = "") -> None:
        self.driver = driver
        self.batch_size = batch_size
        self.database = database

    @staticmethod
    def from_env() -> "Neo4jKGStore":
        """Kết nối theo biến môi trường NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD (.env)."""
        from dotenv import load_dotenv
        from neo4j import GraphDatabase

        load_dotenv()
        missing = [k for k in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD") if not os.getenv(k)]
        if missing:
            raise RuntimeError(f"Thiếu biến môi trường trong .env: {', '.join(missing)}")
        driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"])
        )
        driver.verify_connectivity()
        return Neo4jKGStore(driver)

    def _session(self) -> Any:
        return self.driver.session(database=self.database) if self.database else self.driver.session()

    def ensure_constraints(self) -> None:
        with self._session() as session:
            session.run("CREATE CONSTRAINT kg_id IF NOT EXISTS FOR (n:KG) REQUIRE n.id IS UNIQUE")

    def write_graph(self, graph: KnowledgeGraph) -> Dict[str, int]:
        """Ghi (MERGE) toàn bộ node rồi cạnh. Trả về số lượng đã ghi theo nhãn/kiểu."""
        node_groups = _group(graph.nodes, lambda n: n.label, ALLOWED_LABELS, "Nhãn node")
        edge_groups = _group(graph.edges, lambda e: e.type, ALLOWED_EDGE_TYPES, "Kiểu cạnh")
        counts: Dict[str, int] = {}
        with self._session() as session:
            for label, nodes in node_groups.items():
                counts[label] = self._write_nodes(session, label, nodes)
            for edge_type, edges in edge_groups.items():
                counts[edge_type] = self._write_edges(session, edge_type, edges)
        return counts

    def _write_nodes(self, session: Any, label: str, nodes: Sequence[KGNode]) -> int:
        query = f"UNWIND $rows AS row MERGE (n:KG:{label} {{id: row.id}}) SET n += row.props"
        for batch in _chunks(nodes, self.batch_size):
            session.run(query, rows=[{"id": n.id, "props": _clean_props(n.props)} for n in batch])
        return len(nodes)

    def _write_edges(self, session: Any, edge_type: str, edges: Sequence[KGEdge]) -> int:
        query = (
            "UNWIND $rows AS row "
            "MATCH (a:KG {id: row.source}) MATCH (b:KG {id: row.target}) "
            f"MERGE (a)-[r:{edge_type}]->(b) SET r += row.props"
        )
        for batch in _chunks(edges, self.batch_size):
            rows = [{"source": e.source, "target": e.target, "props": _clean_props(e.props)} for e in batch]
            session.run(query, rows=rows)
        return len(edges)

    def clear_labels(self, labels: Iterable[str]) -> None:
        """Xoá các node thuộc nhãn chỉ định (để nạp lại một tầng mà không đụng tầng khác)."""
        for label in labels:
            if label not in ALLOWED_LABELS:
                raise ValueError(f"Nhãn node không hợp lệ: {label!r}")
            with self._session() as session:
                session.run(f"MATCH (n:KG:{label}) DETACH DELETE n")

    def close(self) -> None:
        self.driver.close()
