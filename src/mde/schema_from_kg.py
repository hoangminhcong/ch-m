"""
Bước 0 của MDE trên KG: dựng môi trường kiểu Γ (Tầng 2) từ tầng Tiến trình của Knowledge Graph.

Trước đây Γ đọc process_schema.json, sinh bởi một script riêng cho BPIC2017 (extract_process_schema.py).
Module này lấy Γ trực tiếp từ KG (process_graph_builder.py, TN3) nên dùng được cho mọi log đã dựng KG
(BPIC2017, BPIC2018) — KG đóng vai trò mô hình miền thay cho sơ đồ lớp UML của OVAS.

Đầu ra cùng định dạng process_schema mà ProcessTypingEnvironment, rag_retriever, synthesis_loop đang đọc:
  valid_activities, activities_by_origin, case_attributes, event_attributes, frequent_transitions
  (+ dataset, source="knowledge_graph"). Không có start/end_activities: KG mức lược đồ không lưu chúng
  và không module nào ngoài extract_process_schema.py dùng tới.
"""

from typing import Any, Dict, List, Mapping

from src.kg.metamodel import ATTRIBUTE_TYPES, NODE_CLASSES, RELATIONS, summary, validate_graph

COMPOSITE_SEP = " / "  # tên activity ghép của BPIC2018: 'loại giấy tờ / tiến trình con / hành động'
DEFAULT_ORIGIN = "Process"
TIME_ATTRIBUTE = "time:timestamp"
MAX_TRANSITIONS = 30
# Kiểu thuộc tính của metamodel (M2) -> tên kiểu mà Γ (typing_environment.py) dùng. Phải phủ ĐỦ ATTRIBUTE_TYPES.
GAMMA_TYPES = {"number": "Float", "string": "String", "boolean": "Boolean", "datetime": "Timestamp"}
# Hợp đồng với metamodel: lớp / quan hệ / thuộc tính mà phép chiếu KG → Γ đọc. Mọi tên ở đây phải được metamodel
# khai báo (kiểm khi gọi gamma_from_kg và trong tests/test_schema_from_kg.py) — đổi metamodel mà quên phép chiếu
# (hoặc ngược lại) thì báo lỗi ngay, không lặng lẽ ra Γ thiếu.
READS_NODE_PROPS = {"Activity": ("name", "origin"), "Attribute": ("name", "level", "type", "values", "min", "max")}
READS_EDGE_PROPS = {"DIRECTLY_FOLLOWS": ("count",)}


class MetamodelViolation(ValueError):
    """Đồ thị tầng Tiến trình không tuân thủ metamodel, hoặc phép chiếu đọc thứ metamodel không khai báo."""


def contract_errors() -> List[str]:
    """Chỗ phép chiếu KG → Γ lệch metamodel (rỗng = khớp)."""
    out = []
    for label, props in READS_NODE_PROPS.items():
        cls = NODE_CLASSES.get(label)
        if cls is None or cls.layer != "process":
            out.append(f"lớp '{label}' không phải lớp tầng Tiến trình của metamodel")
            continue
        declared = {k for k, _ in cls.required} | {k for k, _ in cls.optional}
        out += [f"{label}.{p} không được metamodel khai báo" for p in props if p not in declared]
    for rel, props in READS_EDGE_PROPS.items():
        declared = {k for k, _ in RELATIONS[rel].required} if rel in RELATIONS else None
        if declared is None:
            out.append(f"quan hệ '{rel}' không có trong metamodel")
        else:
            out += [f"{rel}.{p} không bắt buộc trong metamodel" for p in props if p not in declared]
    if set(GAMMA_TYPES) != set(ATTRIBUTE_TYPES):
        out.append(f"GAMMA_TYPES {sorted(GAMMA_TYPES)} ≠ kiểu của metamodel {sorted(ATTRIBUTE_TYPES)}")
    return out


