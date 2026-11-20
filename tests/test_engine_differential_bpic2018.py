"""
Kiểm toán bước 1 — kiểm thử CHÉO engine DECLARE (src/symbolic/declare4py_verifier.py) trên BPIC2018 THẬT.

Bộ kiểm tham chiếu dưới đây viết lại từ đầu theo ngữ nghĩa DECLARE chuẩn (Declare4Py: điều kiện kích hoạt áp lên
sự kiện KÍCH HOẠT — A với họ Response/Not/unary, B với họ Precedence), KHÔNG dùng code của engine hay
data_conditions (điều kiện viết lại bằng Python thuần, ngày tính theo giờ Europe/Berlin bằng zoneinfo).
So trạng thái từng hồ sơ (Satisfied / Violated / Vacuously Satisfied) trên một mẫu 2 000 hồ sơ (seed cố định),
với mọi mẫu, mọi loại điều kiện (thuộc tính hồ sơ chuỗi / Boolean / số, ngày lịch theo năm hồ sơ, thuộc tính
event), có và không có cửa sổ thời gian.

F-PREC (điều kiện của họ Precedence chỉ trên B) đã sửa 2026-11-09; cửa sổ w / mo / wd so với tham chiếu pandas.
Cần data/interim/bpic2018_{events,cases}.parquet; không có → bỏ qua.
"""

import random
import sys
import unittest
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.kg.process_graph_builder import with_composite_activity  # noqa: E402
from src.symbolic.declare4py_verifier import Declare4Py  # noqa: E402

EVENTS = PROJECT_ROOT / "data" / "interim" / "bpic2018_events.parquet"
CASES = PROJECT_ROOT / "data" / "interim" / "bpic2018_cases.parquet"
SAMPLE, SEED, TZ = 2000, 7, ZoneInfo("Europe/Berlin")
APP = "Payment application / Application"
A, B = f"{APP} / begin editing", f"{APP} / calculate"
MAIL, PAY = f"{APP} / mail income", f"{APP} / begin payment"
DAY = 86400.0

Ev = Dict[str, Any]
Cond = Callable[[Ev, Dict[str, Any]], bool]


def _local(ev: Ev) -> date:
    return ev["ts"].tz_convert(TZ).date()


def _year(case: Dict[str, Any]) -> int:
    return int(case["case:year"])


# (dòng điều kiện .decl, điều kiện tham chiếu, chỉ ở mức hồ sơ?)
CONDS: Dict[str, Tuple[str, Cond, bool]] = {
    "none": ("", lambda e, c: True, True),
    "young": ("A.case:young farmer == True", lambda e, c: bool(c["case:young farmer"]), True),
    "year": ("A.case:year == 2016", lambda e, c: c["case:year"] == "2016", True),
    "area": ("A.case:area > 50", lambda e, c: c["case:area"] > 50, True),
    "dept": ('A.case:department == "e7"', lambda e, c: c["case:department"] == "e7", True),
    "date": ("A.date <= year-05-15", lambda e, c: _local(e) <= date(_year(c), 5, 15), False),
    "window": ("A.date >= year-12-01 and A.date <= year+1-06-30",
               lambda e, c: date(_year(c), 12, 1) <= _local(e) <= date(_year(c) + 1, 6, 30), False),
    "success": ("A.success == True", lambda e, c: bool(e["success"]), False),
    "both": ("A.case:young farmer == True and A.date <= year-05-15",
             lambda e, c: bool(c["case:young farmer"]) and _local(e) <= date(_year(c), 5, 15), False),
}
WINDOWS = {"": None, "0,30,d": (0.0, 30 * DAY, "s"), "0,2,d": (0.0, 2 * DAY, "s"), "0,2,w": (0.0, 14 * DAY, "s"),
           "0,1,mo": (0, 1, "mo"), "1,3,mo": (1, 3, "mo"), "0,2,wd": (0, 2, "wd")}


