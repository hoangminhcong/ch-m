"""
Knowledge Graph 3 tầng dùng chung (Legal / Normative / Process).
"""

from .legal_graph_builder import build_legal_graph, build_legal_graph_file
from .schema import EdgeType, KGEdge, KGNode, KnowledgeGraph, NodeLabel

__all__ = [
    "EdgeType",
    "KGEdge",
    "KGNode",
    "KnowledgeGraph",
    "NodeLabel",
    "build_legal_graph",
    "build_legal_graph_file",
]
