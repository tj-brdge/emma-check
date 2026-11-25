"""Price drift: a 'clean' price rising smoothly faster than the vendor's own terms explain,
consistent with accrued interest embedded in the price.

Method (yield space, so rate moves are removed in proportion to each bond's duration):
1. Take each holding's clean price history (>= drift_min_points over >= drift_min_span_days).
2. Convert every price to the yield implied by the vendor's terms on that date. If the vendor
   terms were right, this series moves only with the market plus noise.
3. Market adjustment: subtract the cumulative median yield change of the same maturity band.
4. Fit adjusted yield = a + b*t. Embedded accrual shows up as a steady, high-R^2 *fall* in
   implied yield. Convert to unexplained price drift: excess = -b(per yr) * modified duration.
5. Flag when R^2 >= drift_min_r2, excess >= drift_min_excess_pct and the adjusted yield falls
   at least drift_min_yield_slope_bp per year (filters random-walk trends in long zeros).
"""
from __future__ import annotations

import statistics
from datetime import date

from termscheck.screens.base import ScreenContext, clamp_severity
from termscheck.plugins.muni.screens.common import maturity_band, vendor_implied_yield, years_between
from termscheck.screens.config import ScreenConfig
from termscheck.core.records import Flag, PricePoint, ScreenInput, SecurityRecord


def linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Least squares y = a + b x. Returns (a, b, r2)."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0:
        return my, 0.0, 0.0
    b = sxy / sxx
    a = my - b * mx
    r2 = (sxy * sxy) / (sxx * syy) if syy > 0 else 1.0
    return a, b, r2


def modified_duration(rec: SecurityRecord, d: date, price: float) -> float | None:
    """Numerical price sensitivity under vendor terms: -(dP/dy)/P via a 1bp bump on price."""
    y0 = vendor_implied_yield(rec, d, price)
    y1 = vendor_implied_yield(rec, d, price * 1.0001)
    if y0 is None or y1 is None or y1 == y0:
        return None
    return 0.0001 / (y0 - y1)


class PriceDriftScreen:
    confidence = 0.6
    rule = "price_drift"

    def run(self, data: ScreenInput, config: ScreenConfig, ctx: ScreenContext) -> list[Flag]:
        series: dict[str, tuple[list[PricePoint], list[float]]] = {}
        for cusip, pts in data.history.items():
            rec = data.primary.get(cusip)
            if rec is None:
                continue
            pts = sorted((p for p in pts if p.convention.lower() == "clean"), key=lambda p: p.price_date)
            if len(pts) < config.drift_min_points:
                continue
            if (pts[-1].price_date - pts[0].price_date).days < config.drift_min_span_days:
                continue
            ys = [vendor_implied_yield(rec, p.price_date, p.price) for p in pts]
            if any(y is None for y in ys):
                continue
            series[cusip] = (pts, ys)  # type: ignore[assignment]

        band = {c: maturity_band(years_between(data.as_of, data.primary[c].maturity_date)) for c in series}
        market: dict[tuple[str, date, date], float] = {}
        if config.drift_market_adjust:
            moves: dict[tuple[str, date, date], list[float]] = {}
            for c, (pts, ys) in series.items():
                for i in range(1, len(pts)):
                    key = (band[c], pts[i - 1].price_date, pts[i].price_date)
                    moves.setdefault(key, []).append(ys[i] - ys[i - 1])
            market = {k: statistics.median(v) for k, v in moves.items() if len(v) >= 5}

        flags: list[Flag] = []
        for cusip, (pts, ys) in series.items():
            rec = data.primary[cusip]
            adj = [ys[0]]
            cum = 0.0
            for i in range(1, len(pts)):
                cum += market.get((band[cusip], pts[i - 1].price_date, pts[i].price_date), 0.0)
                adj.append(ys[i] - cum)
            first, last = pts[0].price_date, pts[-1].price_date
            xs = [(p.price_date - first).days for p in pts]
            _, slope, r2 = linear_fit(xs, adj)
            slope_yr = slope * 365.0
            dur = modified_duration(rec, last, pts[-1].price)
            if dur is None:
                continue
            excess = -slope_yr * dur
            if (r2 >= config.drift_min_r2 and excess >= config.drift_min_excess_pct
                    and -slope_yr * 1e4 >= config.drift_min_yield_slope_bp):
                flags.append(Flag(
                    self.rule, cusip,
                    clamp_severity(40 + excess * 300 + (r2 - config.drift_min_r2) * 50),
                    f"'Clean' price {pts[0].price:.3f} -> {pts[-1].price:.3f}: implied yield under vendor "
                    f"terms falls {slope_yr * 1e4:+.0f} bp/yr net of market (R² {r2:.3f}), i.e. "
                    f"{excess:.1%}/yr of price growth the vendor terms do not explain - consistent "
                    "with embedded accrual.",
                    {"points": len(pts), "first_date": first.isoformat(), "last_date": last.isoformat(),
                     "first_price": pts[0].price, "last_price": pts[-1].price, "coupon": rec.coupon,
                     "price_convention": rec.price_convention},
                    {"adj_yield_slope_bp_per_year": slope_yr * 1e4, "r2": r2,
                     "modified_duration": dur, "excess_pct_per_year": excess,
                     "implied_yield_first": ys[0], "implied_yield_last": ys[-1],
                     "market_adjusted": bool(market), "maturity_band": band[cusip]}))
        return flags
