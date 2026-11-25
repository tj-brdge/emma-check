"""Run every screen over a holdings set. Deterministic; no I/O."""
from __future__ import annotations

from .base import Screen, ScreenContext
from .common import vendor_implied_yield
from .config import ScreenConfig
from .models import ScreenInput, ScreenResult
from .peer_outlier import PeerOutlierScreen
from .price_drift import PriceDriftScreen
from .vendor_disagreement import VendorDisagreementScreen
from .yield_coupon import YieldCouponScreen
from .zero_coupon import ZeroCouponScreen

ALL_SCREENS: tuple[Screen, ...] = (
    YieldCouponScreen(), PriceDriftScreen(), PeerOutlierScreen(),
    VendorDisagreementScreen(), ZeroCouponScreen(),
)


def run_screens(data: ScreenInput, config: ScreenConfig | None = None,
                screens: tuple[Screen, ...] = ALL_SCREENS) -> ScreenResult:
    config = config or ScreenConfig()
    held = {p.cusip for p in data.positions} or set(data.primary)
    data = ScreenInput(
        as_of=data.as_of, positions=data.positions,
        primary={c: r for c, r in data.primary.items() if c in held},
        secondary=data.secondary, history=data.history,
    )
    ctx = ScreenContext(implied_yields={c: vendor_implied_yield(r, data.as_of) for c, r in data.primary.items()})
    flags = [f for s in screens for f in s.run(data, config, ctx)]
    flags.sort(key=lambda f: (-f.severity, f.cusip, f.rule))
    return ScreenResult(flags=flags, implied_yields=ctx.implied_yields, config=config.as_dict())
