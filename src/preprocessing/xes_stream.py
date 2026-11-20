"""
Chuyển event log XES rất lớn sang parquet bằng cách đọc tuần tự (streaming) – dùng cho BPIC2018 (1,9 GB),
quá lớn để nạp một lần bằng pm4py.read_xes.

Kết quả gồm hai bảng (tránh lặp ~60 thuộc tính hồ sơ trên 2,5 triệu event):
  events.parquet : case:concept:name + các thuộc tính event (concept:name, time:timestamp, ...)
  cases.parquet  : case:concept:name + các thuộc tính hồ sơ, tiền tố 'case:' (quy ước pm4py)

Lược đồ cột lấy từ khai báo <global scope="trace|event"> ở đầu file XES; kiểu dữ liệu theo thẻ XES.
Thuộc tính kiểu 'id' (UUID kỹ thuật) bị bỏ. Thuộc tính HỒ SƠ không khai báo vẫn được giữ (kiểu theo thẻ
XES; BPIC2018 có amount_applied1..3, ...); thuộc tính EVENT không khai báo bị bỏ và cảnh báo.
Thuộc tính lồng (nested) chỉ lấy cấp ngoài cùng.
"""

import warnings
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from lxml import etree

CASE_COL = "case:concept:name"
CASE_PREFIX = "case:"
DEFAULT_CHUNK_TRACES = 2000
_ARROW_TYPES = {
    "string": pa.string(),
    "int": pa.int64(),
    "float": pa.float64(),
    "boolean": pa.bool_(),
    "date": pa.timestamp("us", tz="UTC"),
}

Schema = Dict[str, str]  # key -> thẻ XES


def _local(tag: Any) -> str:
    return etree.QName(tag).localname if isinstance(tag, str) else ""


def _attributes(elem: etree._Element) -> Dict[str, Tuple[str, str]]:
    """Thuộc tính cấp ngoài cùng của một trace/event: key -> (thẻ, giá trị chuỗi)."""
    return {c.get("key"): (_local(c.tag), c.get("value")) for c in elem if _local(c.tag) in _ARROW_TYPES}


def _convert(tag: str, value: str) -> Any:
    if value is None:
        return None
    if tag == "int":
        return int(value)
    if tag == "float":
        return float(value)
    if tag == "boolean":
        return value.strip().lower() == "true"
    return value  # string; date được chuyển theo cả cột


def _frame(rows: List[Dict[str, Any]], schema: Schema, prefix: str) -> pa.Table:
    columns = [CASE_COL] + [prefix + k for k in schema if prefix + k != CASE_COL]
    df = pd.DataFrame(rows, columns=columns)
    for key, tag in schema.items():
        col = prefix + key
        if tag == "date":
            df[col] = pd.to_datetime(df[col], utc=True, format="ISO8601")
    fields = [pa.field(CASE_COL, pa.string())] + [
        pa.field(prefix + k, _ARROW_TYPES[t]) for k, t in schema.items() if prefix + k != CASE_COL
    ]
    return pa.Table.from_pandas(df, schema=pa.schema(fields), preserve_index=False)


class _Writer:
    """Ghi từng lô vào parquet với lược đồ cố định."""

    def __init__(self, path: Path, schema: Schema, prefix: str) -> None:
        self.path, self.schema, self.prefix = path, schema, prefix
        self.rows: List[Dict[str, Any]] = []
        self.writer = None

    def flush(self) -> None:
        table = _frame(self.rows, self.schema, self.prefix)
        if self.writer is None:
            self.writer = pq.ParquetWriter(str(self.path), table.schema)
        self.writer.write_table(table)
        self.rows = []

    def close(self) -> None:
        if self.rows or self.writer is None:
            self.flush()
        self.writer.close()


def _row(case_id: str, attrs: Dict[str, Tuple[str, str]], schema: Schema, prefix: str,
         undeclared: set) -> Dict[str, Any]:
    row: Dict[str, Any] = {CASE_COL: case_id}
    for key, (_tag, value) in attrs.items():
        if key not in schema:
            undeclared.add(key)
            continue
        row[prefix + key] = _convert(schema[key], value)
    return row


def convert_xes(
    xes_path: Union[str, Path],
    events_out: Union[str, Path],
    cases_out: Union[str, Path],
    chunk_traces: int = DEFAULT_CHUNK_TRACES,
) -> Dict[str, int]:
    """Đọc tuần tự XES, ghi bảng event và bảng hồ sơ. Trả về {'cases': n, 'events': m}."""
    xes_path = Path(xes_path)
    if not xes_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file XES: {xes_path}")
    schemas: Dict[str, Schema] = {"trace": {}, "event": {}}
    ev_writer = None
    case_schema: Schema = {}
    case_rows: List[Dict[str, Any]] = []  # bảng hồ sơ nhỏ (vài chục nghìn dòng): ghi một lần ở cuối
    n_cases = n_events = 0
    undeclared: set = set()

    for _, elem in etree.iterparse(str(xes_path), events=("end",), huge_tree=True):
        name = _local(elem.tag)
        if name == "global":
            schemas[elem.get("scope")] = {k: t for k, (t, _) in _attributes(elem).items() if t != "id"}
            continue
        if name != "trace":
            continue
        if ev_writer is None:
            ev_writer = _Writer(Path(events_out), schemas["event"], "")
            case_schema = {"concept:name": "string", **schemas["trace"]}
        trace_attrs = _attributes(elem)
        case_id = trace_attrs.get("concept:name", ("string", None))[1]
        for key, (tag, _) in trace_attrs.items():  # thuộc tính hồ sơ không khai báo: giữ, kiểu theo thẻ XES
            if key not in case_schema and tag != "id":
                case_schema[key] = tag
        case_rows.append(_row(case_id, trace_attrs, case_schema, CASE_PREFIX, undeclared))
        for ev in elem:
            if _local(ev.tag) == "event":
                ev_writer.rows.append(_row(case_id, _attributes(ev), ev_writer.schema, "", undeclared))
                n_events += 1
        n_cases += 1
        if n_cases % chunk_traces == 0:
            ev_writer.flush()
        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]

    if ev_writer is None:
        raise ValueError(f"File XES không có hồ sơ (trace) nào: {xes_path}")
    ev_writer.close()
    pq.write_table(_frame(case_rows, case_schema, CASE_PREFIX), str(cases_out))
    undeclared.discard("identity:id")
    undeclared.discard("docid_uuid")
    if undeclared:
        warnings.warn(f"Bỏ qua thuộc tính không khai báo trong <global>: {sorted(undeclared)}", stacklevel=2)
    return {"cases": n_cases, "events": n_events}
