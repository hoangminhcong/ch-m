"""
v2 — hồ sơ tầng Tiến trình (docs/V2_DANG_KY_TRUOC.md mục 4, thành phần 1, 3, 4, 5, 11).

Làm giàu "KG thay UML" bằng những gì log ghi được mà Γ v1 bỏ qua, tất định, không dùng LLM:
  - năm hoạt động của từng activity (log BPIC2018 đổi loại giấy tờ theo năm);
  - activity CÙNG BƯỚC ở loại giấy tờ khác (cùng tiến trình con + hành động) — ứng viên nhóm '{A | B}';
  - vai trò thực hiện (org:resource: máy tự động / nhân viên / không rõ), tỉ lệ theo event;
  - bước trước / sau thường gặp (DIRECTLY_FOLLOWS);
  - thuộc tính event có giá trị ở activity (HAS_ATTRIBUTE);
  - quan hệ hồ sơ → tài liệu (docid) → loại giấy tờ: số tài liệu mỗi hồ sơ.

Ghi ra file riêng (data/processed/bpic2018_process_profile.json); Γ v1 (gamma_bpic2018.json) KHÔNG đổi.
Đầu vào: event log đã ghép tên activity (process_graph_builder.with_composite_activity) + bảng hồ sơ.
"""

import re
from typing import Any, Dict, List, Optional

import pandas as pd

from .process_graph_builder import (
    ACTIVITY_COL,
    CASE_COL,
    CASE_PREFIX,
    COMPOSITE_SEP,
    RATIO_DIGITS,
    TIME_COL,
    data_attributes,
)

YEAR_ATTR = "case:year"
RESOURCE_COL = "org:resource"
DOC_COL = "docid"
NEIGHBOURS = 3  # số bước trước / sau ghi cho mỗi activity
ROLE_KINDS = ("automated", "staff", "unknown")
_AUTOMATED = re.compile(r"automaton|processor|scheduler|export|import", re.IGNORECASE)
_STAFF_ID = re.compile(r"[0-9a-f]{6}|\d+")  # mã nhân viên ẩn danh của BPIC2018 (hex 6 ký tự hoặc số)


def resource_kind(name: Optional[str]) -> str:
    """'automated' (máy / dịch vụ tự động), 'staff' (mã nhân viên ẩn danh) hoặc 'unknown' (VD 'DP-Z', '0;n/a')."""
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return "unknown"
    text = str(name).strip()
    if _AUTOMATED.search(text):
        return "automated"
    return "staff" if _STAFF_ID.fullmatch(text) else "unknown"


def _parts(name: str) -> Dict[str, str]:
    bits = name.split(COMPOSITE_SEP)
    if len(bits) >= 3:
        return {"doctype": bits[0], "subprocess": COMPOSITE_SEP.join(bits[1:-1]), "action": bits[-1]}
    return {"doctype": bits[0] if len(bits) > 1 else "", "subprocess": "", "action": bits[-1]}


def _neighbours(df: pd.DataFrame) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    nxt = df.groupby(CASE_COL, sort=False)[ACTIVITY_COL].shift(-1)
    pairs = pd.DataFrame({"a": df[ACTIVITY_COL].to_numpy(), "b": nxt.to_numpy()}).dropna()
    counts = pairs.value_counts().reset_index(name="count")
    counts = counts.sort_values(["count", "a", "b"], ascending=[False, True, True], kind="mergesort")
    out: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for side, key, other in (("successors", "a", "b"), ("predecessors", "b", "a")):
        for name, grp in counts.groupby(key, sort=True):
            out.setdefault(name, {})[side] = [{"activity": r[other], "count": int(r["count"])}
                                              for _, r in grp.head(NEIGHBOURS).iterrows()]
    return out