def _within(ea: Ev, eb: Ev, w) -> bool:
    """Tham chiếu độc lập với src/symbolic/time_windows.py: pandas DateOffset (tháng lịch), bdate_range (ngày làm việc)."""
    if w is None:
        return True
    early, late = sorted((ea["ts"], eb["ts"]))
    if w[2] == "s":
        return w[0] <= (late - early).total_seconds() <= w[1]
    le, ll = early.tz_convert(TZ), late.tz_convert(TZ)
    if w[2] == "mo":
        return le + pd.DateOffset(months=w[0]) <= ll <= le + pd.DateOffset(months=w[1])
    n = len(pd.bdate_range(le.date(), ll.date(), inclusive="left"))
    return w[0] <= n <= w[1]


def reference_state(tpl: str, a: str, b: Optional[str], cond: Cond, w, evs: List[Ev], case: Dict[str, Any]) -> str:
    """Ngữ nghĩa DECLARE chuẩn, viết độc lập với engine. Trả trạng thái như engine (consider_vacuity=True)."""
    act = lambda e: cond(e, case)  # noqa: E731
    is_a = lambda e: e["name"] == a  # noqa: E731
    is_b = lambda e: e["name"] == b  # noqa: E731
    acts, viol = 0, 0
    n = len(evs)
    if tpl in ("Existence", "Exactly1", "Init", "Absence"):
        k = sum(1 for e in evs if is_a(e) and act(e))
        ok = {"Existence": k >= 1, "Exactly1": k == 1, "Absence": k == 0,
              "Init": bool(evs) and is_a(evs[0]) and act(evs[0])}[tpl]
        return "Satisfied" if ok else "Violated"
    if tpl in ("Choice", "Exclusive Choice"):
        ha, hb = any(is_a(e) and act(e) for e in evs), any(is_b(e) and act(e) for e in evs)
        ok = (ha or hb) if tpl == "Choice" else (ha != hb)
        return "Satisfied" if ok else "Violated"
    for i, e in enumerate(evs):
        if tpl in ("Response", "Alternate Response", "Chain Response", "Responded Existence",
                   "Not Response", "Not Co-Existence", "Not Responded Existence"):
            if not (is_a(e) and act(e)):
                continue
            acts += 1
            if tpl == "Response":
                good = any(is_b(f) and _within(e, f, w) for f in evs[i + 1:])
            elif tpl == "Chain Response":
                good = i + 1 < n and is_b(evs[i + 1]) and _within(e, evs[i + 1], w)
            elif tpl == "Alternate Response":
                good = False
                for f in evs[i + 1:]:
                    if is_a(f):
                        break
                    if is_b(f) and _within(e, f, w):
                        good = True
                        break
            elif tpl == "Responded Existence":
                good = any(is_b(f) and _within(e, f, w) for f in evs)
            elif tpl == "Not Response":
                good = not any(is_b(f) and _within(e, f, w) for f in evs[i + 1:])
            else:  # Not Co-Existence / Not Responded Existence
                good = not any(is_b(f) for f in evs)
        else:  # họ Precedence: kích hoạt = B thoả điều kiện; mục tiêu A KHÔNG kèm điều kiện (Declare4Py)
            if not (is_b(e) and act(e)):
                continue
            acts += 1
            if tpl == "Precedence":
                good = any(is_a(f) and _within(f, e, w) for f in evs[:i])
            elif tpl == "Chain Precedence":
                good = i > 0 and is_a(evs[i - 1]) and _within(evs[i - 1], e, w)
            elif tpl == "Not Precedence":
                good = not any(is_a(f) and _within(f, e, w) for f in evs[:i])
            else:  # Alternate Precedence
                good = False
                for f in reversed(evs[:i]):
                    if is_b(f):
                        break
                    if is_a(f) and _within(f, e, w):
                        good = True
                        break
        viol += not good
    if acts == 0:
        return "Vacuously Satisfied"
    return "Violated" if viol else "Satisfied"


UNARY = ["Existence", "Absence", "Exactly1", "Init"]
RESPONSE_SIDE = ["Response", "Alternate Response", "Chain Response", "Responded Existence", "Not Response",
                 "Not Co-Existence", "Not Responded Existence", "Choice", "Exclusive Choice"]
PRECEDENCE = ["Precedence", "Alternate Precedence", "Chain Precedence", "Not Precedence"]
CASE_LEVEL = [k for k, v in CONDS.items() if v[2]]
EVENT_LEVEL = [k for k, v in CONDS.items() if not v[2]]


