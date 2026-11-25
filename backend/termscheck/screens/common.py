"""Helpers shared by screens: vendor-implied yield, rating and maturity buckets."""
from __future__ import annotations

from datetime import date

from ..bondmath import VendorView, implied_yield
from ..bondmath.treatment import vendor_accrued, vendor_terms_as_bond
from .models import SecurityRecord


def vendor_view(rec: SecurityRecord) -> VendorView:
    return VendorView(rec.price, rec.price_convention, rec.coupon, rec.accrual_type)


def vendor_full_value(rec: SecurityRecord, as_of: date, price: float | None = None) -> float:
    p = rec.price if price is None else price
    if rec.price_convention.lower() == "clean":
        return p + vendor_accrued(vendor_view(rec), rec.maturity_date, rec.issue_date, as_of)
    return p


def vendor_implied_yield(rec: SecurityRecord, as_of: date, price: float | None = None) -> float | None:
    """Yield implied by the price if the vendor's stated terms were true."""
    if as_of >= rec.maturity_date or rec.issue_date >= rec.maturity_date:
        return None
    terms = vendor_terms_as_bond(vendor_view(rec), rec.issue_date, rec.maturity_date)
    return implied_yield(terms, vendor_full_value(rec, as_of, price), as_of)


def years_between(d1: date, d2: date) -> float:
    return (d2 - d1).days / 365.25


_SP = {"AAA": "AAA", "AA+": "AA", "AA": "AA", "AA-": "AA", "A+": "A", "A": "A", "A-": "A",
       "BBB+": "BBB", "BBB": "BBB", "BBB-": "BBB"}
_MOODY = {"AAA": "AAA", "AA1": "AA", "AA2": "AA", "AA3": "AA", "A1": "A", "A2": "A", "A3": "A",
          "BAA1": "BBB", "BAA2": "BBB", "BAA3": "BBB"}


def rating_bucket(rating: str) -> str:
    r = (rating or "").strip().upper()
    if r in ("", "NR", "N/R", "WR", "NOT RATED"):
        return "NR"
    if r in _SP:
        return _SP[r]
    if r in _MOODY:
        return _MOODY[r]
    return "HY"


def maturity_band(years: float) -> str:
    if years < 5:
        return "0-5y"
    if years < 10:
        return "5-10y"
    if years < 20:
        return "10-20y"
    return "20y+"