def _roles(df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    if RESOURCE_COL not in df.columns:
        return {}
    kinds = df[RESOURCE_COL].map(resource_kind)
    share = pd.crosstab(df[ACTIVITY_COL], kinds, normalize="index")
    return {act: {k: round(float(share.at[act, k]), RATIO_DIGITS) if k in share.columns else 0.0 for k in ROLE_KINDS}
            for act in share.index}


def _event_attributes(df: pd.DataFrame) -> Dict[str, List[str]]:
    attrs = [a for a in data_attributes(df) if not a.startswith(CASE_PREFIX)]
    if not attrs:
        return {}
    present = df[attrs].notna().groupby(df[ACTIVITY_COL], sort=True).any()
    return {act: [a for a in attrs if bool(present.at[act, a])] for act in present.index}


def _documents(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    if DOC_COL not in df.columns:
        return {}
    docs = df[[CASE_COL, DOC_COL]].assign(doctype=df[ACTIVITY_COL].map(lambda n: _parts(n)["doctype"]))
    per_case = docs.drop_duplicates().groupby(["doctype", CASE_COL]).size()
    out = {}
    for doctype, counts in per_case.groupby(level=0, sort=True):
        out[doctype] = {"cases": int(counts.size), "per_case_median": float(counts.median()),
                        "per_case_max": int(counts.max())}
    return out


def build_process_profile(events: pd.DataFrame, cases: pd.DataFrame) -> Dict[str, Any]:
    """Hồ sơ tầng Tiến trình. Sắp theo (hồ sơ, thời điểm) ỔN ĐỊNH: event cùng thời điểm giữ thứ tự của log, như
    process_graph_builder (rà soát 2026-11-18 H1: 13% event BPIC2018 trùng thời điểm; xếp theo tên activity đảo
    thứ tự bước trước / sau)."""
    df = events.sort_values([CASE_COL, TIME_COL], kind="mergesort").reset_index(drop=True)
    year_of = cases.set_index(CASE_COL)[YEAR_ATTR] if YEAR_ATTR in cases.columns else pd.Series(dtype=object)
    years = df[CASE_COL].map(year_of)
    total_cases = df[CASE_COL].nunique()
    neighbours, roles, attrs = _neighbours(df), _roles(df), _event_attributes(df)
    grouped = df.assign(_year=years).groupby(ACTIVITY_COL, sort=True)
    case_counts = grouped[CASE_COL].nunique()
    act_years = grouped["_year"].agg(lambda s: sorted({int(y) for y in s.dropna()}))
    activities: Dict[str, Dict[str, Any]] = {}
    for name in case_counts.index:
        activities[name] = {
            **_parts(name),
            "years": act_years[name],
            "case_count": int(case_counts[name]),
            "case_ratio": round(case_counts[name] / total_cases, RATIO_DIGITS),
            "roles": roles.get(name, {}),
            "predecessors": neighbours.get(name, {}).get("predecessors", []),
            "successors": neighbours.get(name, {}).get("successors", []),
            "event_attributes": attrs.get(name, []),
        }
    for name, a in activities.items():
        a["same_step"] = sorted(o for o, b in activities.items() if o != name and b["doctype"] != a["doctype"]
                                and (b["subprocess"], b["action"]) == (a["subprocess"], a["action"]))
    all_years = sorted({int(y) for y in years.dropna()})
    doctype_years: Dict[str, List[int]] = {}
    for a in activities.values():
        doctype_years[a["doctype"]] = sorted(set(doctype_years.get(a["doctype"], [])) | set(a["years"]))
    return {"dataset": "bpic2018", "years": all_years, "num_cases": int(total_cases),
            "activities": activities, "documents": _documents(df), "doctype_years": dict(sorted(doctype_years.items())),
            "doctype_replacements": doctype_replacements(doctype_years, all_years)}


def doctype_replacements(doctype_years: Dict[str, List[int]], all_years: List[int]) -> Dict[str, List[str]]:
    """Loại giấy tờ thay thế nhau theo năm: năm hoạt động không giao nhau, gộp lại phủ đủ các năm của log."""
    out: Dict[str, List[str]] = {}
    for d1, y1 in doctype_years.items():
        others = sorted(d2 for d2, y2 in doctype_years.items()
                        if d2 != d1 and y1 and y2 and not set(y1) & set(y2) and set(y1) | set(y2) == set(all_years))
        if others:
            out[d1] = others
    return dict(sorted(out.items()))
