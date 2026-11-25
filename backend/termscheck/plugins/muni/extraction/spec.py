"""Muni official-statement extraction spec: schema, prompt and mapping to bond-math terms."""
from __future__ import annotations

import calendar
from datetime import date
from typing import Any

from termscheck.extraction.spec import ExtractionSpec
from termscheck.plugins.muni.bondmath import DayCount, InterestTerms, InterestType
from termscheck.plugins.muni.extraction.prompt import PROMPT_VERSION, SYSTEM
from termscheck.plugins.muni.extraction.schema import CITED_FIELDS, ExtractedTerms

REQUIRED_FOR_MATH = ["interest_type", "interest_rate_pct", "accrual_start_date", "maturity_date"]
DATE_FIELDS = {"accrual_start_date", "maturity_date", "first_payment_date", "first_compounding_date",
               "conversion_date"}


def value_repr(name: str, value: Any) -> list[str] | None:
    if value is None:
        return None
    if name == "interest_rate_pct":
        return [f"{value:.3f}", f"{value:.2f}", f"{value:g}"]
    if name in DATE_FIELDS:
        try:
            d = date.fromisoformat(value)
        except ValueError:
            return None
        return [f"{calendar.month_name[d.month]} {d.day}, {d.year}", f"{d:%m/%d/%Y}", str(d.year)]
    return None


def _date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def to_interest_terms(t: ExtractedTerms) -> tuple[InterestTerms | None, list[str]]:
    """Map extracted values to bond-math terms. Returns (terms or None, problems).
    Anything not stated is reported, never silently defaulted."""
    problems: list[str] = []
    it = t.interest_type.value
    rate = t.interest_rate_pct.value
    start, mat = _date(t.accrual_start_date.value), _date(t.maturity_date.value)
    for name in REQUIRED_FOR_MATH:
        if getattr(t, name).value is None:
            problems.append(f"{name} not found in document")
    if t.accrual_start_date.value and start is None:
        problems.append("accrual_start_date is not a valid ISO date")
    if t.maturity_date.value and mat is None:
        problems.append("maturity_date is not a valid ISO date")
    if rate is not None and not (0 <= rate <= 30):
        problems.append(f"interest rate {rate}% outside plausible range")
    if problems:
        return None, problems
    itype = InterestType(it.value)
    comp = t.compounding_frequency.value
    if itype is not InterestType.CURRENT_PAY and comp is None:
        problems.append("compounding frequency not stated; assumed semiannual (muni convention)")
        comp = 2
    dc = DayCount(t.day_count.value.value) if t.day_count.value else DayCount.THIRTY_360
    if t.day_count.value is None:
        problems.append("day count not stated; muni default 30/360 applied")
    pay = t.payment_frequency.value
    pays_current = itype in (InterestType.CURRENT_PAY, InterestType.CONVERTIBLE_CAB)
    if pays_current and pay is None:
        problems.append("payment frequency not stated; assumed semiannual (muni convention)")
        pay = 2
    if pay is not None and pay not in (1, 2, 4, 12):
        problems.append(f"payment frequency {pay} not supported; assumed semiannual")
        pay = 2
    try:
        terms = InterestTerms(
            interest_type=itype, rate=rate / 100.0, dated_date=start, maturity_date=mat, day_count=dc,
            payment_frequency=pay or 2, compounding_frequency=comp if comp is not None else 2,
            first_coupon_date=_date(t.first_payment_date.value),
            first_compounding_date=_date(t.first_compounding_date.value),
            conversion_date=_date(t.conversion_date.value),
        )
    except ValueError as e:
        return None, problems + [f"terms inconsistent: {e}"]
    return terms, problems


MUNI_SPEC = ExtractionSpec(
    key="muni", document_label="official statement", schema=ExtractedTerms, system_prompt=SYSTEM,
    prompt_version=PROMPT_VERSION, cited_fields=tuple(CITED_FIELDS), list_fields=("call_features",),
    identification_field="security_identification", value_repr=value_repr, map_terms=to_interest_terms,
)
