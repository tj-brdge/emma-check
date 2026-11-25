"""Vendor disagreement: any term that differs across sources (book of record and every vendor).

Blank-versus-value is reported as a disagreement too (labelled BLANK, never shown as 0); the
specific blank-in-one-source / zero-in-another pattern additionally raises the null-vs-zero flag.
"""
from __future__ import annotations

from datetime import date
from itertools import combinations

from termscheck.core.records import ABSENT, BLANK, Flag, ScreenInput, SecurityRecord
from termscheck.screens.base import ScreenContext, clamp_severity
from termscheck.screens.config import ScreenConfig

WEIGHTS = {"coupon": 40, "accrual_type": 40, "price_convention": 30, "payment_frequency": 20,
           "day_count": 15, "maturity_date": 30, "price": 15, "factor": 25, "payment_delay_days": 20,
           "rate_type": 25, "product_type": 25}
COMPARED = [k for k in WEIGHTS if k != "price"]


def label(rec: SecurityRecord, name: str):
    v = getattr(rec, name)
    if v is None:
        return "BLANK" if rec.state_of(name) == BLANK else None
    if isinstance(v, date):
        return v.isoformat()
    return v.strip().lower() if isinstance(v, str) else v


def differs(a, b) -> bool:
    if a is None or b is None:            # absent in a source: nothing to compare
        return False
    if isinstance(a, float) or isinstance(b, float):
        if isinstance(a, str) or isinstance(b, str):
            return True
        return abs(float(a) - float(b)) > 1e-9
    return a != b


class VendorDisagreementScreen:
    confidence = 0.8
    rule = "vendor_disagreement"

    def run(self, data: ScreenInput, config: ScreenConfig, ctx: ScreenContext) -> list[Flag]:
        flags: list[Flag] = []
        for cusip in data.primary:
            recs = data.sources_for(cusip)
            if len(recs) < 2:
                continue
            diffs: dict[str, dict] = {}
            for name in COMPARED:
                vals = {r.vendor: label(r, name) for r in recs}
                if any(differs(vals[a.vendor], vals[b.vendor]) for a, b in combinations(recs, 2)):
                    diffs[name] = vals
            prices = [r.price for r in recs]
            if max(prices) - min(prices) > config.vendor_price_tolerance:
                diffs["price"] = {r.vendor: r.price for r in recs}
            if diffs:
                sev = clamp_severity(15 + 0.8 * sum(WEIGHTS[k] for k in diffs))
                flags.append(Flag(
                    self.rule, cusip, sev,
                    "Sources disagree on " + ", ".join(
                        f"{k} ({'; '.join(f'{s}={_fmt(v)}' for s, v in d.items())})" for k, d in diffs.items()) + ".",
                    {"sources": [r.vendor for r in recs]},
                    {"differences": diffs}))
        return flags


def _fmt(v) -> str:
    if v is None:
        return "not supplied"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


__all__ = ["VendorDisagreementScreen", "ABSENT"]
