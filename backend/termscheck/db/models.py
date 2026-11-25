"""SQLAlchemy models. Numeric columns use asdecimal=False and are read as floats for the math layer."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (BigInteger, Date, DateTime, ForeignKey, Index, Integer, Numeric, String,
                        Text, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from termscheck.db.base import Base

PRICE = Numeric(18, 6, asdecimal=False)
RATE = Numeric(14, 10, asdecimal=False)
MONEY = Numeric(20, 2, asdecimal=False)


class UploadBatch(Base):
    __tablename__ = "upload_batch"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))  # holdings | vendor_secondary | price_history
    vendor: Mapped[str | None] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[str] = mapped_column(String(128))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Holding(Base):
    __tablename__ = "holding"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batch.id"), index=True)
    portfolio: Mapped[str] = mapped_column(String(64))
    cusip: Mapped[str] = mapped_column(String(9), index=True)
    par: Mapped[float] = mapped_column(MONEY)
    acquisition_date: Mapped[date | None] = mapped_column(Date)


class VendorTerms(Base):
    """One source's terms for a CUSIP. Term columns are NULL when the source left them blank or
    did not supply them; ``field_states`` records which ("blank" vs "absent"), ``raw`` the text."""
    __tablename__ = "vendor_terms"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batch.id"), index=True)
    vendor: Mapped[str] = mapped_column(String(64))
    source_role: Mapped[str] = mapped_column(String(8), server_default="vendor", default="vendor")
    source_row: Mapped[int | None] = mapped_column(Integer)
    cusip: Mapped[str] = mapped_column(String(9), index=True)
    asset_class: Mapped[str] = mapped_column(String(32), server_default="muni", default="muni", index=True)
    description: Mapped[str] = mapped_column(Text)
    price: Mapped[float] = mapped_column(PRICE)
    price_convention: Mapped[str | None] = mapped_column(String(8))
    coupon: Mapped[float | None] = mapped_column(RATE)
    accrual_type: Mapped[str | None] = mapped_column(String(32))
    maturity_date: Mapped[date] = mapped_column(Date)
    issue_date: Mapped[date | None] = mapped_column(Date)
    rating: Mapped[str | None] = mapped_column(String(16))
    sector: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str | None] = mapped_column(String(8))
    payment_frequency: Mapped[int | None] = mapped_column(Integer)
    day_count: Mapped[str | None] = mapped_column(String(16))
    vendor_yield: Mapped[float | None] = mapped_column(RATE)
    product_type: Mapped[str | None] = mapped_column(String(16))
    factor: Mapped[float | None] = mapped_column(Numeric(14, 10, asdecimal=False))
    factor_date: Mapped[date | None] = mapped_column(Date)
    payment_delay_days: Mapped[int | None] = mapped_column(Integer)
    rate_type: Mapped[str | None] = mapped_column(String(16))
    field_states: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", default=dict)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", default=dict)


class PriceHistory(Base):
    __tablename__ = "price_history"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batch.id"), index=True)
    cusip: Mapped[str] = mapped_column(String(9))
    price_date: Mapped[date] = mapped_column(Date)
    price: Mapped[float] = mapped_column(PRICE)
    convention: Mapped[str] = mapped_column(String(8))
    __table_args__ = (Index("ix_price_history_batch_cusip", "batch_id", "cusip"),)


class ScreenRun(Base):
    __tablename__ = "screen_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    as_of: Mapped[date] = mapped_column(Date)
    holdings_batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batch.id"))
    secondary_batch_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batch.id"))
    history_batch_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batch.id"))
    vendor_batch_ids: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]", default=list)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    started_by: Mapped[str] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    flag_count: Mapped[int] = mapped_column(Integer, default=0)
    flags: Mapped[list[ScreenFlag]] = relationship(back_populates="run", order_by="ScreenFlag.id")


class ScreenFlag(Base):
    __tablename__ = "screen_flag"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("screen_run.id"), index=True)
    cusip: Mapped[str] = mapped_column(String(9), index=True)
    rule: Mapped[str] = mapped_column(String(64))
    severity: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3, asdecimal=False), server_default="0.5", default=0.5)
    message: Mapped[str] = mapped_column(Text)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB)
    computed: Mapped[dict[str, Any]] = mapped_column(JSONB)
    run: Mapped[ScreenRun] = relationship(back_populates="flags")


class Document(Base):
    __tablename__ = "document"
    id: Mapped[int] = mapped_column(primary_key=True)
    cusip: Mapped[str] = mapped_column(String(9), index=True)
    asset_class: Mapped[str] = mapped_column(String(32), server_default="muni", default="muni", index=True)
    source: Mapped[str] = mapped_column(String(16))
    source_ref: Mapped[str] = mapped_column(String(128))
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    page_count: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(Text)
    uploaded_by: Mapped[str] = mapped_column(String(128))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentPage(Base):
    __tablename__ = "document_page"
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id"), primary_key=True)
    page_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)


class Extraction(Base):
    __tablename__ = "extraction"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id"), index=True)
    cusip: Mapped[str] = mapped_column(String(9), index=True)
    asset_class: Mapped[str] = mapped_column(String(32), server_default="muni", default="muni", index=True)
    model_requested: Mapped[str] = mapped_column(String(64))
    model_served: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))           # ok | needs_review | failed
    terms: Mapped[dict[str, Any] | None] = mapped_column(JSONB)        # ExtractedTerms
    citation_checks: Mapped[list[Any] | None] = mapped_column(JSONB)
    interest_terms: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # mapped bond-math terms
    problems: Mapped[list[Any] | None] = mapped_column(JSONB)
    page_selection: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    llm_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Finding(Base):
    __tablename__ = "finding"
    id: Mapped[int] = mapped_column(primary_key=True)
    cusip: Mapped[str] = mapped_column(String(9), index=True)
    asset_class: Mapped[str] = mapped_column(String(32), server_default="muni", default="muni", index=True)
    description: Mapped[str] = mapped_column(Text)
    as_of: Mapped[date] = mapped_column(Date)
    screen_run_id: Mapped[int] = mapped_column(ForeignKey("screen_run.id"))
    extraction_id: Mapped[int] = mapped_column(ForeignKey("extraction.id"))
    income_impact_usd: Mapped[float] = mapped_column(MONEY)
    run_rate_gap_usd: Mapped[float] = mapped_column(MONEY)
    headline: Mapped[str] = mapped_column(Text)
    narrative: Mapped[dict[str, Any]] = mapped_column(JSONB)    # vendor_says, document_says, ...
    comparison: Mapped[list[Any]] = mapped_column(JSONB)
    rules: Mapped[list[Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="open")  # derived from review actions
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    computations: Mapped[list[Computation]] = relationship(back_populates="finding", order_by="Computation.id")


class Computation(Base):
    __tablename__ = "computation"
    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("finding.id"), index=True)
    extraction_id: Mapped[int] = mapped_column(ForeignKey("extraction.id"))
    holding_id: Mapped[int] = mapped_column(ForeignKey("holding.id"))
    as_of: Mapped[date] = mapped_column(Date)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB)
    outputs: Mapped[dict[str, Any]] = mapped_column(JSONB)
    bondmath_version: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finding: Mapped[Finding] = relationship(back_populates="computations")


class ReviewAction(Base):
    """Append-only reviewer actions; Finding.status is a cache derived from these."""
    __tablename__ = "review_action"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("finding.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))
    from_status: Mapped[str] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    comment: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(128))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ts: Mapped[str] = mapped_column(String(40))            # ISO-8601 UTC, part of the hashed body
    actor: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    __table_args__ = (Index("ix_audit_event_entity", "entity_type", "entity_id"),)
