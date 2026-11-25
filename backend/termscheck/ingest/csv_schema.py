"""CSV formats accepted by Terms Check.

Conventions
- Coupons and yields are in PERCENT (5.25 = 5.25%); stored internally as decimals.
- Prices are per 100 par. Par is in currency units (face amount held).
- Dates: YYYY-MM-DD or MM/DD/YYYY.
- Header names are case-insensitive; common aliases are accepted.
"""
from __future__ import annotations

HOLDINGS_REQUIRED = [
    "cusip", "description", "par", "price", "price_convention", "coupon", "accrual_type",
    "maturity_date", "issue_date", "rating", "sector", "state",
]
HOLDINGS_OPTIONAL = [
    "portfolio", "vendor_yield", "payment_frequency", "day_count", "acquisition_date",
    "asset_class", "product_type", "factor", "factor_date", "payment_delay_days", "rate_type",
]
# Cells that must be filled in. Every other term cell may be blank: blanks are recorded as
# blank (never as zero) and surface in the null-vs-zero screen.
NON_BLANK = ["cusip", "description", "price", "maturity_date"]
VENDOR_REQUIRED = [c for c in HOLDINGS_REQUIRED if c != "par"]
VENDOR_OPTIONAL = ["par", "vendor_yield", "payment_frequency", "day_count", "asset_class", "product_type",
                   "factor", "factor_date", "payment_delay_days", "rate_type"]
LEDGER_REQUIRED = ["cusip", "entry_date", "cash", "type"]
LEDGER_OPTIONAL = ["portfolio", "booked_income"]
LEDGER_TYPES = {"interest", "principal"}
HISTORY_REQUIRED = ["cusip", "price_date", "price"]
HISTORY_OPTIONAL = ["price_convention"]

ALIASES = {
    "market_price": "price", "px": "price", "vendor_price": "price",
    "convention": "price_convention", "price_type": "price_convention",
    "vendor_coupon": "coupon", "coupon_rate": "coupon",
    "vendor_accrual_type": "accrual_type", "accrual": "accrual_type",
    "maturity": "maturity_date", "issue": "issue_date", "dated_date": "issue_date",
    "par_amount": "par", "quantity": "par", "face": "par",
    "yield": "vendor_yield", "frequency": "payment_frequency", "pay_freq": "payment_frequency",
    "date": "price_date", "cash_received": "cash", "amount": "cash", "payment_date": "entry_date",
    "receipt_date": "entry_date", "cash_type": "type", "booked": "booked_income",
    "asset_type": "asset_class", "product": "product_type", "pool_factor": "factor",
    "delay": "payment_delay_days", "delay_days": "payment_delay_days", "coupon_type": "rate_type",
}

# Text a vendor uses to mean "no value". Treated as blank; the raw text is kept.
NULL_TOKENS = {"", "na", "n/a", "#n/a", "null", "none", "nan", "-", "--"}
ASSET_CLASSES = {"muni": "muni", "municipal": "muni", "agency_mbs": "agency_mbs", "mbs": "agency_mbs",
                 "agency mbs": "agency_mbs"}
PRODUCT_TYPES = {"pass_through", "arm", "po", "io", "cmo", "bond"}
RATE_TYPES = {"fixed", "wac", "arm", "variable", "zero"}
PAYMENT_FREQUENCIES = {0, 1, 2, 4, 12}

PRICE_CONVENTIONS = {"clean", "dirty"}
ACCRUAL_TYPES = {"fixed", "zero", "deferred", "accreting", "cab", "floating", "variable",
                 "step", "none", "deferred_interest", "capital_appreciation", "wac", "arm"}
DAY_COUNTS = {"30/360", "act/360", "act/365", "act/act"}