def gamma_from_kg(graph: Mapping[str, Any], dataset: str) -> Dict[str, Any]:
    """Γ = phép chiếu tầng Tiến trình của KG, CHỈ sau khi đồ thị qua kiểm metamodel (M2 → M1 → Γ).
    Đồ thị phải chỉ chứa lớp tầng Tiến trình. Vi phạm → MetamodelViolation (không sinh Γ từ đồ thị sai)."""
    problems = contract_errors()
    if problems:
        raise MetamodelViolation("Phép chiếu KG → Γ lệch metamodel:\n  " + "\n  ".join(problems))
    violations = validate_graph(graph)
    violations += [f"node {n['id']} [{n['label']}]: lớp không thuộc tầng Tiến trình"
                   for n in graph["nodes"] if n["label"] in NODE_CLASSES
                   and NODE_CLASSES[n["label"]].layer != "process"]
    if violations:
        raise MetamodelViolation(f"Đồ thị {dataset}: {len(violations)} vi phạm metamodel — không dựng Γ.\n"
                                 + summary(violations))
    return process_schema_from_graph(graph, dataset)


def _origin(props: Mapping[str, Any]) -> str:
    if props.get("origin"):
        return str(props["origin"])
    name = str(props["name"])
    return name.split(COMPOSITE_SEP, 1)[0] if COMPOSITE_SEP in name else DEFAULT_ORIGIN


def _samples(props: Mapping[str, Any]) -> List[Any]:
    if "values" in props:
        return list(props["values"])
    if props.get("type") in ("number", "datetime") and "min" in props:
        return [props["min"], props["max"]]
    return []


def _domain(props: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Miền giá trị ĐẦY ĐỦ quan sát trên log (kiểm C, typing_environment.py): KG chỉ ghi 'values' khi đã liệt kê
    mọi giá trị (boolean, chuỗi ≤ MAX_LISTED_VALUES), và min/max của thuộc tính số tính trên toàn bộ log.
    Không chắc đầy đủ (chuỗi nhiều giá trị, ngày giờ) → {} (không kiểm).
    """
    if "values" in props:
        return {"domain": {"values": list(props["values"])}}
    if props.get("type") == "number" and "min" in props:
        return {"domain": {"min": props["min"], "max": props["max"]}}
    return {}


def _attribute_entry(props: Mapping[str, Any]) -> Dict[str, Any]:
    return {"type": GAMMA_TYPES.get(props.get("type", ""), "String"), "samples": _samples(props), **_domain(props)}


def _strip_activity_prefix(node_id: str) -> str:
    return node_id[len("Act:"):] if node_id.startswith("Act:") else node_id


def process_schema_from_graph(graph: Mapping[str, Any], dataset: str) -> Dict[str, Any]:
    """Γ dạng process_schema từ đồ thị tầng Tiến trình ({'nodes': [...], 'edges': [...]})."""
    nodes = graph["nodes"]
    activities = sorted(n["props"]["name"] for n in nodes if n["label"] == "Activity")
    by_origin: Dict[str, List[str]] = {}
    for n in nodes:
        if n["label"] == "Activity":
            by_origin.setdefault(_origin(n["props"]), []).append(n["props"]["name"])

    case_attrs: Dict[str, Dict[str, Any]] = {}
    event_attrs: Dict[str, Dict[str, Any]] = {TIME_ATTRIBUTE: {"type": "Timestamp", "samples": []}}
    for n in nodes:
        if n["label"] != "Attribute":
            continue
        props = n["props"]
        target = case_attrs if props.get("level") == "case" else event_attrs
        target[props["name"]] = _attribute_entry(props)

    follows = [e for e in graph["edges"] if e["type"] == "DIRECTLY_FOLLOWS"]
    follows.sort(key=lambda e: (-e["props"]["count"], e["source"], e["target"]))
    transitions = [
        {"from": _strip_activity_prefix(e["source"]), "to": _strip_activity_prefix(e["target"]),
         "count": e["props"]["count"]}
        for e in follows[:MAX_TRANSITIONS]
    ]
    return {
        "dataset": dataset,
        "source": "knowledge_graph",
        "valid_activities": activities,
        "activities_by_origin": {k: sorted(v) for k, v in sorted(by_origin.items())},
        "case_attributes": case_attrs,
        "event_attributes": event_attrs,
        "frequent_transitions": transitions,
    }
