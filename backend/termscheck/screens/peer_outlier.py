"""Peer outlier: yield far outside what peers in the same sector, rating bucket and maturity
band imply.

With a few hundred holdings, exact sector x rating x band buckets are usually too thin for a
stable median, so peers are modelled additively and robustly (Tukey median polish):

    yield = level + maturity_band_effect + rating_effect + sector_effect + residual

Effects are medians, so a handful of bad prints cannot move them. A bond is flagged when its
robust z-score, 0.6745 * residual / MAD(residuals), exceeds ``peer_z_threshold``. MAD is
floored at ``peer_mad_floor_bp``. Factor levels with fewer than ``peer_min_level``
observations get no effect of their own (they fall back to the remaining factors).
"""
from __future__ import annotations

import statistics

from .base import ScreenContext, clamp_severity
from .common import rating_bucket, years_between
from .config import ScreenConfig
from .models import Flag, ScreenInput

FINE_BANDS = [(0, 3), (3, 5), (5, 7), (7, 10), (10, 15), (15, 20), (20, 25), (25, 100)]


def fine_band(years: float) -> str:
    for lo, hi in FINE_BANDS:
        if lo <= years < hi:
            return f"{lo}-{hi}y" if hi < 100 else f"{lo}y+"
    return "0-3y"


def median_polish(rows: list[tuple[float, tuple[str, ...]]], min_n: int, iters: int = 10):
    """Fit y = level + sum(effects[f][level_f]) by iterated medians. Returns (level, effects)."""
    nf = len(rows[0][1])
    level = statistics.median(y for y, _ in rows)
    effects: list[dict[str, float]] = [dict() for _ in range(nf)]
    counts = [dict() for _ in range(nf)]
    for _, k in rows:
        for f in range(nf):
            counts[f][k[f]] = counts[f].get(k[f], 0) + 1

    def fitted(k):
        return level + sum(effects[f].get(k[f], 0.0) for f in range(nf))

    for _ in range(iters):
        for f in range(nf):
            groups: dict[str, list[float]] = {}
            for y, k in rows:
                partial = y - (fitted(k) - effects[f].get(k[f], 0.0))
                groups.setdefault(k[f], []).append(partial)
            effects[f] = {lv: statistics.median(v) for lv, v in groups.items() if counts[f][lv] >= min_n}
        resid = [y - fitted(k) for y, k in rows]
        level += statistics.median(resid)
    return level, effects


class PeerOutlierScreen:
    rule = "peer_outlier"

    def run(self, data: ScreenInput, config: ScreenConfig, ctx: ScreenContext) -> list[Flag]:
        rows: list[tuple[float, tuple[str, str, str]]] = []
        cusips: list[str] = []
        for cusip, rec in data.primary.items():
            y = rec.vendor_yield if rec.vendor_yield is not None else ctx.implied_yields.get(cusip)
            if y is None:
                continue
            key = (fine_band(years_between(data.as_of, rec.maturity_date)), rating_bucket(rec.rating), rec.sector)
            rows.append((y, key))
            cusips.append(cusip)
        if len(rows) < 10:
            return []
        level, effects = median_polish(rows, config.peer_min_level)

        def expected(k):
            return level + sum(effects[f].get(k[f], 0.0) for f in range(3))

        resid = [y - expected(k) for y, k in rows]
        mad_raw = statistics.median(abs(r) for r in resid)
        mad = max(mad_raw, config.peer_mad_floor_bp / 1e4)
        flags: list[Flag] = []
        for cusip, (y, k), r in zip(cusips, rows, resid):
            z = 0.6745 * r / mad
            if abs(z) > config.peer_z_threshold:
                rec = data.primary[cusip]
                flags.append(Flag(
                    self.rule, cusip, clamp_severity(25 + abs(z) * 5),
                    f"Yield {y:.2%} vs {expected(k):.2%} expected for {rec.sector} / {k[1]} / {k[0]} "
                    f"peers ({r * 1e4:+.0f} bp, robust z {z:+.1f}).",
                    {"yield": y, "yield_source": "vendor" if rec.vendor_yield is not None else "implied",
                     "sector": rec.sector, "rating": rec.rating, "rating_bucket": k[1], "maturity_band": k[0]},
                    {"peer_expected_yield": expected(k), "residual_bp": r * 1e4, "z": z,
                     "mad_bp": mad * 1e4, "mad_raw_bp": mad_raw * 1e4, "threshold": config.peer_z_threshold,
                     "effects_bp": {"level": level * 1e4,
                                    "maturity_band": effects[0].get(k[0], 0.0) * 1e4,
                                    "rating": effects[1].get(k[1], 0.0) * 1e4,
                                    "sector": effects[2].get(k[2], 0.0) * 1e4},
                     "peer_count": len(rows)}))
        return flags
