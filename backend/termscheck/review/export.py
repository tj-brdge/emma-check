"""CSV export of approved findings for the operations team (one row per position)."""
from __future__ import annotations

import csv
import io
from typing import Any

COLUMNS = [
    "finding_id", "asset_class", "cusip", "description", "as_of", "portfolio", "par",
    "vendor_coupon_pct", "vendor_accrual_type", "vendor_price", "vendor_price_convention",
    "document_interest_type", "document_rate_pct", "document_compounding", "document_day_count",
    "document_accrual_start", "document_maturity",
    "document_payment_delay_days",
    "accreted_value_per_100", "accrued_interest_per_100", "correct_clean_per_100", "correct_dirty_per_100",
    "current_factor", "current_face", "interest_receivable_document", "interest_receivable_book",
    "unbooked_income_usd", "run_rate_gap_usd_12m", "unbooked_since_acquisition_usd",
    "citations", "approved_by", "approved_at", "approval_comment", "finding_headline",
]


# Columns that can hold free text from outside the app (vendor files, reviewers, documents).
TEXT_COLUMNS = {"description", "portfolio", "vendor_accrual_type", "vendor_price_convention",
                "document_interest_type", "document_day_count", "citations", "approved_by", "approval_comment",
                "finding_headline", "cusip", "asset_class"}
FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r", "\n")


def safe_cell(column: str, value: Any) -> Any:
    """Neutralise spreadsheet formula injection in text columns (prefix with an apostrophe).
    Numeric columns are left alone so legitimate negatives such as -38179.00 stay numbers."""
    if value is None:
        return ""
    if column in TEXT_COLUMNS and isinstance(value, str) and value.startswith(FORMULA_LEADS):
        return "'" + value
    return value


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: safe_cell(k, r.get(k)) for k in COLUMNS})
    return buf.getvalue()
