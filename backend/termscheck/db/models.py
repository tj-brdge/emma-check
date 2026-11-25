"""SQLAlchemy models. Numeric columns use asdecimal=False and are read as floats for the math layer."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (BigInteger, Date, DateTime, ForeignKey, Index, Integer, Numeric, String,
                        Text, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

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
    __tablename__ = "vendor_terms"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batch.id"), index=True)
    vendor: Mapped[str] = mapped_column(String(64))
    cusip: Mapped[str] = mapped_column(String(9), index=True)
    description: Mapped[str] = mapped_column(Text)
    price: Mapped[float] = mapped_column(PRICE)
    price_convention: Mapped[str] = mapped_column(String(8))
    coupon: Mapped[float] = mapped_column(RATE)
    accrual_type: Mapped[str] = mapped_column(String(32))
    maturity_date: Mapped[date] = mapped_column(Date)
    issue_date: Mapped[date] = mapped_column(Date)
    rating: Mapped[str] = mapped_column(String(16))
    sector: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(8))
    payment_frequency: Mapped[int | None] = mapped_column(Integer)
    day_count: Mapped[str | None] = mapped_column(String(16))
    vendor_yield: Mapped[float | None] = mapped_column(RATE)


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
    message: Mapped[str] = mapped_column(Text)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB)
    computed: Mapped[dict[str, Any]] = mapped_column(JSONB)
    run: Mapped[ScreenRun] = relationship(back_populates="flags")
