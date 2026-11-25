"""Write typed records back to the CSV formats (used by the synthetic generator and exports)."""
from __future__ import annotations

import csv
import io

from termscheck.core.records import Position, PricePoint, SecurityRecord


def _cell(x) -> str:
    """Blank only for None: 0 must be written as 0."""
    return "" if x is None else str(x)


MBS_COLS = ["asset_class", "product_type", "factor", "factor_date", "payment_delay_days", "rate_type"]


def _date(d) -> str:
    return "" if d is None else d.isoformat()


def _mbs(r: SecurityRecord) -> list[str]:
    return [r.asset_class, _cell(r.product_type), "" if r.factor is None else f"{r.factor:.10f}",
            _date(r.factor_date), _cell(r.payment_delay_days), _cell(r.rate_type)]


def ledger_csv(entries) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["portfolio", "cusip", "entry_date", "cash", "type", "booked_income"])
    for e in entries:
        w.writerow([e.portfolio, e.cusip, e.entry_date.isoformat(), f"{e.cash:.2f}", e.kind,
                    "" if e.booked_income is None else f"{e.booked_income:.2f}"])
    return buf.getvalue()


def _pct(x: float | None) -> str:
    return "" if x is None else f"{x * 100:.4f}"


def holdings_csv(pairs: list[tuple[Position, SecurityRecord]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    mbs = any(r.asset_class != "muni" for _, r in pairs)
    w.writerow(["portfolio", "cusip", "description", "par", "price", "price_convention", "coupon",
                "accrual_type", "maturity_date", "issue_date", "rating", "sector", "state",
                "vendor_yield", "payment_frequency", "day_count", "acquisition_date"] + (MBS_COLS if mbs else []))
    for pos, r in pairs:
        w.writerow([pos.portfolio, r.cusip, r.description, f"{pos.par:.2f}", f"{r.price:.3f}",
                    _cell(r.price_convention), _pct(r.coupon), _cell(r.accrual_type), r.maturity_date.isoformat(),
                    _date(r.issue_date), _cell(r.rating), _cell(r.sector), _cell(r.state), _pct(r.vendor_yield),
                    _cell(r.payment_frequency), _cell(r.day_count), _date(pos.acquisition_date)]
                   + (_mbs(r) if mbs else []))
    return buf.getvalue()


def vendor_csv(records: list[SecurityRecord]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    mbs = any(r.asset_class != "muni" for r in records)
    w.writerow(["cusip", "description", "price", "price_convention", "coupon", "accrual_type",
                "maturity_date", "issue_date", "rating", "sector", "state", "vendor_yield",
                "payment_frequency", "day_count"] + (MBS_COLS if mbs else []))
    for r in records:
        w.writerow([r.cusip, r.description, f"{r.price:.3f}", _cell(r.price_convention), _pct(r.coupon),
                    _cell(r.accrual_type), r.maturity_date.isoformat(), _date(r.issue_date), _cell(r.rating),
                    _cell(r.sector), _cell(r.state), _pct(r.vendor_yield), _cell(r.payment_frequency),
                    _cell(r.day_count)] + (_mbs(r) if mbs else []))
    return buf.getvalue()


def history_csv(points: list[PricePoint]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["cusip", "price_date", "price", "price_convention"])
    for p in points:
        w.writerow([p.cusip, p.price_date.isoformat(), f"{p.price:.3f}", p.convention])
    return buf.getvalue()
