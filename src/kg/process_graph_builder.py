"""
M3 – Process Graph Builder (TN3): dựng tầng Tiến trình của KG ở mức LƯỢC ĐỒ từ event log.

Tầng này đóng vai trò "mô hình miền" (thay sơ đồ lớp UML trong OVAS): nó cho biết hệ thống
có những activity nào, thuộc tính nào, activity nào thực sự mang thuộc tính nào.
Được khai phá tự động, tất định từ log (không dùng LLM).

Node:  Activity  (mỗi giá trị concept:name)     Attribute (mỗi cột dữ liệu không phải cột kỹ thuật)
Cạnh:  DIRECTLY_FOLLOWS  Activity -> Activity   (B xảy ra ngay sau A trong cùng hồ sơ; kèm số lần)
       HAS_ATTRIBUTE     Activity -> Attribute  (event của A có giá trị thuộc tính; kèm tỉ lệ có giá trị)

Không nạp từng event (1,2 triệu) vào đồ thị: việc kiểm tra tuân thủ chạy trực tiếp trên log.
"""

from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from .schema import EdgeType, KGEdge, KGNode, KnowledgeGraph, NodeLabel

CASE_COL = "case:concept:name"
ACTIVITY_COL = "concept:name"
TIME_COL = "time:timestamp"
ORIGIN_COL = "EventOrigin"
CASE_PREFIX = "case:"
# Cột định danh / kỹ thuật của log: không phải dữ liệu nghiệp vụ, không tạo node Attribute.
TECHNICAL_COLUMNS = frozenset({
    CASE_COL, ACTIVITY_COL, TIME_COL, ORIGIN_COL,
    "Action", "EventID", "OfferID", "lifecycle:transition", "org:resource",
    "eventid", "docid",  # BPIC2018
})
COMPOSITE_PARTS = ("doctype", "subprocess", "activity")  # BPIC2018: 'Original Activity' classifier
COMPOSITE_SEP = " / "
MAX_LISTED_VALUES = 20  # thuộc tính chuỗi có nhiều giá trị hơn thì chỉ ghi số lượng
RATIO_DIGITS = 4


def activity_node_id(name: str) -> str:
    return f"Act:{name}"


def attribute_node_id(name: str) -> str:
    return f"Attr:{name}"


def data_attributes(df: pd.DataFrame) -> List[str]:
    """Cột dữ liệu nghiệp vụ (loại bỏ cột kỹ thuật), giữ thứ tự cột của log."""
    return [c for c in df.columns if c not in TECHNICAL_COLUMNS]


# --------------------------------------------------------------------------- activities


def _activity_nodes(df: pd.DataFrame) -> List[KGNode]:
    total_cases = df[CASE_COL].nunique()
    grouped = df.groupby(ACTIVITY_COL, sort=True)
    event_counts = grouped.size()
    case_counts = grouped[CASE_COL].nunique()
    origins = grouped[ORIGIN_COL].agg(lambda s: s.mode().iat[0]) if ORIGIN_COL in df else None
    nodes = []
    for name in event_counts.index:
        props: Dict[str, Any] = {
            "name": name,
            "event_count": int(event_counts[name]),
            "case_count": int(case_counts[name]),
            "case_ratio": round(case_counts[name] / total_cases, RATIO_DIGITS),
        }
        if origins is not None:
            props["origin"] = str(origins[name])
        nodes.append(KGNode(activity_node_id(name), NodeLabel.ACTIVITY, props))
    return nodes


def _directly_follows_edges(df: pd.DataFrame) -> List[KGEdge]:
    ordered = df.sort_values([CASE_COL, TIME_COL], kind="mergesort")
    following = ordered.groupby(CASE_COL, sort=False)[ACTIVITY_COL].shift(-1)
    pairs = pd.DataFrame({"a": ordered[ACTIVITY_COL], "b": following}).dropna()
    counts = pairs.groupby(["a", "b"], sort=True).size()
    return [
        KGEdge(activity_node_id(a), activity_node_id(b), EdgeType.DIRECTLY_FOLLOWS, {"count": int(n)})
        for (a, b), n in counts.items()
    ]


# --------------------------------------------------------------------------- attributes


def _is_boolean(values: pd.Series) -> bool:
    return bool(len(values)) and set(values.astype(str).str.lower().unique()) <= {"true", "false"}


