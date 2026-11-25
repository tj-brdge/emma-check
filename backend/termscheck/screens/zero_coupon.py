"""Zero-coupon sanity: a zero-coupon bond priced near or above par with meaningful time to
maturity implies a ~0% or negative yield, which a real zero would not carry."""
from __future__ import annotations

from .base import ScreenContext, clamp_severity
from .common import years_between
from .config import ScreenConfig
from .models import Flag, ScreenInput


class ZeroCouponScreen:
    rule = "zero_coupon_sanity"

    def run(self, data: ScreenInput, config: ScreenConfig, ctx: ScreenContext) -> list[Flag]:
        flags: list[Flag] = []
        for cusip, rec in data.primary.items():
            if rec.coupon > 0:
                continue
            years = years_between(data.as_of, rec.maturity_date)
            if years < config.zero_min_years or rec.price < config.zero_near_par_price:
                continue
            y = ctx.implied_yields.get(cusip)
            flags.append(Flag(
                self.rule, cusip,
                clamp_severity(45 + min(30.0, (rec.price - config.zero_near_par_price) * 0.5) + min(20.0, years * 2)),
                f"Zero coupon priced {rec.price:.3f} with {years:.1f} years to maturity "
                f"(implied yield {'n/a' if y is None else f'{y:.2%}'}).",
                {"price": rec.price, "coupon": rec.coupon, "maturity_date": rec.maturity_date.isoformat(),
                 "accrual_type": rec.accrual_type},
                {"years_to_maturity": years, "implied_yield": y,
                 "near_par_threshold": config.zero_near_par_price}))
        return flags
