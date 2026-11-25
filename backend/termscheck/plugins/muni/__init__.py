"""Municipal bonds: current pay, CABs, deferred interest, convertible CABs."""
from __future__ import annotations

from datetime import date
from typing import Any

from termscheck.core.plugin import register
from termscheck.core.records import CashPeriod
from termscheck.core.schedules import add_months
from termscheck.plugins.muni.bondmath import DayCount, InterestTerms, InterestType
from termscheck.plugins.muni.extraction.spec import MUNI_SPEC
from termscheck.plugins.muni.findings import build_finding
from termscheck.plugins.muni.screens.peer_outlier import PeerOutlierScreen
from termscheck.plugins.muni.screens.price_drift import PriceDriftScreen
from termscheck.plugins.muni.screens.yield_coupon import YieldCouponScreen
from termscheck.plugins.muni.screens.zero_coupon import ZeroCouponScreen


class MuniPlugin:
    key = "muni"
    label = "Municipal bonds"
    from termscheck.plugins.muni.bondmath import BONDMATH_VERSION as math_version
    screens = (YieldCouponScreen(), PriceDriftScreen(), PeerOutlierScreen(), ZeroCouponScreen())
    extraction = MUNI_SPEC

    def cash_period(self, rec, pos, entry, data) -> CashPeriod:
        """A muni coupon receipt pays the coupon period ending on (or just before) the receipt."""
        assumptions = []
        freq = rec.payment_frequency
        if not freq:
            assumptions.append("payment frequency not usable from book terms; semiannual assumed")
            freq = 2
        step = 12 // freq
        anchor = rec.maturity_date
        k = 0
        while add_months(anchor, -step * k) > entry.entry_date:
            k += 1
        end = add_months(anchor, -step * k)
        if (entry.entry_date - end).days > 20:
            assumptions.append("receipt not on a scheduled coupon date; nearest prior coupon date used")
        return CashPeriod(add_months(end, -step), end, pos.par, 1.0 / freq, tuple(assumptions))

    def prepare_context(self, data, ctx) -> None:
        """Vendor-terms implied yields, shared by the yield, drift and peer screens."""
        from termscheck.plugins.muni.screens.common import vendor_implied_yield
        ctx.implied_yields.update({c: vendor_implied_yield(r, data.as_of) for c, r in data.primary.items()})

    def terms_to_json(self, terms: InterestTerms) -> dict[str, Any]:
        from termscheck.services.serialize import jsonable
        return jsonable(terms)

    def terms_from_json(self, d: dict[str, Any]) -> InterestTerms:
        def dt(k):
            return date.fromisoformat(d[k]) if d.get(k) else None
        return InterestTerms(
            interest_type=InterestType(d["interest_type"]), rate=d["rate"], dated_date=dt("dated_date"),
            maturity_date=dt("maturity_date"), day_count=DayCount(d["day_count"]),
            payment_frequency=d["payment_frequency"], compounding_frequency=d["compounding_frequency"],
            first_coupon_date=dt("first_coupon_date"), first_compounding_date=dt("first_compounding_date"),
            conversion_date=dt("conversion_date"))

    def build_finding(self, record, positions, terms, as_of, *, citations=None, rules=None, ledger=None,
                      context=None):
        return build_finding(record, positions, terms, as_of, citations=citations, rules=rules)


PLUGIN = register(MuniPlugin())