@unittest.skipUnless(EVENTS.exists() and CASES.exists(), "cần data/interim/bpic2018_*.parquet")
class TestEngineMatchesReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cases = pd.read_parquet(CASES)
        ids = sorted(random.Random(SEED).sample(sorted(cases["case:concept:name"]), SAMPLE))
        cls.cases = cases[cases["case:concept:name"].isin(ids)].reset_index(drop=True)
        ev = pd.read_parquet(EVENTS, filters=[("case:concept:name", "in", ids)])
        ev = with_composite_activity(ev)
        cls.engine = Declare4Py(ev, cases=cls.cases, timezone="Europe/Berlin")
        ev = ev.sort_values(["case:concept:name", "time:timestamp"], kind="mergesort")
        cls.case_rec = cls.cases.set_index("case:concept:name").to_dict("index")
        cls.traces = {cid: [{"name": r["concept:name"], "ts": r["time:timestamp"], "success": r["success"]}
                            for r in g.to_dict("records")] for cid, g in ev.groupby("case:concept:name", sort=False)}

    def _diff(self, tpl: str, a: str, b: Optional[str], cond_key: str, win: str = "") -> List[str]:
        line_cond, ref_cond, _ = CONDS[cond_key]
        acts = f"{a}, {b}" if b else a
        line = f"{tpl}[{acts}] | {line_cond} | | {win}"
        parsed = self.engine.parse_decl_lines([line])[0]
        bad = []
        for cid, evs in self.traces.items():
            got = self.engine._check_single_trace(self.engine._trace_index[str(cid)]["events"], parsed,
                                                  consider_vacuity=True).state
            want = reference_state(tpl, a, b, ref_cond, WINDOWS[win], evs, self.case_rec[cid])
            if got != want:
                bad.append(f"{cid}: engine={got} ref={want}")
        return bad

    def test_sample_is_nontrivial(self) -> None:
        self.assertEqual(len(self.traces), SAMPLE)
        self.assertGreater(sum(any(e["name"] == MAIL for e in t) for t in self.traces.values()), 100)

    def test_unary_all_conditions(self) -> None:
        for tpl in UNARY:
            for ck in CONDS:
                with self.subTest(tpl=tpl, cond=ck):
                    self.assertEqual(self._diff(tpl, MAIL, None, ck)[:3], [])

    def test_response_side_all_conditions(self) -> None:
        for tpl in RESPONSE_SIDE:
            for ck in CONDS:
                with self.subTest(tpl=tpl, cond=ck):
                    self.assertEqual(self._diff(tpl, A, B, ck)[:3], [])

    def test_time_windows(self) -> None:
        for tpl in ("Response", "Chain Response", "Alternate Response", "Not Response", "Precedence",
                    "Not Precedence", "Alternate Precedence"):
            for win in ("0,30,d", "0,2,d", "0,2,w", "0,1,mo", "1,3,mo", "0,2,wd"):
                with self.subTest(tpl=tpl, win=win):
                    self.assertEqual(self._diff(tpl, MAIL, PAY, "none", win)[:3], [])

    def test_precedence_case_level_conditions(self) -> None:
        """Điều kiện mức hồ sơ giống nhau ở A và B → engine và chuẩn trùng nhau dù áp điều kiện lên cả A."""
        for tpl in PRECEDENCE:
            for ck in CASE_LEVEL:
                with self.subTest(tpl=tpl, cond=ck):
                    self.assertEqual(self._diff(tpl, A, B, ck)[:3], [])

    def test_precedence_event_level_conditions(self) -> None:
        """
        AUDIT F-PREC (đã sửa 2026-11-09): trước đây engine áp điều kiện lên CẢ A (Declare4Py chỉ áp lên B) —
        lệch 963/2 000 hồ sơ với khoảng ngày. Gồm cả Not Precedence (kích hoạt = B).
        """
        diffs = [d for tpl in PRECEDENCE for ck in EVENT_LEVEL for d in self._diff(tpl, A, B, ck)]
        self.assertEqual(diffs[:3], [])


if __name__ == "__main__":
    unittest.main()
