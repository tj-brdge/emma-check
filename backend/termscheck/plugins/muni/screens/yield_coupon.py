"""Yield/coupon impossibility: the stated coupon cannot produce the reported yield at the price."""
from __future__ import annotations

from termscheck.screens.base import ScreenContext, clamp_severity
from termscheck.screens.config import ScreenConfig
from termscheck.core.records import Flag, ScreenInput


class YieldCouponScreen:
    rule = "yield_coupon_impossibility"

    def run(self, data: ScreenInput, config: ScreenConfig, ctx: ScreenContext) -> list[Flag]:
        flags: list[Flag] = []
        for cusip, rec in data.primary.items():
            y = ctx.implied_yields.get(cusip)
            inputs = {"price": rec.price, "price_convention": rec.price_convention,
                      "coupon": rec.coupon, "vendor_yield": rec.vendor_yield,
                      "maturity_date": rec.maturity_date.isoformat(),
                      "issue_date": rec.issue_date.isoformat()}
            if y is None or y < config.min_plausible_yield:
                why = ("no yield reproduces the price" if y is None
                       else f"implied yield {y:.2%} is below plausible floor")
                gap = None if (y is None or rec.vendor_yield is None) else (rec.vendor_yield - y) * 1e4
                flags.append(Flag(
                    self.rule, cusip,
                    clamp_severity(70 + (abs(gap) / 50 if gap is not None else 20)),
                    f"Coupon {rec.coupon:.3%} at price {rec.price:.3f} ({rec.price_convention}): {why}.",
                    inputs, {"implied_yield": y, "gap_bp": gap,
                             "min_plausible_yield": config.min_plausible_yield}))
                continue
            if rec.vendor_yield is not None:
                gap = (rec.vendor_yield - y) * 1e4
                if abs(gap) > config.max_yield_gap_bp:
                    low = rec.coupon <= 0.02
                    flags.append(Flag(
                        self.rule, cusip,
                        clamp_severity(40 + abs(gap) / 15 + (15 if low else 0)),
                        f"Reported yield {rec.vendor_yield:.2%} but coupon {rec.coupon:.3%} at "
                        f"price {rec.price:.3f} implies {y:.2%} ({gap:+.0f} bp).",
                        inputs, {"implied_yield": y, "gap_bp": gap,
                                 "threshold_bp": config.max_yield_gap_bp}))
        return flags
