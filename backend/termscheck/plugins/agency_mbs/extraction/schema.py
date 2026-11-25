"""Structured extraction schema for agency MBS offering circular supplements. Every value
carries the page number and a verbatim excerpt."""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from termscheck.plugins.agency_mbs.extraction._cited import (CitedDate, CitedDayCount, CitedInt, CitedNumber,
                                                             CitedText)


class RateTypeValue(StrEnum):
    fixed = "fixed"
    wac = "wac"
    arm = "arm"


class ProductValue(StrEnum):
    pass_through = "pass_through"
    arm = "arm"
    po = "po"
    io = "io"


class CitedRateType(BaseModel):
    value: RateTypeValue | None
    page: int | None = Field(description="1-based page number from the <page number=...> tag")
    excerpt: str | None = Field(description="Verbatim text copied from that page (<= 40 words)")


class CitedProduct(BaseModel):
    value: ProductValue | None
    page: int | None
    excerpt: str | None


class MBSExtractedTerms(BaseModel):
    security_identification: CitedText = Field(description="Line naming the target CUSIP (and pool number)")
    product_type: CitedProduct
    rate_type: CitedRateType = Field(description="fixed, wac (net coupon = collateral WAC less a fee/strip), or arm")
    net_coupon_pct: CitedNumber = Field(description="Stated (initial or fixed) net coupon / pass-through rate in percent")
    reset_rule: CitedText = Field(description="How a variable net coupon is determined and when it changes; null if fixed")
    rate_spread_pct: CitedNumber = Field(
        description="Amount subtracted from the WAC (servicing + guarantee fee) or ARM margin, in percent")
    current_factor: CitedNumber = Field(description="Pool factor stated in the document, if any")
    factor_date: CitedDate = Field(description="Month the stated factor applies to")
    payment_delay_days: CitedInt = Field(description="Stated payment delay in days")
    day_count: CitedDayCount
    issue_date: CitedDate = Field(description="Issue date / date interest begins to accrue")
    first_payment_date: CitedDate
    maturity_date: CitedDate
    payment_frequency: CitedInt = Field(description="Payments per year (monthly -> 12)")
    notes: str = Field(description="Ambiguities or conflicts the reviewer should know about")


CITED_FIELDS = [
    "security_identification", "product_type", "rate_type", "net_coupon_pct", "reset_rule", "rate_spread_pct",
    "current_factor", "factor_date", "payment_delay_days", "day_count", "issue_date", "first_payment_date",
    "maturity_date", "payment_frequency",
]
