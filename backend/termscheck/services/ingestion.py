from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from termscheck.audit import record
from termscheck.db.models import Holding, LedgerRow, PriceHistory, UploadBatch, VendorTerms
from termscheck.core.records import BLANK
from termscheck.ingest import ParseResult, parse_holdings, parse_ledger, parse_price_history, parse_vendor

KINDS = ("holdings", "vendor_secondary", "price_history", "ledger")
RECORD_COLUMNS = ("vendor", "source_role", "source_row", "cusip", "asset_class", "description", "price",
                  "price_convention", "coupon", "accrual_type", "maturity_date", "issue_date", "rating", "sector",
                  "state", "payment_frequency", "day_count", "vendor_yield", "product_type", "factor",
                  "factor_date", "payment_delay_days", "rate_type")


class IngestError(Exception):
    def __init__(self, result: ParseResult):
        self.result = result
        super().__init__(f"{len(result.errors)} validation errors")


@dataclass
class IngestOutcome:
    batch: UploadBatch
    result: ParseResult


def ingest_file(session: Session, *, kind: str, filename: str, text: str, user: str,
                vendor: str | None = None) -> IngestOutcome:
    if kind == "holdings":
        vendor = vendor or "FundAccounting"
        res = parse_holdings(text, vendor)
    elif kind == "vendor_secondary":
        vendor = vendor or "VendorB"
        res = parse_vendor(text, vendor)
    elif kind == "price_history":
        res = parse_price_history(text)
    elif kind == "ledger":
        res = parse_ledger(text)
    else:
        raise ValueError(f"unknown upload kind {kind!r}")
    if not res.ok:
        raise IngestError(res)

    batch = UploadBatch(kind=kind, vendor=vendor, filename=filename, sha256=res.sha256,
                        row_count=res.row_count, uploaded_by=user)
    session.add(batch)
    session.flush()
    for p in res.positions:
        session.add(Holding(batch_id=batch.id, portfolio=p.portfolio, cusip=p.cusip, par=p.par,
                            acquisition_date=p.acquisition_date))
    for r in res.records:
        session.add(VendorTerms(batch_id=batch.id, field_states=dict(r.states), raw=dict(r.raw),
                                **{k: getattr(r, k) for k in RECORD_COLUMNS}))
    for i, e in enumerate(res.ledger, start=1):
        session.add(LedgerRow(batch_id=batch.id, row_no=i, portfolio=e.portfolio, cusip=e.cusip,
                              entry_date=e.entry_date, cash=e.cash, kind=e.kind, booked_income=e.booked_income))
    if res.prices:
        session.bulk_insert_mappings(PriceHistory, [
            dict(batch_id=batch.id, cusip=p.cusip, price_date=p.price_date, price=p.price,
                 convention=p.convention) for p in res.prices])
    session.flush()
    record(session, actor=user, event_type="upload.accepted", entity_type="upload_batch", entity_id=batch.id,
           payload={"kind": kind, "vendor": vendor, "filename": filename, "sha256": res.sha256,
                    "rows": res.row_count, "positions": len(res.positions), "records": len(res.records),
                    "prices": len(res.prices), "ledger_entries": len(res.ledger),
                    "blank_cells": blank_summary(res)})
    return IngestOutcome(batch, res)


def record_rejection(session: Session, *, kind: str, filename: str, user: str, result: ParseResult) -> None:
    record(session, actor=user, event_type="upload.rejected", entity_type="upload", entity_id=result.sha256[:16],
           payload={"kind": kind, "filename": filename, "sha256": result.sha256, "rows": result.row_count,
                    "error_count": len(result.errors),
                    "errors": [vars(e) for e in result.errors[:50]]})


def blank_summary(res: ParseResult) -> dict[str, int]:
    """Count of blank cells per term field (blank is recorded, never converted to zero)."""
    out: dict[str, int] = {}
    for r in res.records:
        for k, st in r.states.items():
            if st == BLANK:
                out[k] = out.get(k, 0) + 1
    return out
