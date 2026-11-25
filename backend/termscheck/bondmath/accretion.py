"""Accreted value for CABs, convertible CABs and deferred-interest bonds. Pure functions.

Convention (MSRB Rule G-33 style): value is compounded at each compounding date and
interpolated *linearly* between compounding dates on the bond's day-count basis.
A short first period (dated date to first compounding date) compounds by a fractional
exponent equal to the fraction of a regular period it covers.
"""
from __future__ import annotations

from datetime import date

from .daycount import add_months, period_fraction, year_fraction
from .schedules import regular_schedule
from .models import AccretionPoint, InterestTerms, InterestType

ACCRETING_TYPES = (
    InterestType.CAPITAL_APPRECIATION,
    InterestType.DEFERRED_INTEREST,
    InterestType.CONVERTIBLE_CAB,
)


def accretion_end(terms: InterestTerms) -> date:
    if terms.interest_type is InterestType.CONVERTIBLE_CAB:
        assert terms.conversion_date is not None
        return terms.conversion_date
    return terms.maturity_date


def _anchored_at_end(terms: InterestTerms) -> bool:
    """CAB/CCAB values are anchored so that V(end) = 100; deferred interest V(dated) = 100."""
    return terms.interest_type in (InterestType.CAPITAL_APPRECIATION, InterestType.CONVERTIBLE_CAB)


def _compounding_points(terms: InterestTerms) -> list[tuple[date, float]]:
    """(date, cumulative periods since dated date) for the dated date and each compounding date."""
    m = terms.compounding_frequency
    end = accretion_end(terms)
    dates = regular_schedule(terms.dated_date, end, m, terms.first_compounding_date)
    first = dates[0]
    nominal_start = add_months(first, -(12 // m))
    if nominal_start < terms.dated_date:
        stub = 1.0 - period_fraction(terms.day_count, nominal_start, first, terms.dated_date, m)
    else:
        # Long first period: count whole periods plus the fraction before nominal_start.
        stub = 1.0
        prev = nominal_start
        while prev > terms.dated_date:
            p2 = add_months(prev, -(12 // m))
            if p2 <= terms.dated_date:
                stub += 1.0 - period_fraction(terms.day_count, p2, prev, terms.dated_date, m)
                break
            stub += 1.0
            prev = p2
    pts = [(terms.dated_date, 0.0)]
    for i, d in enumerate(dates):
        pts.append((d, stub + i))
    return pts


def _value_at_periods(terms: InterestTerms, p: float, n_total: float) -> float:
    g = 1.0 + terms.rate / terms.compounding_frequency
    if _anchored_at_end(terms):
        return 100.0 * g ** (p - n_total)
    return 100.0 * g ** p


def _simple_value(terms: InterestTerms, d: date) -> float:
    yf = year_fraction(terms.day_count, terms.dated_date, d)
    if _anchored_at_end(terms):
        yf_end = year_fraction(terms.day_count, terms.dated_date, accretion_end(terms))
        return 100.0 * (1.0 + terms.rate * yf) / (1.0 + terms.rate * yf_end)
    return 100.0 * (1.0 + terms.rate * yf)


def accretion_schedule(terms: InterestTerms) -> list[AccretionPoint]:
    """Accreted value per 100 par at the dated date and every compounding date."""
    if terms.interest_type not in ACCRETING_TYPES:
        raise ValueError("accretion schedule applies only to accreting interest types")
    if terms.compounding_frequency == 0:
        # Simple interest: report semiannual checkpoints for readability.
        dates = [terms.dated_date] + regular_schedule(terms.dated_date, accretion_end(terms), 2)
        return [AccretionPoint(d, _simple_value(terms, d)) for d in dates]
    pts = _compounding_points(terms)
    n_total = pts[-1][1]
    return [AccretionPoint(d, _value_at_periods(terms, p, n_total)) for d, p in pts]


def accreted_value(terms: InterestTerms, d: date) -> float:
    """Accreted value per 100 par on date d (linear interpolation between compounding dates)."""
    if terms.interest_type not in ACCRETING_TYPES:
        raise ValueError("accreted value applies only to accreting interest types")
    end = accretion_end(terms)
    if d <= terms.dated_date:
        d = terms.dated_date
    if d >= end:
        d = end
    if terms.compounding_frequency == 0:
        return _simple_value(terms, d)
    pts = _compounding_points(terms)
    n_total = pts[-1][1]
    for (d0, p0), (d1, p1) in zip(pts, pts[1:]):
        if d0 <= d <= d1:
            v0 = _value_at_periods(terms, p0, n_total)
            v1 = _value_at_periods(terms, p1, n_total)
            f = period_fraction(terms.day_count, d0, d1, d, terms.compounding_frequency)
            return v0 + (v1 - v0) * f
    return _value_at_periods(terms, n_total, n_total)
