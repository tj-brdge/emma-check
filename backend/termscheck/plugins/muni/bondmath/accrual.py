"""Accrued interest, economic income and cash flows. Pure functions."""
from __future__ import annotations

from datetime import date

from termscheck.plugins.muni.bondmath.accretion import accreted_value
from termscheck.core.daycount import year_fraction
from termscheck.core.schedules import bracket, regular_schedule
from termscheck.plugins.muni.bondmath.models import CashFlow, InterestTerms, InterestType


def coupon_start(terms: InterestTerms) -> date | None:
    """Date current interest starts accruing, or None if the bond never pays current interest."""
    if terms.interest_type is InterestType.CURRENT_PAY:
        return terms.dated_date
    if terms.interest_type is InterestType.CONVERTIBLE_CAB:
        return terms.conversion_date
    return None


def coupon_schedule(terms: InterestTerms) -> list[date]:
    start = coupon_start(terms)
    if start is None:
        return []
    first = terms.first_coupon_date
    if first is not None and first <= start:
        first = None
    return regular_schedule(start, terms.maturity_date, terms.payment_frequency, first)


def _coupon_accrual(terms: InterestTerms, start: date, d: date) -> float:
    sched = coupon_schedule(terms)
    prev, nxt = bracket(sched, start, d)
    if nxt is None:
        return 0.0
    yf = year_fraction(
        terms.day_count, prev, d, period_start=prev, period_end=nxt, frequency=terms.payment_frequency
    )
    return 100.0 * terms.rate * yf


def accrued_interest(terms: InterestTerms, d: date) -> float:
    """Accrued-but-unpaid interest per 100 par on date d (the amount embedded in a dirty price).

    CURRENT_PAY        coupon accrued since the last coupon date.
    DEFERRED_INTEREST  all interest accrued since the dated date (accreted value - 100).
    CAPITAL_APPRECIATION 0: the whole accreted value is principal; income is recognised as
                       accretion, not as accrued interest.
    CONVERTIBLE_CAB    0 before conversion; coupon accrual after.
    """
    t = terms.interest_type
    if d <= terms.dated_date or d >= terms.maturity_date:
        return 0.0
    if t is InterestType.CURRENT_PAY:
        return _coupon_accrual(terms, terms.dated_date, d)
    if t is InterestType.DEFERRED_INTEREST:
        return accreted_value(terms, d) - 100.0
    if t is InterestType.CAPITAL_APPRECIATION:
        return 0.0
    assert terms.conversion_date is not None
    if d <= terms.conversion_date:
        return 0.0
    return _coupon_accrual(terms, terms.conversion_date, d)


def economic_income(terms: InterestTerms, d1: date, d2: date) -> float:
    """Interest income earned per 100 par between d1 and d2 under the document terms
    (coupon accrual for current interest, accretion for accreting interest)."""
    if d2 <= d1:
        return 0.0
    d1 = max(d1, terms.dated_date)
    d2 = min(d2, terms.maturity_date)
    if d2 <= d1:
        return 0.0
    t = terms.interest_type
    if t is InterestType.CURRENT_PAY:
        return 100.0 * terms.rate * year_fraction(terms.day_count, d1, d2)
    if t in (InterestType.DEFERRED_INTEREST, InterestType.CAPITAL_APPRECIATION):
        return accreted_value(terms, d2) - accreted_value(terms, d1)
    assert terms.conversion_date is not None
    conv = terms.conversion_date
    inc = accreted_value(terms, min(d2, conv)) - accreted_value(terms, min(d1, conv))
    if d2 > conv:
        inc += 100.0 * terms.rate * year_fraction(terms.day_count, max(d1, conv), d2)
    return inc


def cash_flows(terms: InterestTerms, after: date) -> list[CashFlow]:
    """Remaining cash flows per 100 par strictly after ``after``."""
    t = terms.interest_type
    flows: list[CashFlow] = []
    start = coupon_start(terms)
    if start is not None:
        sched = coupon_schedule(terms)
        prev = start
        for cd in sched:
            amt = 100.0 * terms.rate * year_fraction(
                terms.day_count, prev, cd, period_start=prev, period_end=cd,
                frequency=terms.payment_frequency,
            )
            if cd > after:
                flows.append(CashFlow(cd, amt))
            prev = cd
    if terms.maturity_date > after:
        if t is InterestType.DEFERRED_INTEREST:
            principal = accreted_value(terms, terms.maturity_date)
        else:
            principal = 100.0
        flows.append(CashFlow(terms.maturity_date, principal))
    # merge same-date flows
    merged: dict[date, float] = {}
    for f in flows:
        merged[f.date] = merged.get(f.date, 0.0) + f.amount
    return [CashFlow(d, a) for d, a in sorted(merged.items())]
