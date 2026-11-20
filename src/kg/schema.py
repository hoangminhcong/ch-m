"""
Schema của Knowledge Graph 3 tầng dùng chung (Legal / Normative / Process).

Mọi module (M1–M10) đọc và ghi KG thông qua các kiểu dữ liệu bất biến ở đây,
nên KG có thể xuất ra JSON (chạy offline, không cần Neo4j) hoặc nạp vào Neo4j.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Tuple


class NodeLabel:
    """Nhãn node. Lớp nào được phép, thuộc tính bắt buộc, quan hệ giữa các lớp: xem METAMODEL src/kg/metamodel.py
    (kiểm bằng scripts/check_kg_metamodel.py). Nhãn đánh dấu 'dự trữ' chưa có trong metamodel → node mang nhãn đó
    bị coi là vi phạm cho tới khi được khai báo."""

    # Tầng Pháp lý
    ARTICLE = "Article"
    PARAGRAPH = "Paragraph"
    ANNEX = "Annex"  # Phụ lục (bộ CAP, kiểm toán đợt 2 F-ANNEX)
    DEFINED_TERM = "DefinedTerm"  # v2 (src/kg/legal_enrichment.py)
    LEGAL_CONCEPT = "LegalConcept"  # dự trữ (kế hoạch M2 cũ, chưa dựng)
    # Tầng Chuẩn tắc (src/kg/constraint_export.py, khung chuẩn tắc của cấu hình N)
    NORM = "Norm"
    CONSTRAINT = "DeclareConstraint"  # dự trữ (tên cũ; ràng buộc đã kiểm dùng VerifiedConstraint)
    # Tầng Ràng buộc (src/kg/constraint_export.py)
    VERIFIED_CONSTRAINT = "VerifiedConstraint"
    # Tầng Quy trình
    ACTIVITY = "Activity"
    ATTRIBUTE = "Attribute"
    # Tầng Cầu nối (src/kg/mapping_graph_builder.py, ontology loại giấy tờ đã duyệt)
    DOCUMENT_TYPE = "DocumentType"


class EdgeType:
    """Kiểu cạnh giữa các node — cặp (lớp nguồn, lớp đích) được phép: METAMODEL src/kg/metamodel.py."""

    HAS_PARAGRAPH = "HAS_PARAGRAPH"  # Article -> Paragraph
    REFERS_TO = "REFERS_TO"  # Article | Paragraph | Annex -> Article | Paragraph | Annex
    DEFINES = "DEFINES"  # Article | Paragraph -> DefinedTerm
    USES_TERM = "USES_TERM"  # Article | Paragraph -> DefinedTerm (v2)
    MENTIONS = "MENTIONS"  # dự trữ (chưa dựng)
    GROUNDED_IN = "GROUNDED_IN"  # Norm | VerifiedConstraint -> Article | Paragraph | Annex
    FORMALIZED_AS = "FORMALIZED_AS"  # Norm -> VerifiedConstraint
    ON = "ON"  # VerifiedConstraint -> Activity
    CONFLICTS_WITH = "CONFLICTS_WITH"  # VerifiedConstraint -> VerifiedConstraint (kiểm tập ràng buộc)
    IMPLIES = "IMPLIES"  # VerifiedConstraint -> VerifiedConstraint
    DUPLICATE_OF = "DUPLICATE_OF"  # VerifiedConstraint -> VerifiedConstraint
    MAPS_TO = "MAPS_TO"  # Article | Paragraph | Annex -> DocumentType, chỉ từ ontology đã duyệt (mang `terms`)
    OF_DOCTYPE = "OF_DOCTYPE"  # Activity -> DocumentType (phần đầu tên activity ghép)
    RELATED_DOCTYPE = "RELATED_DOCTYPE"  # DocumentType -> DocumentType (quan hệ đã duyệt trong ontology)
    DIRECTLY_FOLLOWS = "DIRECTLY_FOLLOWS"  # Activity -> Activity (B xảy ra ngay sau A trong một hồ sơ)
    HAS_ATTRIBUTE = "HAS_ATTRIBUTE"  # Activity -> Attribute (event của activity mang giá trị thuộc tính)


@dataclass(frozen=True)
class KGNode:
    id: str
    label: str
    props: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "label": self.label, "props": dict(self.props)}


@dataclass(frozen=True)
class KGEdge:
    source: str
    target: str
    type: str
    props: Dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> Tuple[str, str, str]:
        return (self.source, self.target, self.type)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "props": dict(self.props),
        }


@dataclass(frozen=True)
class KnowledgeGraph:
    """Đồ thị bất biến. Dùng `merge` để tạo đồ thị mới thay vì sửa tại chỗ."""

    nodes: Tuple[KGNode, ...] = ()
    edges: Tuple[KGEdge, ...] = ()

    def node_index(self) -> Dict[str, KGNode]:
        return {n.id: n for n in self.nodes}

    def nodes_with_label(self, label: str) -> List[KGNode]:
        return [n for n in self.nodes if n.label == label]

    def edges_of_type(self, edge_type: str) -> List[KGEdge]:
        return [e for e in self.edges if e.type == edge_type]

    def out_edges(self, node_id: str, edge_type: str = "") -> List[KGEdge]:
        return [
            e
            for e in self.edges
            if e.source == node_id and (not edge_type or e.type == edge_type)
        ]

    def merge(self, nodes: Iterable[KGNode], edges: Iterable[KGEdge]) -> "KnowledgeGraph":
        """Trả về đồ thị mới; node/cạnh trùng khoá thì bản mới ghi đè bản cũ."""
        node_map = {n.id: n for n in self.nodes}
        node_map.update({n.id: n for n in nodes})
        edge_map = {e.key: e for e in self.edges}
        edge_map.update({e.key: e for e in edges})
        return KnowledgeGraph(nodes=tuple(node_map.values()), edges=tuple(edge_map.values()))

    def validate(self) -> List[str]:
        """Liệt kê cạnh trỏ tới node không tồn tại (rỗng nghĩa là hợp lệ)."""
        ids = {n.id for n in self.nodes}
        return [
            f"{e.type}: {e.source} -> {e.target}"
            for e in self.edges
            if e.source not in ids or e.target not in ids
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "KnowledgeGraph":
        return KnowledgeGraph(
            nodes=tuple(KGNode(n["id"], n["label"], dict(n.get("props", {}))) for n in data["nodes"]),
            edges=tuple(
                KGEdge(e["source"], e["target"], e["type"], dict(e.get("props", {})))
                for e in data["edges"]
            ),
        )
