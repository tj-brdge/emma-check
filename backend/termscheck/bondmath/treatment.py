"""Correct accounting treatment from document terms vs. vendor terms. Pure functions.

Core identity: the market value of a position does not depend on labels.
    full (dirty) value = vendor price + vendor-computed accrued   if vendor says "clean"
                       = vendor price                            if vendor says "dirty"
The *split* of that full value between principal (clean) and accrued interest is what
the vendor can get wrong. The correct split uses accrued interest from the document terms:
    correct clean = full value - true accrued
Headline unbooked income (per position) = (true accrued - vendor accrued) x par / 100,
i.e. income sitting in the price that fund accounting carries as principal / unrealized
appreciation instead of accrued income. Positive = income understated.
"""
from __future__ import annotations

from datetime import date

from .accretion import ACCRETING_TYPES, accretion_schedule, accreted_value
from .accrual import accrued_interest, cash_flows, economic_income
from .daycount import days_30_360, year_fraction
from .schedules import bracket, regular_schedule
from .models import AccretionPoint, DayCount, InterestTerms, InterestType, Treatment, VendorView
from .yields import yield_from_dirty_price

# Vendor accrual-type labels meaning "the accounting system recognises accretion".
ACCRETING_VENDOR_LABELS = frozenset(
    {"accreting", "cab", "capital appreciation", "capital_appreciation", "deferred",
     "deferred_interest", "deferred interest", "compound", "compounding"}
)

BONDMATH_VERSION = "1.0.0"


def vendor_accrued(vendor: VendorView, maturity: date, dated: date, as_of: date) -> float:
    """Accrued interest fund accounting would book from vendor terms: vendor coupon on a
    semiannual 30/360 schedule generated backward from maturity."""
    if vendor.coupon <= 0 or as_of <= dated or as_of >= maturity:
        return 0.0
    sched = regular_schedule(dated, maturity, 2)
    prev, nxt = bracket(sched, dated, as_of)
    if nxt is None:
        return 0.0
    return 100.0 * vendor.coupon * days_30_360(prev, as_of) / 360.0


def vendor_terms_as_bond(vendor: VendorView, dated: date, maturity: date) -> InterestTerms:
    """Interpret vendor fields as a bond: coupon > 0 -> current pay; coupon == 0 -> zero/CAB."""
    if vendor.coupon > 0:
        return InterestTerms(InterestType.CURRENT_PAY, vendor.coupon, dated, maturity)
    return InterestTerms(InterestType.CAPITAL_APPRECIATION, 0.0, dated, maturity)


def implied_yield(terms: InterestTerms, full_value: float, as_of: date) -> float | None:
    freq = terms.payment_frequency if terms.interest_type is InterestType.CURRENT_PAY else 2
    return yield_from_dirty_price(
        cash_flows(terms, as_of), as_of, full_value,
        anchor=terms.maturity_date, frequency=freq, day_count=terms.day_count,
    )


def compute_treatment(
    terms: InterestTerms,
    vendor: VendorView,
    par: float,
    as_of: date,
    *,
    window_start: date | None = None,
) -> Treatment:
    notes: list[str] = []
    label = vendor.accrual_type.strip().lower()
    vendor_recognises_accretion = label in ACCRETING_VENDOR_LABELS

    v_acc = vendor_accrued(vendor, terms.maturity_date, terms.dated_date, as_of)
    conv = vendor.price_convention.strip().lower()
    if conv not in ("clean", "dirty"):
        raise ValueError(f"unknown price convention {vendor.price_convention!r}")
    full = vendor.price + v_acc if conv == "clean" else vendor.price

    t_acc = accrued_interest(terms, as_of)
    if vendor_recognises_accretion and terms.interest_type in ACCRETING_TYPES:
        # Vendor label says accounting accretes; assume the booked accrual matches.
        v_acc_effective = t_acc
        notes.append("Vendor accrual type indicates accretion is recognised; booked accrual "
                     "assumed equal to document accrual.")
    else:
        v_acc_effective = v_acc

    av = accreted_value(terms, as_of) if terms.interest_type in ACCRETING_TYPES else None
    if terms.interest_type is InterestType.CAPITAL_APPRECIATION:
        notes.append("CAB: no accrued interest; income is recognised through accretion of the "
                     "accreted value (original-issue schedule).")

    schedule: list[AccretionPoint] = []
    if terms.interest_type in ACCRETING_TYPES:
        schedule = accretion_schedule(terms)
        if av is not None and all(p.date != as_of for p in schedule):
            schedule = sorted(schedule + [AccretionPoint(as_of, av)], key=lambda p: p.date)

    unbooked = t_acc - v_acc_effective
    y_doc = implied_yield(terms, full, as_of)
    y_vendor = implied_yield(vendor_terms_as_bond(vendor, terms.dated_date, terms.maturity_date),
                             full, as_of)

    window_usd = None
    ws = None
    if window_start is not None:
        ws = max(window_start, terms.dated_date)
        true_inc = economic_income(terms, ws, as_of)
        if vendor_recognises_accretion and terms.interest_type in ACCRETING_TYPES:
            vend_inc = true_inc
        else:
            vend_inc = 100.0 * vendor.coupon * year_fraction(DayCount.THIRTY_360, ws, min(as_of, terms.maturity_date))
        window_usd = (true_inc - vend_inc) * par / 100.0

    return Treatment(
        as_of=as_of,
        interest_type=terms.interest_type,
        accreted_value=av,
        true_accrued=t_acc,
        vendor_accrued=v_acc_effective,
        full_value=full,
        correct_clean=full - t_acc,
        correct_dirty=full,
        vendor_clean=full - v_acc,
        yield_document_terms=y_doc,
        yield_vendor_terms=y_vendor,
        accretion_since_dated=economic_income(terms, terms.dated_date, as_of),
        unbooked_per_100=unbooked,
        unbooked_income_usd=unbooked * par / 100.0,
        window_start=ws,
        unbooked_window_usd=window_usd,
        schedule=schedule,
        notes=notes,
    )
