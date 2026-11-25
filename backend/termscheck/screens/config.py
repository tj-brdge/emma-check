"""Screen thresholds. Serialised into every screen run for reproducibility."""
from __future__ import annotations

from dataclasses import asdict, dataclass

SCREEN_CONFIG_VERSION = "1.0.0"


@dataclass(frozen=True)
class ScreenConfig:
    # yield / coupon impossibility
    max_yield_gap_bp: float = 150.0          # |vendor yield - implied yield| that triggers
    min_plausible_yield: float = -0.005      # implied yields below this are impossible for munis
    # price drift
    drift_min_points: int = 6
    drift_min_span_days: int = 90
    drift_min_r2: float = 0.90
    drift_min_excess_pct: float = 0.025      # unexplained annual drift / price, after market adj.
    drift_market_adjust: bool = True         # subtract band-median implied-yield moves
    drift_min_yield_slope_bp: float = 30.0   # min fall in adjusted implied yield, bp/yr
    # peer outlier
    peer_z_threshold: float = 3.0
    peer_min_level: int = 3                  # min observations for a factor level to get its own effect
    peer_mad_floor_bp: float = 15.0          # floor on MAD so tight buckets don't explode z
    # vendor disagreement
    vendor_price_tolerance: float = 2.0      # points
    # zero-coupon sanity
    zero_near_par_price: float = 95.0
    zero_min_years: float = 3.0

    # null vs zero / frequency contradiction
    blank_alone_severity: int = 30           # blank in one source with no zero anywhere
    blank_alone_fields: tuple[str, ...] = ("coupon", "factor")   # benign blanks elsewhere are not reported
    # cash reconciliation
    cash_shortfall_pct: float = 0.10         # booked income below cash by more than this share
    cash_rate_gap_bp: float = 25.0           # ...and the implied rate differs by more than this
    cash_overbooked_pct: float = 0.10        # booked income above cash (over-accrual)
    cash_lookback_days: int = 400

    def as_dict(self) -> dict:
        return {"version": SCREEN_CONFIG_VERSION, **asdict(self)}
