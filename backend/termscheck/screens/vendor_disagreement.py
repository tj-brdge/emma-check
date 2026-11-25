"""Vendor disagreement: coupon, accrual type, payment schedule, price convention, day count
or price mismatch between the primary and secondary vendor."""
from __future__ import annotations

from .base import ScreenContext, clamp_severity
from .config import ScreenConfig
from .models import Flag, ScreenInput

WEIGHTS = {"coupon": 40, "accrual_type": 40, "price_convention": 30, "payment_frequency": 20,
           "day_count": 15, "maturity_date": 30, "price": 15}


def _norm(s: str | None) -> str | None:
    return None if s is None else s.strip().lower()


class VendorDisagreementScreen:
    rule = "vendor_disagreement"

    def run(self, data: ScreenInput, config: ScreenConfig, ctx: ScreenContext) -> list[Flag]:
        flags: list[Flag] = []
        for cusip, a in data.primary.items():
            b = data.secondary.get(cusip)
            if b is None:
                continue
            diffs: dict[str, dict] = {}
            if abs(a.coupon - b.coupon) > 1e-6:
                diffs["coupon"] = {a.vendor: a.coupon, b.vendor: b.coupon}
            if _norm(a.accrual_type) != _norm(b.accrual_type):
                diffs["accrual_type"] = {a.vendor: a.accrual_type, b.vendor: b.accrual_type}
            if _norm(a.price_convention) != _norm(b.price_convention):
                diffs["price_convention"] = {a.vendor: a.price_convention, b.vendor: b.price_convention}
            if a.payment_frequency and b.payment_frequency and a.payment_frequency != b.payment_frequency:
                diffs["payment_frequency"] = {a.vendor: a.payment_frequency, b.vendor: b.payment_frequency}
            if a.day_count and b.day_count and _norm(a.day_count) != _norm(b.day_count):
                diffs["day_count"] = {a.vendor: a.day_count, b.vendor: b.day_count}
            if a.maturity_date != b.maturity_date:
                diffs["maturity_date"] = {a.vendor: a.maturity_date.isoformat(),
                                          b.vendor: b.maturity_date.isoformat()}
            if abs(a.price - b.price) > config.vendor_price_tolerance:
                diffs["price"] = {a.vendor: a.price, b.vendor: b.price}
            if diffs:
                sev = clamp_severity(20 + sum(WEIGHTS[k] for k in diffs))
                flags.append(Flag(
                    self.rule, cusip, sev,
                    "Vendors disagree on " + ", ".join(diffs) + ".",
                    {"vendors": [a.vendor, b.vendor]},
                    {"differences": diffs}))
        return flags
