"""Price <-> yield on a maturity-anchored compounding grid (MSRB G-33 style). Pure functions.

Discount exponent for a cash flow on date c seen from settlement s:
    t = DSC/E + (whole grid periods between the next grid date after s and c)
where the grid is generated backward from maturity every 12/f months, and DSC/E is the
fraction of the current period remaining at s on the bond's day-count basis.
Simplification vs. G-33: bonds within one period of maturity are still discounted with
compound (not simple) interest. Callable bonds are priced to maturity only.
"""
from __future__ import annotations

from datetime import date

from .daycount import add_months, period_fraction, year_fraction
from .models import CashFlow, DayCount


def _grid_index_after(s: date, anchor: date, f: int) -> int:
    """Largest k such that add_months(anchor, -step*k) > s."""
    step = 12 // f
    k = 0
    while add_months(anchor, -step * (k + 1)) > s:
        k += 1
    return k


def discount_periods(s: date, c: date, anchor: date, f: int, dc: DayCount) -> float:
    step = 12 // f
    if c <= s:
        return 0.0
    k_s = _grid_index_after(s, anchor, f)
    g = add_months(anchor, -step * k_s)
    prev = add_months(anchor, -step * (k_s + 1))
    frac_remaining = 1.0 - period_fraction(dc, prev, g, s, f)
    # locate c on the grid
    k = 0
    while True:
        gd = add_months(anchor, -step * k)
        if gd == c:
            return frac_remaining + (k_s - k)
        if gd < c or k > k_s:
            break
        k += 1
    return year_fraction(dc, s, c) * f  # off-grid fallback


def dirty_price_from_yield(
    flows: list[CashFlow], settle: date, y: float, *, anchor: date, frequency: int = 2,
    day_count: DayCount = DayCount.THIRTY_360,
) -> float:
    return _pv(_timed(flows, settle, anchor, frequency, day_count), y, frequency)


def _timed(flows: list[CashFlow], settle: date, anchor: date, f: int, dc: DayCount) -> list[tuple[float, float]]:
    return [(cf.amount, discount_periods(settle, cf.date, anchor, f, dc)) for cf in flows if cf.date > settle]


def _pv(timed: list[tuple[float, float]], y: float, f: int) -> float:
    base = 1.0 + y / f
    return sum(a * base ** (-t) for a, t in timed)


def yield_from_dirty_price(
    flows: list[CashFlow], settle: date, price: float, *, anchor: date, frequency: int = 2,
    day_count: DayCount = DayCount.THIRTY_360, lo: float = -0.9, hi: float = 2.0, tol: float = 1e-10,
) -> float | None:
    """Solve for the yield (annual, compounded ``frequency``) that reproduces the dirty price.

    Price is strictly decreasing in yield for non-negative flows, so bisection is robust.
    Returns None when no yield in [lo, hi] reproduces the price.
    """
    if price <= 0 or not any(cf.date > settle for cf in flows):
        return None

    timed = _timed(flows, settle, anchor, frequency, day_count)

    def f(y: float) -> float:
        return _pv(timed, y, frequency) - price

    flo, fhi = f(lo), f(hi)
    if flo < 0 or fhi > 0:
        return None
    for _ in range(300):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if abs(fm) < tol:
            return mid
        if fm > 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
