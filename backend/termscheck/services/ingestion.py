from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..audit import record
from ..db.models import Holding, PriceHistory, UploadBatch, VendorTerms
from ..ingest import ParseResult, parse_holdings, parse_price_history, parse_vendor

KINDS = ("holdings", "vendor_secondary", "price_history")


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
        vendor = vendor or "VendorA"
        res = parse_holdings(text, vendor)
    elif kind == "vendor_secondary":
        vendor = vendor or "VendorB"
        res = parse_vendor(text, vendor)
    elif kind == "price_history":
        res = parse_price_history(text)
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
        session.add(VendorTerms(
            batch_id=batch.id, vendor=r.vendor, cusip=r.cusip, description=r.description,
            price=r.price, price_convention=r.price_convention, coupon=r.coupon,
            accrual_type=r.accrual_type, maturity_date=r.maturity_date, issue_date=r.issue_date,
            rating=r.rating, sector=r.sector, state=r.state, payment_frequency=r.payment_frequency,
            day_count=r.day_count, vendor_yield=r.vendor_yield))
    if res.prices:
        session.bulk_insert_mappings(PriceHistory, [
            dict(batch_id=batch.id, cusip=p.cusip, price_date=p.price_date, price=p.price,
                 convention=p.convention) for p in res.prices])
    session.flush()
    record(session, actor=user, event_type="upload.accepted", entity_type="upload_batch", entity_id=batch.id,
           payload={"kind": kind, "vendor": vendor, "filename": filename, "sha256": res.sha256,
                    "rows": res.row_count, "positions": len(res.positions), "records": len(res.records),
                    "prices": len(res.prices)})
    return IngestOutcome(batch, res)


def record_rejection(session: Session, *, kind: str, filename: str, user: str, result: ParseResult) -> None:
    record(session, actor=user, event_type="upload.rejected", entity_type="upload", entity_id=result.sha256[:16],
           payload={"kind": kind, "filename": filename, "sha256": result.sha256, "rows": result.row_count,
                    "error_count": len(result.errors),
                    "errors": [vars(e) for e in result.errors[:50]]})
