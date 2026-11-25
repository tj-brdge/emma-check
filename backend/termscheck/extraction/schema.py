"""Structured extraction schema. Every extracted value carries the page number and a short
verbatim excerpt that supports it."""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class InterestTypeValue(StrEnum):
    current_pay = "current_pay"
    capital_appreciation = "capital_appreciation"
    deferred_interest = "deferred_interest"
    convertible_cab = "convertible_cab"


class DayCountValue(StrEnum):
    thirty_360 = "30/360"
    act_360 = "ACT/360"
    act_365 = "ACT/365"
    act_act = "ACT/ACT"


class CallKind(StrEnum):
    optional = "optional"
    mandatory_sinking_fund = "mandatory_sinking_fund"
    extraordinary = "extraordinary"
    make_whole = "make_whole"
    other = "other"


class _Cited(BaseModel):
    page: int | None = Field(description="1-based page number from the <page number=...> tag")
    excerpt: str | None = Field(description="Verbatim text copied from that page (<= 40 words)")


class CitedText(_Cited):
    value: str | None


class CitedNumber(_Cited):
    value: float | None


class CitedInt(_Cited):
    value: int | None


class CitedDate(_Cited):
    value: str | None = Field(description="ISO date YYYY-MM-DD")


class CitedInterestType(_Cited):
    value: InterestTypeValue | None


class CitedDayCount(_Cited):
    value: DayCountValue | None


class CallFeature(_Cited):
    kind: CallKind
    first_call_date: str | None = Field(description="ISO date or null")
    price: str | None = Field(description="Redemption price as stated, e.g. '100%' or 'Accreted Value'")
    description: str


class ExtractedTerms(BaseModel):
    security_identification: CitedText = Field(
        description="Line that ties this bond to the target CUSIP (maturity schedule row)")
    interest_type: CitedInterestType
    interest_rate_pct: CitedNumber = Field(description="Coupon or accretion rate in percent, e.g. 5.25")
    compounding_frequency: CitedInt = Field(
        description="Compounding periods per year for accreting/deferred interest (0 = simple); null for current pay")
    day_count: CitedDayCount
    accrual_start_date: CitedDate = Field(description="Date interest/accretion starts (dated date)")
    maturity_date: CitedDate
    payment_frequency: CitedInt = Field(
        description="Current interest payments per year; null if no interest is paid before maturity/conversion")
    payment_dates: CitedText = Field(description="Payment dates as stated, or 'at maturity'")
    first_payment_date: CitedDate
    first_compounding_date: CitedDate
    conversion_date: CitedDate = Field(description="Convertible CABs only")
    call_features: list[CallFeature]
    notes: str = Field(description="Ambiguities or conflicts the reviewer should know about")


CITED_FIELDS = [
    "security_identification", "interest_type", "interest_rate_pct", "compounding_frequency",
    "day_count", "accrual_start_date", "maturity_date", "payment_frequency", "payment_dates",
    "first_payment_date", "first_compounding_date", "conversion_date",
]
