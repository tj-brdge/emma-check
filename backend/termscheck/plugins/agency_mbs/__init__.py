"""Agency MBS: pass-throughs and ARMs (Freddie Mac / Fannie Mae / Ginnie Mae style pools).

PO/IO strips are recognised by product type only so they are not mis-flagged; their math is
out of scope for v1.
"""
from __future__ import annotations

from termscheck.core.records import CashPeriod
from termscheck.core.plugin import register
from termscheck.plugins.agency_mbs.bondmath import accrual_month_paid_on
from termscheck.plugins.agency_mbs.disclosure import parse_pool_disclosure
from termscheck.plugins.agency_mbs.extraction.spec import MBS_SPEC, terms_from_json
from termscheck.plugins.agency_mbs.findings import build_mbs_finding
from termscheck.plugins.agency_mbs.screens import FactorMismatchScreen, RateVsDisclosureScreen

# Common stated delays by the day of month the payment lands on (used only when the delay is
# not supplied by any source, and always reported as an assumption).
DELAY_BY_PAY_DAY = {15: 45, 25: 55, 20: 50}


def infer_delay(rec, pay_day: int) -> tuple[int, str | None]:
    if rec.payment_delay_days is not None:
        return rec.payment_delay_days, None
    for day, delay in DELAY_BY_PAY_DAY.items():
        if abs(pay_day - day) <= 3:          # allow weekend / holiday shifts
            return delay, f"payment delay not supplied; {delay} days inferred from payment on day {pay_day}"
    return 45, f"payment delay not supplied and day {pay_day} is not a standard pay day; 45 days assumed"


class AgencyMBSPlugin:
    key = "agency_mbs"
    label = "Agency MBS"
    primary_document_kind = "oc_supplement"
    term_fields = frozenset({"price_convention", "coupon", "accrual_type", "issue_date", "payment_frequency",
                             "day_count", "product_type", "factor", "factor_date", "payment_delay_days", "rate_type"})
    from termscheck.plugins.agency_mbs.treatment import TREATMENT_VERSION as math_version
    screens = (FactorMismatchScreen(), RateVsDisclosureScreen())
    extraction = MBS_SPEC
    data_document_kinds = ("pool_disclosure",)

    def terms_to_json(self, terms: dict) -> dict:
        return dict(terms)

    def terms_from_json(self, data: dict) -> dict:
        terms_from_json(data)        # validate
        return dict(data)

    SUPPORTED_PRODUCTS = {"pass_through", "arm"}

    def unsupported_reason(self, record, terms) -> str | None:
        for source, product in (("book of record", record.product_type),
                                ("offering document", (terms or {}).get("product_type"))):
            if product and product not in self.SUPPORTED_PRODUCTS:
                what = {"cmo": "CMO tranches", "io": "interest-only strips", "po": "principal-only strips",
                        "bond": "non-pool agency bonds"}.get(product, f"product type {product!r}")
                return (f"{what} are not implemented ({source} says {product}); only pass-through and ARM "
                        "pools are computed - review this security manually")
        return None

    def build_finding(self, record, positions, terms, as_of, *, citations=None, rules=None, ledger=None,
                      context=None):
        ctx = context or {}
        return build_mbs_finding(record, positions, terms, as_of, citations=citations, rules=rules, ledger=ledger,
                                 observations=ctx.get("observations"), sources=ctx.get("sources"))

    def parse_data_document(self, kind: str, filename: str, text: str):
        if kind != "pool_disclosure":
            raise ValueError(f"unsupported data document kind {kind!r}")
        return parse_pool_disclosure(filename, text)

    def cash_period(self, rec, pos, entry, data) -> CashPeriod:
        """An MBS interest receipt pays one accrual month: payment date minus the stated delay.
        Face = original face (position par) x that month's factor."""
        assumptions = []
        delay, why = infer_delay(rec, entry.entry_date.day)
        if why:
            assumptions.append(why)
        month = accrual_month_paid_on(entry.entry_date, delay)
        ob = next((o for o in data.observations.get(rec.cusip, []) if o.month == month), None)
        factor = ob.factor if ob is not None else None
        if factor is None:
            factor = rec.factor
            assumptions.append(f"no disclosed factor for {month:%Y-%m}; book factor used"
                               if factor is not None else f"no factor for {month:%Y-%m}; original face used")
        face = pos.par * (factor if factor is not None else 1.0)
        nxt = month.replace(year=month.year + month.month // 12, month=month.month % 12 + 1)
        book_face = pos.par * rec.factor if rec.factor is not None else None
        return CashPeriod(month, nxt, face, 1.0 / 12.0, tuple(assumptions), book_face,
                          ob.net_coupon if ob is not None else None)


PLUGIN = register(AgencyMBSPlugin())