def _attribute_props(name: str, column: pd.Series) -> Dict[str, Any]:
    values = column.dropna()
    props: Dict[str, Any] = {
        "name": name,
        "level": "case" if name.startswith(CASE_PREFIX) else "event",
        "non_null_ratio": round(len(values) / len(column), RATIO_DIGITS) if len(column) else 0.0,
    }
    if pd.api.types.is_numeric_dtype(column) and not pd.api.types.is_bool_dtype(column):
        props.update(type="number", min=float(values.min()), max=float(values.max()))
    elif pd.api.types.is_datetime64_any_dtype(column):
        props.update(type="datetime", min=str(values.min()), max=str(values.max()))
    elif _is_boolean(values):
        props.update(type="boolean", values=sorted(values.astype(str).unique().tolist()))
    else:
        distinct = sorted(values.astype(str).unique().tolist())
        props.update(type="string", distinct_count=len(distinct))
        if len(distinct) <= MAX_LISTED_VALUES:
            props["values"] = distinct
    return props


def _attribute_nodes(df: pd.DataFrame, attributes: Sequence[str]) -> List[KGNode]:
    return [
        KGNode(attribute_node_id(a), NodeLabel.ATTRIBUTE, _attribute_props(a, df[a]))
        for a in attributes
    ]


def _has_attribute_edges(df: pd.DataFrame, attributes: Sequence[str]) -> List[KGEdge]:
    """Chỉ thuộc tính mức event: thuộc tính mức hồ sơ có ở mọi activity nên không cần cạnh."""
    event_attrs = [a for a in attributes if not a.startswith(CASE_PREFIX)]
    if not event_attrs:
        return []
    present = df[event_attrs].notna().groupby(df[ACTIVITY_COL], sort=True)
    counts, ratios = present.sum(), present.mean()
    edges = []
    for activity in counts.index:
        for attr in event_attrs:
            n = int(counts.at[activity, attr])
            if n == 0:
                continue
            edges.append(KGEdge(
                activity_node_id(activity), attribute_node_id(attr), EdgeType.HAS_ATTRIBUTE,
                {"count": n, "non_null_ratio": round(float(ratios.at[activity, attr]), RATIO_DIGITS)},
            ))
    return edges


# ----------------------------------------------------------------------------- building


def with_composite_activity(
    df: pd.DataFrame, parts: Sequence[str] = COMPOSITE_PARTS, sep: str = COMPOSITE_SEP
) -> pd.DataFrame:
    """Bản sao log với concept:name = các phần ghép bằng sep (bỏ phần trống); các cột thành phần bị bỏ.

    BPIC2018: 'begin editing' có ở 6 loại giấy tờ, nên tên activity phải gồm cả loại giấy tờ.
    """
    present = [p for p in parts if p in df.columns]
    if not present:
        raise KeyError(f"Log không có cột nào trong {list(parts)}")
    # Chỉ vài chục tổ hợp khác nhau: tính tên trên tổ hợp rồi gắn lại (nhanh trên 2,5 triệu dòng).
    combos = df[present].drop_duplicates().reset_index(drop=True)
    combos["_name"] = combos.apply(lambda r: sep.join(str(v) for v in r if pd.notna(v) and v != ""), axis=1)
    names = df[present].merge(combos, on=present, how="left")["_name"].to_numpy()
    return df.drop(columns=present).assign(**{ACTIVITY_COL: names})


def build_process_graph(df: pd.DataFrame, cases: Optional[pd.DataFrame] = None) -> KnowledgeGraph:
    """Dựng tầng Tiến trình (mức lược đồ) từ event log dạng bảng (mỗi dòng một event).

    cases: bảng hồ sơ tách riêng (một dòng mỗi hồ sơ, cột 'case:*'), dùng khi log quá lớn để lặp
    thuộc tính hồ sơ trên mọi event (BPIC2018). Node thuộc tính hồ sơ khi đó được tính trên bảng này.
    """
    missing = [c for c in (CASE_COL, ACTIVITY_COL, TIME_COL) if c not in df.columns]
    if missing:
        raise KeyError(f"Log thiếu cột bắt buộc: {missing}")
    attributes = data_attributes(df)
    attribute_nodes = _attribute_nodes(df, attributes)
    if cases is not None:
        case_attrs = [c for c in data_attributes(cases) if c.startswith(CASE_PREFIX)]
        attribute_nodes += _attribute_nodes(cases, case_attrs)
    return KnowledgeGraph().merge(
        nodes=[*_activity_nodes(df), *attribute_nodes],
        edges=[*_directly_follows_edges(df), *_has_attribute_edges(df, attributes)],
    )
