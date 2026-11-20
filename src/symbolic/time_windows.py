"""
Cửa sổ thời gian 'min,max,unit' của dòng .decl (F-UNITS, kiểm toán 2026-11-09).

Đơn vị cố định (đổi ra giây, như trước): s, m (phút), h, d (ngày lịch), w (tuần = 7 ngày).
Đơn vị theo lịch (không đổi ra số giây cố định — quy tắc mục 7: "một tháng không phải 30/90 ngày"):
  mo  tháng theo lịch: B nằm trong [A + min tháng, A + max tháng], cộng tháng trên giờ địa phương (dateutil)
  wd  ngày làm việc Thứ Hai–Thứ Sáu: số ngày làm việc trong [ngày(A), ngày(B)) thuộc [min, max].
      KHÔNG trừ ngày lễ (log không có lịch lễ của bang) → hơi lỏng hơn luật ở tuần có ngày lễ.
Đơn vị lạ → ngày (giữ hành vi cũ của engine).
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import numpy as np
from dateutil.relativedelta import relativedelta

FIXED_SECONDS = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0, "w": 7 * 86400.0}
CALENDAR_UNITS = ("mo", "wd")
DEFAULT_UNIT = "d"


@dataclass(frozen=True)
class TimeWindow:
    lo: float
    hi: float
    unit: str


def parse_time_window(text: str) -> Optional[TimeWindow]:
    if not text:
        return None
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 3:
        return None
    try:
        lo, hi = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    unit = parts[2].lower()
    return TimeWindow(lo, hi, unit if unit in FIXED_SECONDS or unit in CALENDAR_UNITS else DEFAULT_UNIT)


CALENDAR_PERIOD_UNITS = ("d", "w", "mo")


def _add_period(day: date, n: int, unit: str) -> date:
    return day + (relativedelta(months=n) if unit == "mo" else timedelta(days=n * (7 if unit == "w" else 1)))


def _roll_weekend(day: date) -> date:
    """Quy định 1182/71 Điều 3(4): hạn rơi vào Thứ Bảy / Chủ Nhật → kết thúc cuối ngày làm việc kế tiếp (lễ: không có dữ liệu)."""
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def within_calendar(early_local: datetime, late_local: datetime, window: TimeWindow) -> bool:
    """
    F-DAYS (kiểm toán đợt 2) — thời hạn ngày / tuần / tháng theo Quy định (EEC, Euratom) số 1182/71: không tính ngày
    xảy ra sự kiện, hạn chót là HẾT ngày cuối (so theo ngày lịch địa phương, không theo n×24 giờ); tháng: cùng
    số ngày của tháng sau, thiếu ngày đó thì ngày cuối tháng (relativedelta); cuối tuần → ngày làm việc kế tiếp.
    """
    da, db = early_local.date(), late_local.date()
    lower = _add_period(da, int(window.lo), window.unit)
    upper = _roll_weekend(_add_period(da, int(window.hi), window.unit))
    return lower <= db <= upper


def within(ts_a: float, ts_b: float, window: Optional[TimeWindow], tz: ZoneInfo, calendar_periods: bool = False) -> bool:
    """
    Khoảng cách giữa hai sự kiện (giây epoch, không phân biệt thứ tự — như engine cũ) nằm trong cửa sổ.
    calendar_periods=True (bộ CAP): d / w / mo tính theo ngày lịch (within_calendar); mặc định: n×24 giờ như cũ.
    """
    if window is None:
        return True
    early, late = sorted((float(ts_a), float(ts_b)))
    if calendar_periods and window.unit in CALENDAR_PERIOD_UNITS:
        return within_calendar(datetime.fromtimestamp(early, tz), datetime.fromtimestamp(late, tz), window)
    if window.unit in FIXED_SECONDS:
        scale = FIXED_SECONDS[window.unit]
        return window.lo * scale <= late - early <= window.hi * scale
    da, db = datetime.fromtimestamp(early, tz), datetime.fromtimestamp(late, tz)
    if window.unit == "mo":
        return da + relativedelta(months=int(window.lo)) <= db <= da + relativedelta(months=int(window.hi))
    # v1.2 (rà soát lõi C4): sự kiện vào cuối tuần được tính như xảy ra ngày làm việc liền trước (thứ Sáu), nên thứ
    # Hai là ngày làm việc 1 (Reg 1182/71 không đếm ngày của sự kiện). Trước đây đếm từ chính thứ Bảy → lệch một ngày
    # (thứ Bảy → thứ Tư vẫn '≤ 2 ngày làm việc').
    start = np.busday_offset(da.date(), 0, roll="backward")
    n = int(np.busday_count(start, db.date()))
    return window.lo <= n <= window.hi
