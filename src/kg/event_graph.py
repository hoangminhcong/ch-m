"""
Đồ thị sự kiện trong Neo4j cho M8 (src/kg/cypher_compiler.py): (:EvCase)-[:HAS_EVENT]->(:Ev).

Dựng TỪ chỉ mục của engine Declare4Py (cùng thứ tự event, cùng thuộc tính hồ sơ) → Cypher và engine Python chạy trên
đúng cùng dữ liệu, so được từng hồ sơ. Thuộc tính giữ tên gốc ('case:young farmer', 'concept:name' → activity).
"""

import math
import random
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from ..symbolic.data_conditions import CASE_KEY, DEFAULT_TIMEZONE
from .cypher_compiler import CASE_LABEL, EVENT_LABEL, HAS_EVENT

BATCH = 2000
_SKIP_EVENT_KEYS = {CASE_KEY, "_ts_sec", "concept:name", "case:concept:name"}


def _primitive(v: Any) -> Any:
    """Giá trị Neo4j lưu được; None/NaN → None (bỏ thuộc tính, như engine coi là thiếu)."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):  # numpy scalar
        v = v.item()
    if isinstance(v, (bool, int, float, str)):
        return v
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _props(record: Mapping[str, Any], skip: Iterable[str] = ()) -> Dict[str, Any]:
    out = {}
    for k, v in record.items():
        if k in skip:
            continue
        pv = _primitive(v)
        if pv is not None:
            out[k] = pv
    return out


def select_cases(trace_index: Mapping[str, Any], n: Optional[int], seed: int = 2018) -> List[str]:
    """n hồ sơ chọn ngẫu nhiên có seed (None = mọi hồ sơ), giữ thứ tự của engine."""
    ids = list(trace_index)
    if n is None or n >= len(ids):
        return ids
    chosen = set(random.Random(seed).sample(ids, n))
    return [i for i in ids if i in chosen]


def event_graph_rows(trace_index: Mapping[str, Any], case_ids: Sequence[str], timezone: str = DEFAULT_TIMEZONE
                     ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """ts = giây epoch (_ts_sec của engine); day = ngày địa phương theo `timezone` — đúng phép tính của engine
    (datetime.fromtimestamp(ts, tz).date()), để điều kiện ngày và thời hạn theo lịch trong Cypher khớp engine."""
    tz = ZoneInfo(timezone)
    cases, events = [], []
    for cid in case_ids:
        evs = trace_index[cid]["events"]
        case_attrs = (evs[0].get(CASE_KEY) or {}) if evs else {}
        cases.append({"id": cid, "props": _props(case_attrs)})
        for idx, e in enumerate(evs):
            ts = _primitive(e.get("_ts_sec"))
            row = {"case": cid, "idx": idx, "activity": e["concept:name"], "props": _props(e, _SKIP_EVENT_KEYS)}
            if ts is not None:
                row["props"] = {**row["props"], "ts": float(ts),
                                "day": datetime.fromtimestamp(float(ts), tz).date()}
            events.append(row)
    return cases, events


def write_event_graph(session: Any, cases: Sequence[Mapping[str, Any]], events: Sequence[Mapping[str, Any]],
                      replace: bool = True) -> None:
    if replace:
        session.run(f"MATCH (n:{EVENT_LABEL}) CALL (n) {{ DETACH DELETE n }} IN TRANSACTIONS OF 10000 ROWS")
        session.run(f"MATCH (n:{CASE_LABEL}) CALL (n) {{ DETACH DELETE n }} IN TRANSACTIONS OF 10000 ROWS")
    session.run(f"CREATE INDEX evcase_id IF NOT EXISTS FOR (c:{CASE_LABEL}) ON (c.id)")
    for i in range(0, len(cases), BATCH):
        session.run(f"UNWIND $rows AS r CREATE (c:{CASE_LABEL} {{id: r.id}}) SET c += r.props",
                    rows=list(cases[i:i + BATCH]))
    for i in range(0, len(events), BATCH):
        session.run(f"UNWIND $rows AS r MATCH (c:{CASE_LABEL} {{id: r.case}}) "
                    f"CREATE (c)-[:{HAS_EVENT}]->(e:{EVENT_LABEL} {{idx: r.idx, activity: r.activity}}) "
                    "SET e += r.props", rows=list(events[i:i + BATCH]))
