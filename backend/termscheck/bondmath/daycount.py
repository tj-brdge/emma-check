"""Day-count conventions and calendar helpers. Pure functions."""
from __future__ import annotations

import calendar
from datetime import date

from .models import DayCount


def is_last_day_of_feb(d: date) -> bool:
    return d.month == 2 and d.day == calendar.monthrange(d.year, 2)[1]


def days_30_360(d1: date, d2: date) -> int:
    """30/360 per MSRB Rule G-33(b)(i)(B) / SIA bond basis with end-of-February rules.

    1. If D1 and D2 are both the last day of February, D2 -> 30.
    2. If D1 is the last day of February, D1 -> 30.
    3. If D2 is 31 and D1 is 30 or 31, D2 -> 30.
    4. If D1 is 31, D1 -> 30.
    """
    y1, m1, dd1 = d1.year, d1.month, d1.day
    y2, m2, dd2 = d2.year, d2.month, d2.day
    if is_last_day_of_feb(d1) and is_last_day_of_feb(d2):
        dd2 = 30
    if is_last_day_of_feb(d1):
        dd1 = 30
    if dd2 == 31 and dd1 >= 30:
        dd2 = 30
    if dd1 == 31:
        dd1 = 30
    return 360 * (y2 - y1) + 30 * (m2 - m1) + (dd2 - dd1)


def day_count_days(dc: DayCount, d1: date, d2: date) -> int:
    if dc is DayCount.THIRTY_360:
        return days_30_360(d1, d2)
    return (d2 - d1).days


def year_fraction(
    dc: DayCount,
    d1: date,
    d2: date,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    frequency: int = 2,
) -> float:
    """Year fraction between d1 and d2.

    ACT/ACT (ICMA) needs the enclosing coupon/compounding period; when omitted it falls
    back to actual/365.25-free form: actual days / actual days in the year of d1.
    """
    if dc is DayCount.THIRTY_360:
        return days_30_360(d1, d2) / 360.0
    if dc is DayCount.ACT_360:
        return (d2 - d1).days / 360.0
    if dc is DayCount.ACT_365:
        return (d2 - d1).days / 365.0
    if period_start is not None and period_end is not None:
        return (d2 - d1).days / (frequency * (period_end - period_start).days)
    ydays = 366 if calendar.isleap(d1.year) else 365
    return (d2 - d1).days / ydays


def period_fraction(dc: DayCount, start: date, end: date, d: date, frequency: int) -> float:
    """Fraction (0..1) of the period [start, end] elapsed at d, under the day count.

    For 30/360 a regular semiannual period is 180 days, so the fraction is days/180.
    For actual conventions it is actual days / actual days in the period.
    """
    if dc is DayCount.THIRTY_360:
        total = days_30_360(start, end)
        return days_30_360(start, d) / total if total else 0.0
    total = (end - start).days
    return (d - start).days / total if total else 0.0


def add_months(d: date, months: int) -> date:
    """Add months, clamping the day to the target month's length."""
    total = d.year * 12 + (d.month - 1) + months
    y, m = divmod(total, 12)
    m += 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))
