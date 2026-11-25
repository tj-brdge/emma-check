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


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in COLUMNS})
    return buf.getvalue()
