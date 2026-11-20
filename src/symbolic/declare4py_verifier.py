"""
Bước 3.2 & 3.3: Trọng tài Kiểm tra Tuân thủ Tất định bằng Declare4Py,
Kiểm tra Tính Không Rỗng (Log-Grounded Vacuity Check) và Trích xuất Bản chụp Phản ví dụ (Counterexample Snapshot).
Tham khảo:
- Repo Declare4Py (ProcessModels/DeclareModel.py & Utils/Declare/Checkers.py)
- Bài OCL2026 (OVAS): Mục 3.4.6 (Vacuity Check & Concrete Deterministic State Snapshot)
- Bài arXiv:2510.07161 (Janus evaluation metrics: activations, fulfillments, violations)
"""

from dataclasses import dataclass
import os
import re
import tempfile
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import numpy as np
import pandas as pd

from zoneinfo import ZoneInfo

from .data_conditions import CASE_KEY, DEFAULT_TIMEZONE, DEFAULT_YEAR_ATTR, compile_condition
from .time_windows import TimeWindow, parse_time_window, within


@dataclass
class RuleCheckResult:
    """Kết quả kiểm chứng Declare4Py trên từng hồ sơ vay (Trace)."""

    num_activations: int
    num_fulfillments: int
    num_violations: int
    state: str  # "Satisfied" | "Violated" | "Vacuously Satisfied"


def _activity_set(spec: str) -> frozenset:
    """'A' -> {A}; nhóm '{X | Y}' -> {X, Y} (VD hai kênh gửi đề nghị vay O_Sent)."""
    spec = spec.strip()
    if spec.startswith("{") and spec.endswith("}"):
        return frozenset(p.strip() for p in spec[1:-1].split("|") if p.strip())
    return frozenset({spec})


