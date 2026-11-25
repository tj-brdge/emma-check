"""Pure bond math: day counts, schedules, accretion, accrual, yields and treatment.

No I/O, database or LLM dependencies; safe to expose directly as MCP tools.
"""
from termscheck.plugins.muni.bondmath.accretion import accreted_value, accretion_schedule
from termscheck.plugins.muni.bondmath.accrual import accrued_interest, cash_flows, economic_income
from termscheck.core.daycount import days_30_360, year_fraction
from termscheck.plugins.muni.bondmath.treatment import BONDMATH_VERSION, compute_treatment, implied_yield
from termscheck.plugins.muni.bondmath.models import (AccretionPoint, CashFlow, DayCount, InterestTerms, InterestType, Treatment,
                    VendorView)
from termscheck.plugins.muni.bondmath.yields import dirty_price_from_yield, yield_from_dirty_price

__all__ = [
    "AccretionPoint", "BONDMATH_VERSION", "CashFlow", "DayCount", "InterestTerms", "InterestType",
    "Treatment", "VendorView", "accreted_value", "accretion_schedule", "accrued_interest",
    "cash_flows", "compute_treatment", "days_30_360", "dirty_price_from_yield", "economic_income",
    "implied_yield", "year_fraction", "yield_from_dirty_price",
]
