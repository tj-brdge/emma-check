"""Coupon and compounding date schedules. Pure functions."""
from __future__ import annotations

from datetime import date

from .daycount import add_months


def regular_schedule(start: date, end: date, frequency: int, first: date | None = None) -> list[date]:
    """Dates in (start, end], ending exactly on ``end``.

    Without ``first``, the schedule is generated backward from ``end`` in steps of
    12/frequency months (the usual muni convention; any stub falls at the front).
    With ``first``, it runs forward from ``first`` and ends on ``end``.
    Generation uses offsets from a single anchor so month-end days never drift.
    """
    if frequency <= 0:
        raise ValueError("frequency must be positive")
    step = 12 // frequency
    out: list[date] = []
    if first is None:
        k = 0
        while True:
            d = add_months(end, -step * k)
            if d <= start:
                break
            out.append(d)
            k += 1
        out.reverse()
    else:
        if not (start < first <= end):
            raise ValueError("first date must fall in (start, end]")
        k = 0
        while True:
            d = add_months(first, step * k)
            if d >= end:
                break
            out.append(d)
            k += 1
        out.append(end)
    return out


def bracket(schedule: list[date], start: date, d: date) -> tuple[date, date | None]:
    """Return (previous date <= d, next date > d), treating ``start`` as the period-0 date."""
    prev = start
    for s in schedule:
        if s <= d:
            prev = s
        else:
            return prev, s
    return prev, None