class Declare4Py:
    """
    Engine Declare4Py tích hợp trực tiếp cú pháp parser .decl của repo Declare4Py
    và bộ kiểm chứng tốc độ cao trên Event Log BPI Challenge 2017 (31.509 traces).
    Tương thích hoàn toàn với phương thức:
      - parse_decl_model(model_path=...)
      - conformance_checking(consider_vacuity=False)
    """

    def __init__(
        self,
        log_df: Optional[pd.DataFrame] = None,
        cases: Optional[pd.DataFrame] = None,
        timezone: str = DEFAULT_TIMEZONE,
        year_attr: str = DEFAULT_YEAR_ATTR,
        calendar_periods: bool = False,
    ) -> None:
        """
        cases: bảng hồ sơ riêng (1 dòng / hồ sơ, cột 'case:concept:name' + thuộc tính 'case:…'), VD BPIC2018.
        timezone: múi giờ tính 'A.date' (BPIC2018: 'Europe/Berlin'); year_attr: thuộc tính năm cho 'year'.
        Mặc định (không cases, UTC) giữ nguyên hành vi BPIC2017.
        """
        self.log_df: Optional[pd.DataFrame] = None
        self.parsed_constraints: List[Dict[str, Any]] = []
        self._trace_index: Dict[str, Dict[str, Any]] = {}
        self.timezone = timezone
        self._tz = ZoneInfo(timezone)
        # F-DAYS: True (bộ CAP) → thời hạn ngày/tuần/tháng theo ngày lịch, Quy định 1182/71 (time_windows.py)
        self.calendar_periods = calendar_periods
        self.year_attr = year_attr
        if log_df is not None:
            self.load_dataframe_log(log_df, cases=cases)

    def load_dataframe_log(self, log_df: pd.DataFrame, cases: Optional[pd.DataFrame] = None) -> None:
        """
        Chuẩn bị và lập chỉ mục 31.509 hồ sơ vay từ DataFrame của BPI Challenge 2017
        để kiểm chứng mỗi ràng buộc .decl chỉ trong ~0.1 - 0.3 giây.
        Đồng thời lan truyền (forward/backward-fill theo từng hồ sơ) các thuộc tính mức Offer
        (OfferedAmount, CreditScore, Accepted, MonthlyCost, NumberOfTerms) để các sự kiện trong cùng
        hồ sơ truy xuất được trạng thái đề nghị vay tương ứng.
        """
        df = log_df.copy()
        if "time:timestamp" in df.columns:
            df["time:timestamp"] = pd.to_datetime(df["time:timestamp"], utc=True)
            df = df.sort_values(["case:concept:name", "time:timestamp"], kind="mergesort")

        # Lan truyền thuộc tính Offer trong phạm vi từng hồ sơ (case:concept:name)
        offer_cols = [
            c
            for c in [
                "OfferedAmount",
                "CreditScore",
                "Accepted",
                "Selected",
                "MonthlyCost",
                "NumberOfTerms",
                "FirstWithdrawalAmount",
            ]
            if c in df.columns
        ]
        if offer_cols:
            df[offer_cols] = df.groupby("case:concept:name", sort=False)[offer_cols].transform(
                lambda g: g.ffill().bfill()
            )

        self.log_df = df

        # Xây dựng cấu trúc chỉ mục mảng theo từng hồ sơ vay (case_id)
        self._trace_index = {}
        cols_to_keep = [
            c
            for c in [
                "concept:name",
                "time:timestamp",
                "org:resource",
                "case:RequestedAmount",
                "case:LoanGoal",
                "case:ApplicationType",
                "OfferedAmount",
                "CreditScore",
                "Accepted",
                "Selected",
                "MonthlyCost",
                "NumberOfTerms",
            ]
            if c in df.columns
        ]
        case_records: Dict[str, Dict[str, Any]] = {}
        if cases is not None:
            # Có bảng hồ sơ riêng: giữ MỌI cột mức event; thuộc tính hồ sơ lấy từ `cases`, lưu 1 lần / trace.
            cols_to_keep = [c for c in df.columns if not c.startswith("case:")]
            case_records = {
                str(k): v for k, v in cases.set_index("case:concept:name").to_dict("index").items()
            }

        # Chuyển thời gian về giây (float epoch seconds) chính xác cho mọi độ phân giải datetime64[s/ms/us/ns] trong Pandas 3.0
        epoch = pd.Timestamp("1970-01-01", tz="UTC")
        df["_ts_sec"] = (df["time:timestamp"] - epoch).dt.total_seconds().to_numpy()

        # Một lần to_dict cho cả log rồi chia theo hồ sơ (trước: to_dict từng nhóm, 43.809 lần ≈ 80 s trên BPIC2018).
        # Thứ tự hồ sơ = lần xuất hiện đầu (như groupby(sort=False)), thứ tự event giữ nguyên, khóa rỗng bị bỏ
        # (như groupby dropna) — tests/test_engine_index_fast_path.py so khớp với cách cũ.
        all_records = df[cols_to_keep + ["_ts_sec"]].to_dict("records")
        codes, case_ids = pd.factorize(df["case:concept:name"], sort=False)
        order = np.argsort(codes, kind="stable")
        counts = np.bincount(codes[codes >= 0], minlength=len(case_ids))
        start = int((codes < 0).sum())  # mã -1 (khóa rỗng) đứng đầu sau argsort → bỏ qua
        for case_id, n in zip(case_ids, counts, strict=True):  # bincount(minlength=len) → cùng độ dài
            records = [all_records[i] for i in order[start:start + n]]
            start += int(n)
            if cases is not None:
                shared = case_records.get(str(case_id), {})
                for r in records:
                    r[CASE_KEY] = shared  # cùng một dict cho mọi event của hồ sơ
            self._trace_index[str(case_id)] = {
                "events": records,
                "activities": [r["concept:name"] for r in records],
            }

    def parse_decl_model(self, model_path: str) -> List[Dict[str, Any]]:
        """
        Đọc và phân tích cú pháp file .decl chuẩn của Declare4Py:
        Template[Activation, Target] | Activation_Condition | Correlation_Condition | Time_Condition
        """
        with open(model_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        self.parsed_constraints = self.parse_decl_lines(lines)
        return self.parsed_constraints

    def parse_decl_lines(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Phân tích các dòng .decl (không cần file tạm; không đổi parsed_constraints). Dòng sai cú pháp bị bỏ."""
        parsed: List[Dict[str, Any]] = []
        pattern = re.compile(r"^([^\[]+)\[(.*?)\]\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*)$")

        for line in (ln.strip() for ln in lines):
            if line.lower().startswith(("activity ", "bind ")):
                continue
            m = pattern.match(line)
            if not m:
                continue
            tpl_name = m.group(1).strip()
            acts = [a.strip() for a in m.group(2).split(",") if a.strip()]
            act_cond_str = m.group(3).strip()
            corr_cond_str = m.group(4).strip()
            time_cond_str = m.group(5).strip()

            parsed.append(
                {
                    "raw_line": line,
                    "template": tpl_name,
                    "activities": acts,
                    "activity_sets": [_activity_set(a) for a in acts],
                    "act_cond": self._compile_data_cond(act_cond_str, self.timezone, self.year_attr),
                    "corr_cond": self._compile_data_cond(corr_cond_str, self.timezone, self.year_attr),
                    "time_window": parse_time_window(time_cond_str),
                }
            )
        return parsed

    def count_witness_cases(self, constraint: Dict[str, Any], years: Optional[Sequence[int]] = None) -> int:
        """
        Kiểm rỗng (B): số hồ sơ có ít nhất một sự kiện KÍCH HOẠT thoả act_cond — cùng phía kích hoạt với
        _check_single_trace: B với họ Precedence, A (hoặc A/B với Choice) với các mẫu còn lại.
        0 = ràng buộc không bao giờ được kích hoạt bởi một sự kiện thoả điều kiện: với Response/Precedence là
        thoả rỗng ở mọi hồ sơ; với Existence là vi phạm ở MỌI hồ sơ (không hồ sơ nào có sự kiện thoả).
        """
        if not self._trace_index:
            raise RuntimeError("Event log has not been loaded into Declare4Py engine.")
        sets = constraint.get("activity_sets") or [_activity_set(a) for a in constraint["activities"]]
        if constraint["template"] in ("Precedence", "Alternate Precedence", "Chain Precedence", "Not Precedence"):
            names = sets[1]
        elif constraint["template"] in ("Choice", "Exclusive Choice"):
            names = sets[0] | (sets[1] if len(sets) > 1 else frozenset())
        else:
            names = sets[0]
        cond = constraint["act_cond"]
        # v1.2 (rà soát lõi, LOW): Init chỉ xét event ĐẦU TIÊN của hồ sơ (như _check_single_trace)
        first_only = constraint["template"] == "Init"
        return sum(
            any(e["concept:name"] in names and cond(e) for e in (trace["events"][:1] if first_only else trace["events"]))
            for trace in self._trace_index.values() if self._in_years(trace, years)
        )

    def case_results(self, constraint: Dict[str, Any], years: Optional[Sequence[int]] = None
                     ) -> List[Tuple[str, RuleCheckResult, List[Dict[str, Any]]]]:
        """Kết quả của MỘT ràng buộc đã phân tích trên từng hồ sơ (theo thứ tự hồ sơ), kèm event của hồ sơ.
        Cùng ngữ nghĩa với conformance_checking(consider_vacuity=True); không đổi parsed_constraints.
        years (tập Đức): chỉ hồ sơ của các năm đó; None = mọi hồ sơ."""
        if not self._trace_index:
            raise RuntimeError("Event log has not been loaded into Declare4Py engine.")
        return [(case_id, self._check_single_trace(t["events"], constraint, consider_vacuity=True), t["events"])
                for case_id, t in self._trace_index.items() if self._in_years(t, years)]

    def _in_years(self, trace: Dict[str, Any], years: Optional[Sequence[int]]) -> bool:
        if years is None:
            return True
        events = trace["events"]
        value = events[0].get(CASE_KEY, {}).get(self.year_attr) if events else None
        try:
            return int(float(value)) in {int(y) for y in years}
        except (TypeError, ValueError):
            return False

    def cases_in(self, years: Optional[Sequence[int]]) -> int:
        return sum(self._in_years(t, years) for t in self._trace_index.values())

    def trace_years(self) -> List[Optional[int]]:
        """Năm (thuộc tính year_attr) của từng hồ sơ, theo đúng thứ tự của conformance_checking."""
        out: List[Optional[int]] = []
        for t in self._trace_index.values():
            value = t["events"][0].get(CASE_KEY, {}).get(self.year_attr) if t["events"] else None
            try:
                out.append(int(float(value)))
            except (TypeError, ValueError):
                out.append(None)
        return out

    @property
    def num_cases(self) -> int:
        return len(self._trace_index)

    @staticmethod
    def _compile_data_cond(
        cond_str: str, timezone: str = DEFAULT_TIMEZONE, year_attr: str = DEFAULT_YEAR_ATTR
    ) -> Callable[[Dict[str, Any]], bool]:
        """Biên dịch điều kiện 'A.<attr> <op> <val> [and …]' / 'A.date <op> year-MM-DD' (xem data_conditions.py)."""
        return compile_condition(cond_str, timezone=timezone, year_attr=year_attr)

    def _within_time(self, ev_a: Dict[str, Any], ev_b: Dict[str, Any], window: Optional[TimeWindow]) -> bool:
        """Cửa sổ 'min,max,unit' — s/m/h/d/w cố định; mo (tháng lịch), wd (ngày làm việc) theo giờ địa phương."""
        return within(ev_a["_ts_sec"], ev_b["_ts_sec"], window, self._tz, self.calendar_periods)

    def _check_single_trace(
        self,
        events: List[Dict[str, Any]],
        constraint: Dict[str, Any],
        consider_vacuity: bool = False,
    ) -> RuleCheckResult:
        """
        Thực thi ngữ nghĩa kiểm chứng Declare4Py (Checkers.py) cho một hồ sơ vay:
        Hỗ trợ đầy đủ Response, Precedence, Alternate/Chain Response & Precedence, Existence, Absence, Init, Not Response, Not Co-Existence...
        """
        tpl = constraint["template"]
        acts = constraint["activities"]
        act_cond = constraint["act_cond"]
        time_window = constraint["time_window"]

        sets = constraint.get("activity_sets") or [_activity_set(a) for a in acts]
        set_a = sets[0]
        set_b = sets[1] if len(sets) > 1 else frozenset()

        def is_a(e: Dict[str, Any]) -> bool:
            return e["concept:name"] in set_a

        def is_b(e: Dict[str, Any]) -> bool:
            return e["concept:name"] in set_b

        num_activations = 0
        num_fulfillments = 0
        num_violations = 0

        if tpl in ("Existence", "Exactly1", "Init", "Absence"):
            matching = [e for e in events if is_a(e) and act_cond(e)]
            count = len(matching)
            if tpl == "Existence":
                num_activations = 1
                if count >= 1:
                    num_fulfillments = 1
                else:
                    num_violations = 1
            elif tpl == "Exactly1":
                num_activations = 1
                if count == 1:
                    num_fulfillments = 1
                else:
                    num_violations = 1
            elif tpl == "Absence":
                num_activations = max(1, count)
                if count == 0:
                    num_fulfillments = 1
                else:
                    num_violations = count
            elif tpl == "Init":
                num_activations = 1
                if events and is_a(events[0]) and act_cond(events[0]):
                    num_fulfillments = 1
                else:
                    num_violations = 1

        elif tpl in ("Response", "Alternate Response", "Chain Response", "Responded Existence"):
            # Trong họ Response: sự kiện A là Activation, yêu cầu sau đó (hoặc trong trace) phải có B trong khoảng thời gian
            for i, ev in enumerate(events):
                if is_a(ev) and act_cond(ev):
                    num_activations += 1
                    if tpl == "Responded Existence":
                        candidates = [e2 for e2 in events if is_b(e2)]
                    elif tpl == "Chain Response":
                        candidates = (
                            [events[i + 1]]
                            if (i + 1 < len(events) and is_b(events[i + 1]))
                            else []
                        )
                    elif tpl == "Alternate Response":
                        candidates = []
                        for e2 in events[i + 1 :]:
                            if is_a(e2):
                                break
                            if is_b(e2):
                                candidates.append(e2)
                    else:  # Response
                        candidates = [e2 for e2 in events[i + 1 :] if is_b(e2)]

                    fulfilled = any(self._within_time(ev, c, time_window) for c in candidates)
                    if fulfilled:
                        num_fulfillments += 1
                    else:
                        num_violations += 1

        elif tpl in ("Precedence", "Alternate Precedence", "Chain Precedence"):
            # Họ Precedence: KÍCH HOẠT là B (thoả act_cond); trước đó phải có A trong cửa sổ thời gian.
            # F-PREC (kiểm toán 2026-11-09, quy ước Declare4Py): act_cond CHỈ áp lên B. Trước đây áp lên cả A →
            # với điều kiện mức event (ngày) lệch chuẩn ở 963/2 000 hồ sơ BPIC2018.
            for i, ev in enumerate(events):
                if is_b(ev) and act_cond(ev):
                    num_activations += 1
                    if tpl == "Chain Precedence":
                        prior_a = [events[i - 1]] if (i - 1 >= 0 and is_a(events[i - 1])) else []
                    elif tpl == "Alternate Precedence":
                        prior_a = []
                        for e_prev in reversed(events[:i]):
                            if is_b(e_prev):
                                break
                            if is_a(e_prev):
                                prior_a.append(e_prev)
                    else:  # Precedence
                        prior_a = [e_prev for e_prev in events[:i] if is_a(e_prev)]

                    fulfilled = any(self._within_time(e_prev, ev, time_window) for e_prev in prior_a)
                    if fulfilled:
                        num_fulfillments += 1
                    else:
                        num_violations += 1

        elif tpl == "Not Precedence":
            # B (thoả act_cond, sự kiện kích hoạt — F-PREC) không được có A nào đứng trước trong cửa sổ.
            # Không điều kiện: cùng tập vi phạm với bản cũ ("A không được có B sau"); chỉ khác chỗ đếm kích hoạt.
            for i, ev in enumerate(events):
                if is_b(ev) and act_cond(ev):
                    num_activations += 1
                    if any(is_a(e0) and self._within_time(e0, ev, time_window) for e0 in events[:i]):
                        num_violations += 1
                    else:
                        num_fulfillments += 1

        elif tpl in ("Not Response", "Not Co-Existence", "Not Responded Existence"):
            for i, ev in enumerate(events):
                if is_a(ev) and act_cond(ev):
                    num_activations += 1
                    if tpl == "Not Response":
                        # LTLf G(A -> ¬F B): A (thoả act_cond) không được có B nào xảy ra SAU nó.
                        bad = [
                            e2
                            for e2 in events[i + 1 :]
                            if is_b(e2) and self._within_time(ev, e2, time_window)
                        ]
                    else:
                        bad = [e2 for e2 in events if is_b(e2)]

                    if bad:
                        num_violations += 1
                    else:
                        num_fulfillments += 1

        elif tpl in ("Choice", "Exclusive Choice"):
            # Ràng buộc mức hồ sơ (như Existence): luôn được kích hoạt, hồ sơ thiếu cả A và B là vi phạm.
            has_a = any(is_a(e) and act_cond(e) for e in events)
            has_b = any(is_b(e) and act_cond(e) for e in events)
            num_activations = 1
            if tpl == "Choice":
                if has_a or has_b:
                    num_fulfillments = 1
                else:
                    num_violations = 1
            else:  # Exclusive Choice
                if has_a ^ has_b:
                    num_fulfillments = 1
                else:
                    num_violations = 1

        else:
            raise ValueError(f"Template DECLARE không được hỗ trợ: {tpl!r}")

        if num_activations == 0:
            # Không kích hoạt = thoả (vacuous). consider_vacuity chỉ quyết định có tách nhãn riêng hay không;
            # trước đây chế độ mặc định gắn nhầm 'Violated' (xem TN4).
            state = "Vacuously Satisfied" if consider_vacuity else "Satisfied"
        elif num_violations > 0:
            state = "Violated"
        else:
            state = "Satisfied"

        return RuleCheckResult(
            num_activations=num_activations,
            num_fulfillments=num_fulfillments,
            num_violations=num_violations,
            state=state,
        )

    def conformance_checking(self, consider_vacuity: bool = False) -> Dict[Tuple[int, str], Dict[str, RuleCheckResult]]:
        """
        Thực thi conformance checking trên toàn bộ các hồ sơ vay trong Event Log,
        trả về cấu trúc tương thích hoàn toàn với Declare4Py:
          {(trace_idx, case_id): {constraint_line: RuleCheckResult}}
        """
        if not self._trace_index:
            raise RuntimeError("Event log has not been loaded into Declare4Py engine.")
        if not self.parsed_constraints:
            raise RuntimeError("No DECLARE model parsed. Call parse_decl_model() first.")

        results: Dict[Tuple[int, str], Dict[str, RuleCheckResult]] = {}
        for idx, (case_id, trace_data) in enumerate(self._trace_index.items()):
            events = trace_data["events"]
            c_map: Dict[str, RuleCheckResult] = {}
            for c in self.parsed_constraints:
                c_map[c["raw_line"]] = self._check_single_trace(
                    events, c, consider_vacuity=consider_vacuity
                )
            results[(idx, case_id)] = c_map
        return results


def extract_concrete_trace_snapshots(
    log_df: pd.DataFrame,
    sample_violations: List[Dict[str, Any]],
    ast_obj: Any,
) -> List[Dict[str, Any]]:
    """
    Bước 3.3: Trích xuất bản chụp trạng thái cụ thể (Concrete State Snapshot - theo Mục 3.4.6 của OVAS)
    cho các hồ sơ vi phạm để chuyển sang Bước 4 (Giải trình tất định).
    """
    snapshots: List[Dict[str, Any]] = []
    relevant_acts = {ast_obj.activation_activity}
    if ast_obj.target_activity:
        relevant_acts.add(ast_obj.target_activity)

    target_case_ids = [v["case_id"] for v in sample_violations]
    if not target_case_ids:
        return snapshots

    subset_df = log_df[log_df["case:concept:name"].isin(target_case_ids)]

    for v in sample_violations:
        cid = v["case_id"]
        case_events = subset_df[subset_df["case:concept:name"] == cid].sort_values("time:timestamp")
        if case_events.empty:
            continue

        # Lấy giá trị OfferedAmount và CreditScore đại diện trong hồ sơ (nếu có)
        case_offered = (
            float(case_events["OfferedAmount"].dropna().iloc[0])
            if "OfferedAmount" in case_events and not case_events["OfferedAmount"].dropna().empty
            else None
        )
        case_credit_score = (
            float(case_events["CreditScore"].dropna().iloc[0])
            if "CreditScore" in case_events and not case_events["CreditScore"].dropna().empty
            else None
        )

        focused_events: List[Dict[str, Any]] = []
        first_ts: Optional[pd.Timestamp] = None
        last_ts: Optional[pd.Timestamp] = None

        for _, row in case_events.iterrows():
            if row["concept:name"] in relevant_acts:
                ts_val = row["time:timestamp"]
                if first_ts is None:
                    first_ts = ts_val
                last_ts = ts_val
                raw_offered = row.get("OfferedAmount", None)
                offered_val = (
                    float(raw_offered)
                    if raw_offered is not None and not pd.isna(raw_offered)
                    else case_offered
                )
                focused_events.append(
                    {
                        "activity": row["concept:name"],
                        "timestamp": str(ts_val),
                        "resource": str(row.get("org:resource", "N/A")),
                        "offered_amount": offered_val,
                    }
                )

        elapsed_days = (
            round((last_ts - first_ts).total_seconds() / 86400.0, 2)
            if (first_ts is not None and last_ts is not None and last_ts >= first_ts)
            else None
        )

        snapshots.append(
            {
                "case_id": cid,
                "num_activations": v.get("num_activations", 1),
                "num_violations": v.get("num_violations", 1),
                "requested_amount": (
                    float(case_events["case:RequestedAmount"].iloc[0])
                    if "case:RequestedAmount" in case_events
                    and not pd.isna(case_events["case:RequestedAmount"].iloc[0])
                    else None
                ),
                "offered_amount": case_offered,
                "credit_score": case_credit_score,
                "elapsed_days_between_relevant_events": elapsed_days,
                "full_trace_sequence": case_events["concept:name"].tolist(),
                "violating_event_pairs": focused_events,
            }
        )
    return snapshots


def run_layer3_declare4py_verifier(
    d4py_engine: Declare4Py,
    log_df: pd.DataFrame,
    ast_obj: Any,
    decl_line: str,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Bước 3.2: Thực thi Declare4Py conformance checking & Vacuity Check (Mục 3.4.6 bài OCL2026)
    trên toàn bộ 31.509 hồ sơ của BPI Challenge 2017.
    """
    # 1. Ghi dòng ràng buộc chuẩn ra file .decl tạm thời theo định dạng của Declare4Py
    header = f"activity {ast_obj.activation_activity}\n"
    if ast_obj.target_activity:
        header += f"activity {ast_obj.target_activity}\n"

    with tempfile.NamedTemporaryFile("w", suffix=".decl", delete=False, encoding="utf-8") as tmp:
        tmp.write(header + decl_line + "\n")
        tmp_decl_path = tmp.name

    try:
        # 2. Gọi parser và bộ kiểm chứng của Declare4Py
        d4py_engine.parse_decl_model(model_path=tmp_decl_path)
        # consider_vacuity=False giúp tách biệt rõ trace thực sự kích hoạt quy tắc với trace rỗng
        check_results = d4py_engine.conformance_checking(consider_vacuity=False)
    finally:
        if os.path.exists(tmp_decl_path):
            os.remove(tmp_decl_path)

    # 3. Tổng hợp thống kê kích hoạt / vi phạm (theo chuẩn đánh giá của Janus - arXiv:2510.07161)
    total_activations = 0
    total_fulfillments = 0
    total_violations = 0
    satisfied_cases: List[str] = []
    violated_cases: List[Dict[str, Any]] = []
    vacuous_cases = 0

    for trace_idx, constraints_res in check_results.items():
        rule_res = list(constraints_res.values())[0]
        case_id = trace_idx[1] if isinstance(trace_idx, tuple) else str(trace_idx)

        if rule_res.num_activations == 0:
            vacuous_cases += 1
        else:
            total_activations += rule_res.num_activations
            total_fulfillments += rule_res.num_fulfillments
            total_violations += rule_res.num_violations
            if rule_res.num_violations > 0 or rule_res.state == "Violated":
                violated_cases.append(
                    {
                        "case_id": case_id,
                        "num_activations": rule_res.num_activations,
                        "num_violations": rule_res.num_violations,
                    }
                )
            else:
                satisfied_cases.append(case_id)

    # 4. KIỂM TRA TÍNH KHÔNG RỖNG (Vacuity Check - kế thừa Mục 3.4.6 của bài OCL2026):
    if total_activations == 0:
        return False, {
            "error_type": "VACUOUS_CONSTRAINT",
            "feedback": (
                f"[Layer 3 Vacuity Failure]: The constraint '{decl_line}' had 0 activations across all "
                f"{len(check_results)} cases in the BPIC 2017 log. Please select a valid activation activity "
                f"or relax the attribute condition."
            ),
        }

    # 5. Nếu hợp lệ (total_activations > 0): Trích xuất Concrete Counterexample Snapshot (Mục 3.4.6 bài OCL2026)
    counterexamples = extract_concrete_trace_snapshots(
        log_df, violated_cases[:5], ast_obj
    )

    activated_count = len(satisfied_cases) + len(violated_cases)
    return True, {
        "article_id": getattr(ast_obj, "article_id", ""),
        "decl_formula": decl_line,
        "total_cases": len(check_results),
        "activated_cases_count": activated_count,
        "satisfied_cases_count": len(satisfied_cases),
        "violated_cases_count": len(violated_cases),
        "vacuous_cases_count": vacuous_cases,
        "total_event_activations": total_activations,
        "total_event_fulfillments": total_fulfillments,
        "total_event_violations": total_violations,
        "compliance_rate": round(len(satisfied_cases) / activated_count * 100, 2)
        if activated_count > 0
        else 0.0,
        "counterexample_snapshots": counterexamples,
    }
