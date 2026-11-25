"""Write typed records back to the CSV formats (used by the synthetic generator and exports)."""
from __future__ import annotations

import csv
import io

from ..screens.models import Position, PricePoint, SecurityRecord


def _pct(x: float | None) -> str:
    return "" if x is None else f"{x * 100:.4f}"


def holdings_csv(pairs: list[tuple[Position, SecurityRecord]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["portfolio", "cusip", "description", "par", "price", "price_convention", "coupon",
                "accrual_type", "maturity_date", "issue_date", "rating", "sector", "state",
                "vendor_yield", "payment_frequency", "day_count", "acquisition_date"])
    for pos, r in pairs:
        w.writerow([pos.portfolio, r.cusip, r.description, f"{pos.par:.2f}", f"{r.price:.3f}",
                    r.price_convention, _pct(r.coupon), r.accrual_type, r.maturity_date.isoformat(),
                    r.issue_date.isoformat(), r.rating, r.sector, r.state, _pct(r.vendor_yield),
                    r.payment_frequency or "", r.day_count or "",
                    pos.acquisition_date.isoformat() if pos.acquisition_date else ""])
    return buf.getvalue()


def vendor_csv(records: list[SecurityRecord]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["cusip", "description", "price", "price_convention", "coupon", "accrual_type",
                "maturity_date", "issue_date", "rating", "sector", "state", "vendor_yield",
                "payment_frequency", "day_count"])
    for r in records:
        w.writerow([r.cusip, r.description, f"{r.price:.3f}", r.price_convention, _pct(r.coupon),
                    r.accrual_type, r.maturity_date.isoformat(), r.issue_date.isoformat(), r.rating,
                    r.sector, r.state, _pct(r.vendor_yield), r.payment_frequency or "", r.day_count or ""])
    return buf.getvalue()


def history_csv(points: list[PricePoint]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["cusip", "price_date", "price", "price_convention"])
    for p in points:
        w.writerow([p.cusip, p.price_date.isoformat(), f"{p.price:.3f}", p.convention])
    return buf.getvalue()
