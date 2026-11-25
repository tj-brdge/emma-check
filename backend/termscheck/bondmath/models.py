"""Typed inputs/outputs for the bond-math module.

All prices and values are expressed per 100 of par. Rates are decimals (0.05 = 5%).
"Par" semantics differ by interest type and are documented on ``InterestType``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class DayCount(StrEnum):
    THIRTY_360 = "30/360"   # MSRB Rule G-33 / SIA bond basis (muni default)
    ACT_360 = "ACT/360"
    ACT_365 = "ACT/365"
    ACT_ACT = "ACT/ACT"     # ICMA: actual days / (freq * actual days in period)


class InterestType(StrEnum):
    """How the bond earns and pays interest.

    CURRENT_PAY         periodic coupons on par; par repaid at maturity.
    CAPITAL_APPRECIATION (CAB) no coupons; par is the *maturity* value. Accreted value
                        grows from an initial amount to 100 at maturity.
    DEFERRED_INTEREST   par is the *principal*. Interest accrues (simple or compounded)
                        from the accrual start date and is paid in full at maturity.
    CONVERTIBLE_CAB     accretes like a CAB until the conversion date, where the accreted
                        value reaches 100 (par); then pays current interest on par.
    """

    CURRENT_PAY = "current_pay"
    CAPITAL_APPRECIATION = "capital_appreciation"
    DEFERRED_INTEREST = "deferred_interest"
    CONVERTIBLE_CAB = "convertible_cab"


@dataclass(frozen=True)
class InterestTerms:
    interest_type: InterestType
    rate: float                         # coupon or accretion rate, annual decimal
    dated_date: date                    # accrual start date
    maturity_date: date
    day_count: DayCount = DayCount.THIRTY_360
    payment_frequency: int = 2          # coupons/yr (current pay, or CCAB post-conversion)
    compounding_frequency: int = 2      # accretion compounding/yr; 0 = simple interest
    first_coupon_date: date | None = None       # optional explicit first coupon date
    first_compounding_date: date | None = None  # optional explicit first compounding date
    conversion_date: date | None = None         # CONVERTIBLE_CAB only

    def __post_init__(self) -> None:
        if self.maturity_date <= self.dated_date:
            raise ValueError("maturity_date must be after dated_date")
        if self.interest_type is InterestType.CONVERTIBLE_CAB:
            if self.conversion_date is None:
                raise ValueError("CONVERTIBLE_CAB requires conversion_date")
            if not (self.dated_date < self.conversion_date <= self.maturity_date):
                raise ValueError("conversion_date must fall between dated and maturity dates")
        if self.payment_frequency not in (1, 2, 4, 12):
            raise ValueError("payment_frequency must be 1, 2, 4 or 12")
        if self.compounding_frequency not in (0, 1, 2, 4, 12):
            raise ValueError("compounding_frequency must be 0 (simple), 1, 2, 4 or 12")


@dataclass(frozen=True)
class CashFlow:
    date: date
    amount: float  # per 100 par


@dataclass(frozen=True)
class AccretionPoint:
    date: date
    value: float   # accreted value per 100 par


@dataclass(frozen=True)
class VendorView:
    """What a vendor / security master says about the bond."""

    price: float                    # per 100 par
    price_convention: str           # "clean" | "dirty"
    coupon: float                   # annual decimal
    accrual_type: str               # vendor label, normalized lower-case


@dataclass(frozen=True)
class Treatment:
    """Correct accounting treatment derived from document terms. Per 100 par unless noted."""

    as_of: date
    interest_type: InterestType
    accreted_value: float | None            # None for current pay
    true_accrued: float                     # accrued-but-unpaid interest embedded in value
    vendor_accrued: float                   # accrual fund accounting books from vendor terms
    full_value: float                       # dirty price (vendor price normalized to dirty)
    correct_clean: float
    correct_dirty: float
    vendor_clean: float
    yield_document_terms: float | None      # yield implied by price under document terms
    yield_vendor_terms: float | None        # yield implied by price under vendor terms
    accretion_since_dated: float            # economic income since accrual start
    unbooked_per_100: float                 # true_accrued - vendor_accrued (headline basis)
    unbooked_income_usd: float              # par-weighted, headline (option a)
    income_next_12m_document: float = 0.0     # forward income run-rate under document terms
    income_next_12m_vendor: float = 0.0       # what accounting would book from vendor terms
    run_rate_gap_usd: float = 0.0             # (document - vendor) next-12m income, par-weighted
    window_start: date | None = None
    unbooked_window_usd: float | None = None  # since acquisition (option b), if supplied
    schedule: list[AccretionPoint] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
