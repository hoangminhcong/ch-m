"""
Metamodel (tầng M2) của Knowledge Graph — viết tay, đóng vai metamodel UML trong MDE.

  M2  metamodel này (lớp node, quan hệ được phép, thuộc tính bắt buộc, nguồn gốc của cạnh)
      + schema AST ràng buộc DECLARE (src/mde/constraint_ast.py)
  M1  đồ thị cụ thể: cap_legal_graph(_v2).json, de_legal_graph.json, bpic2018_process_graph.json; Γ;
      cầu nối cap_mapping_graph.json / de_mapping_graph.json (ontology loại giấy tờ đã duyệt + MAPS_TO) — cạnh của
      cầu nối trỏ vào node của đồ thị luật và đồ thị tiến trình, nên được kiểm trên HỢP của ba đồ thị
  M0  log sự kiện (hồ sơ / event)

Thế giới ĐÓNG: lớp / quan hệ / cặp (lớp nguồn, lớp đích) không khai báo là vi phạm. Metamodel KHÔNG được suy ra từ
đồ thị (vòng tròn: sẽ hợp thức hoá cả lỗi); `drift` chỉ liệt kê chỗ lệch để NGƯỜI quyết sửa metamodel hay bộ dựng.

Nguồn gốc (provenance) của mỗi quan hệ — mọi cạnh phải truy được về nguồn:
  structural   suy từ cấu trúc văn bản (mã khoản 'R1306:Art7(3)' thuộc Điều 'R1306:Art7')
  textual      trích từ chữ trong khoản; cạnh REFERS_TO mang `cited_as` (đích như đọc được)
  definitional khoản nguồn chính là khoản định nghĩa (= thuộc tính `source` của DefinedTerm)
  statistical  đếm trên log; cạnh mang `count`
  approved     chỉ từ ánh xạ miền đã được người duyệt; cạnh mang `approved_by`
  derived      do hệ thống sinh và kiểm (luật đã kiểm chứng, kết quả kiểm tập ràng buộc); mang `method` nếu là suy luận
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, List, Mapping, Optional, Set, Tuple

Check = Callable[[Any], bool]


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _is_bool(v: Any) -> bool:
    return isinstance(v, bool)


def _is_count(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def _is_ratio(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= v <= 1.0


def _is_years(v: Any) -> bool:
    return isinstance(v, list) and bool(v) and all(isinstance(y, int) and 1990 <= y <= 2100 for y in v)


def _any(_: Any) -> bool:
    return True


def _one_of(*allowed: str) -> Check:
    return lambda v: v in allowed


@dataclass(frozen=True)
class NodeClass:
    name: str
    layer: str
    required: Tuple[Tuple[str, Check], ...]
    optional: Tuple[Tuple[str, Check], ...] = ()
    doc: str = ""


@dataclass(frozen=True)
class Relation:
    name: str
    sources: FrozenSet[str]
    targets: FrozenSet[str]
    provenance: str
    required: Tuple[Tuple[str, Check], ...] = ()
    dangling_allowed_if_out_of_scope: bool = False  # đích ngoài bộ văn bản không có node — chỉ khi in_scope=False
    doc: str = ""


_PROVISION = frozenset({"Article", "Paragraph", "Annex"})
# kiểu thuộc tính của log (src/kg/process_graph_builder.py sinh đúng 4 kiểu này); Γ (src/mde/schema_from_kg.py)
# phải ánh xạ ĐỦ cả 4 — không kiểu nào rơi vào mặc định ngầm
ATTRIBUTE_TYPES = ("number", "string", "boolean", "datetime")
# danh mục ĐÓNG loại chuẩn tắc (khung chuẩn tắc, cấu hình N — src/symbolic/norm_frame.py đọc từ đây)
NORM_TYPES = ("action_order", "deadline", "prohibition", "content_requirement", "calculation", "organisational",
              "penalty", "definition")
_LEGAL_TEXT = (("title", _is_str), ("text", _is_str), ("has_numeric_bound", _is_bool))

NODE_CLASSES: Dict[str, NodeClass] = {c.name: c for c in (
    NodeClass("Article", "legal", (("doc_id", _is_str), ("in_scope", _is_bool)), _LEGAL_TEXT,
              "Điều; in_scope=False = node giữ chỗ cho đích dẫn chiếu chưa tách được / ngoài bộ (không có text)"),
    NodeClass("Paragraph", "legal", (("doc_id", _is_str), ("text", _is_str)),
              _LEGAL_TEXT + (("in_scope", _is_bool), ("years", _is_years), ("language", _is_str)),
              "Khoản; `years` = các năm của log mà phiên bản này có hiệu lực (tập Đức)"),
    NodeClass("Annex", "legal", (("doc_id", _is_str), ("in_scope", _is_bool)), _LEGAL_TEXT, "Phụ lục"),
    NodeClass("DefinedTerm", "legal",
              (("term", _is_str), ("definition", _is_str), ("source", _is_str), ("scope", _is_str)), (),
              "Thuật ngữ định nghĩa trong luật; `source` = khoản định nghĩa"),
    NodeClass("Activity", "process",
              (("name", _is_str), ("case_count", _is_count), ("event_count", _is_count), ("case_ratio", _is_ratio)),
              (("origin", _is_str),),
              "Activity của log (tên ghép như Γ dùng); `origin` = nhóm tiến trình khai báo sẵn (BPIC2017: "
              "Application / Offer / Workflow) — không có thì Γ lấy tiền tố tên ghép"),
    NodeClass("Attribute", "process",
              (("name", _is_str), ("level", _one_of("case", "event")), ("type", _one_of(*ATTRIBUTE_TYPES)),
               ("non_null_ratio", _is_ratio)),
              (("values", lambda v: isinstance(v, list)), ("min", _any), ("max", _any), ("distinct_count", _is_count)),
              "Thuộc tính hồ sơ / sự kiện; miền giá trị (values hoặc min–max) dùng cho kiểm C của Tầng 2"),
    # tầng Cầu nối (data/processed/*_mapping_graph.json): ontology loại giấy tờ ĐÃ DUYỆT (data/review/bpic2018_ontology.json)
    NodeClass("DocumentType", "bridge",
              (("name", _is_str), ("meaning", _is_str), ("confidence", _one_of("high", "medium", "low"))), (),
              "Loại giấy tờ của tiến trình (phần đầu tên activity ghép BPIC2018); nghĩa do người duyệt"),
    # tầng Chuẩn tắc (M2 Norm Extractor): khung chuẩn tắc LLM điền cho một khoản (cấu hình N), xuất bởi
    # src/kg/constraint_export.py — kể cả khi KHÔNG thành ràng buộc (loại không diễn đạt được → expressible=False)
    NodeClass("Norm", "normative",
              (("config", _is_str), ("clause", _is_str), ("norm_type", _one_of(*NORM_TYPES)), ("action", _is_str)),
              (("duty_bearer", _is_str), ("deadline", lambda v: v is None or _is_str(v)),
               ("observable_in_log", _is_bool), ("expressible", _is_bool),
               ("evidence", lambda v: isinstance(v, str))),
              "Chuẩn tắc của một khoản: loại (danh mục đóng), hành động và thời hạn trích nguyên văn"),
    NodeClass("VerifiedConstraint", "constraint",
              (("config", _is_str), ("clause", _is_str), ("template", _is_str), ("decl", _is_str)),
              (("vacuous", lambda v: v is None or isinstance(v, bool)),
               ("mass_violation_ratio", lambda v: v is None or _is_ratio(v))),
              "Ràng buộc đã qua mọi lớp kiểm (src/kg/constraint_export.py); cấu trúc bên trong = schema AST"),
)}

RELATIONS: Dict[str, Relation] = {r.name: r for r in (
    Relation("HAS_PARAGRAPH", frozenset({"Article"}), frozenset({"Paragraph"}), "structural"),
    Relation("REFERS_TO", _PROVISION, _PROVISION, "textual",
             # kind: EU — internal / external; tập Đức — internal (cùng luật) / national (luật Đức khác) / eu
             (("cited_as", _is_str), ("kind", _one_of("internal", "external", "national", "eu")),
              ("in_scope", _is_bool)),
             dangling_allowed_if_out_of_scope=True),
    Relation("DEFINES", frozenset({"Article", "Paragraph"}), frozenset({"DefinedTerm"}), "definitional"),
    Relation("USES_TERM", frozenset({"Article", "Paragraph"}), frozenset({"DefinedTerm"}), "textual"),
    Relation("DIRECTLY_FOLLOWS", frozenset({"Activity"}), frozenset({"Activity"}), "statistical",
             (("count", _is_count),)),
    Relation("HAS_ATTRIBUTE", frozenset({"Activity"}), frozenset({"Attribute"}), "statistical",
             (("count", _is_count), ("non_null_ratio", _is_ratio))),
    # nối hai tầng (đăng ký trước v2, thành phần 9): khoản luật → loại giấy tờ, khi khoản nhắc thuật ngữ pháp lý
    # của loại đó trong ontology ĐÃ DUYỆT; `terms` = thuật ngữ khớp (truy được vì sao có cạnh)
    Relation("MAPS_TO", _PROVISION, frozenset({"DocumentType"}), "approved",
             (("approved_by", _is_str), ("terms", lambda v: isinstance(v, list) and bool(v)
                                         and all(_is_str(t) for t in v)))),
    Relation("OF_DOCTYPE", frozenset({"Activity"}), frozenset({"DocumentType"}), "structural",
             doc="activity thuộc loại giấy tờ = phần đầu tên ghép 'loại giấy tờ / tiến trình con / hành động'"),
    Relation("RELATED_DOCTYPE", frozenset({"DocumentType"}), frozenset({"DocumentType"}), "approved",
             (("kind", _is_str), ("confidence", _one_of("high", "medium", "low")), ("approved_by", _is_str))),
    # tầng Ràng buộc (luật đã kiểm chứng) — nguồn gốc 'derived': do hệ thống sinh và kiểm, truy về khoản + activity
    Relation("GROUNDED_IN", frozenset({"VerifiedConstraint", "Norm"}), _PROVISION, "derived"),
    Relation("FORMALIZED_AS", frozenset({"Norm"}), frozenset({"VerifiedConstraint"}), "derived",
             doc="chuẩn tắc → ràng buộc DECLARE đã qua mọi lớp kiểm hình thức hoá nó"),
    Relation("ON", frozenset({"VerifiedConstraint"}), frozenset({"Activity"}), "derived"),
    Relation("CONFLICTS_WITH", frozenset({"VerifiedConstraint"}), frozenset({"VerifiedConstraint"}), "derived",
             (("kind", _one_of("CONFLICT", "CONFLICT_IF_ACTIVATED")), ("method", _is_str))),
    Relation("IMPLIES", frozenset({"VerifiedConstraint"}), frozenset({"VerifiedConstraint"}), "derived",
             (("method", _is_str),)),
    Relation("DUPLICATE_OF", frozenset({"VerifiedConstraint"}), frozenset({"VerifiedConstraint"}), "derived"),
)}


# ------------------------------------------------------------------------------ kiểm tuân thủ


def _check_props(where: str, props: Mapping[str, Any], required: Tuple[Tuple[str, Check], ...],
                 optional: Tuple[Tuple[str, Check], ...], closed: bool) -> List[str]:
    out = []
    for key, ok in required:
        if key not in props:
            out.append(f"{where}: thiếu thuộc tính bắt buộc '{key}'")
        elif not ok(props[key]):
            out.append(f"{where}: '{key}' sai kiểu / miền = {props[key]!r}")
    for key, ok in optional:
        if key in props and not ok(props[key]):
            out.append(f"{where}: '{key}' sai kiểu / miền = {props[key]!r}")
    if closed:
        known = {k for k, _ in required} | {k for k, _ in optional}
        out += [f"{where}: thuộc tính không khai báo '{k}'" for k in sorted(set(props) - known)]
    return out


def _node_violations(n: Mapping[str, Any]) -> List[str]:
    cls = NODE_CLASSES.get(n["label"])
    where = f"node {n['id']} [{n['label']}]"
    if cls is None:
        return [f"{where}: lớp không có trong metamodel"]
    props = n.get("props", {})
    out = _check_props(where, props, cls.required, cls.optional, closed=True)
    if cls.name in ("Article", "Annex") and props.get("in_scope") is True and not props.get("title"):
        out.append(f"{where}: in_scope=True nhưng không có title (chỉ node giữ chỗ in_scope=False được rỗng)")
    return out


def _edge_violations(e: Mapping[str, Any], labels: Mapping[str, str],
                     nodes: Mapping[str, Mapping[str, Any]]) -> List[str]:
    rel = RELATIONS.get(e["type"])
    where = f"cạnh {e['type']} {e['source']} -> {e['target']}"
    if rel is None:
        return [f"{where}: quan hệ không có trong metamodel"]
    props = e.get("props", {})
    out = _check_props(where, props, rel.required, (), closed=False)
    src, tgt = labels.get(e["source"]), labels.get(e["target"])
    if src is None:
        out.append(f"{where}: node nguồn không tồn tại")
    elif src not in rel.sources:
        out.append(f"{where}: lớp nguồn không được phép = {src}")
    if tgt is None:
        if not (rel.dangling_allowed_if_out_of_scope and props.get("in_scope") is False):
            out.append(f"{where}: node đích không tồn tại (chỉ được phép khi in_scope=False)")
    elif tgt not in rel.targets:
        out.append(f"{where}: lớp đích không được phép = {tgt}")
    if rel.provenance == "definitional" and tgt is not None \
            and nodes[e["target"]].get("props", {}).get("source") != e["source"]:
        out.append(f"{where}: nguồn gốc sai — khoản nguồn khác `source` của thuật ngữ")
    return out


def validate_graph(graph: Mapping[str, Any]) -> List[str]:
    """Mọi vi phạm metamodel của một đồ thị dạng JSON (rỗng = tuân thủ)."""
    nodes = {n["id"]: n for n in graph["nodes"]}
    labels = {i: n["label"] for i, n in nodes.items()}
    out = [v for n in graph["nodes"] for v in _node_violations(n)]
    return out + [v for e in graph["edges"] for v in _edge_violations(e, labels, nodes)]


def observed_triples(graph: Mapping[str, Any]) -> Dict[Tuple[str, str, str], int]:
    """(lớp nguồn, quan hệ, lớp đích) có thật trong đồ thị, kèm số cạnh ('?' = đích không có node)."""
    labels = {n["id"]: n["label"] for n in graph["nodes"]}
    out: Dict[Tuple[str, str, str], int] = {}
    for e in graph["edges"]:
        key = (labels.get(e["source"], "?"), e["type"], labels.get(e["target"], "?"))
        out[key] = out.get(key, 0) + 1
    return out


def drift(graphs: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """Chỗ lệch giữa metamodel và các đồ thị: bộ ba có thật nhưng không khai báo; quan hệ / lớp khai báo nhưng
    không đồ thị nào dùng (có thể là dư, hoặc chưa được dựng — VD tầng Ràng buộc khi chưa xuất luật đã kiểm)."""
    seen: Dict[Tuple[str, str, str], int] = {}
    used_labels: Set[str] = set()
    for g in graphs.values():
        for k, v in observed_triples(g).items():
            seen[k] = seen.get(k, 0) + v
        used_labels |= {n["label"] for n in g["nodes"]}
    undeclared = {k: v for k, v in seen.items() if k[1] not in RELATIONS or k[0] not in RELATIONS[k[1]].sources
                  or (k[2] != "?" and k[2] not in RELATIONS[k[1]].targets)}
    return {"undeclared_triples": undeclared,
            "unused_relations": sorted(set(RELATIONS) - {k[1] for k in seen}),
            "unused_classes": sorted(set(NODE_CLASSES) - used_labels)}


def summary(violations: List[str], limit: Optional[int] = 10) -> str:
    """Tóm tắt theo loại vi phạm (bỏ mã node) + vài ví dụ."""
    kinds: Dict[str, int] = {}
    for v in violations:
        kind = v.split(": ", 1)[1].split(" = ")[0]
        kinds[kind] = kinds.get(kind, 0) + 1
    lines = [f"  {n:6d} × {k}" for k, n in sorted(kinds.items(), key=lambda x: -x[1])]
    return "\n".join(lines + [f"    VD: {v}" for v in violations[:limit or 0]])
