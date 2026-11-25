"""Typed inputs and outputs for the screening layer (no DB, no LLM)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class SecurityRecord:
    """One vendor's reference data for a security."""

    vendor: str
    cusip: str
    description: str
    price: float                      # per 100 par
    price_convention: str             # "clean" | "dirty"
    coupon: float                     # annual decimal
    accrual_type: str                 # vendor label, lower-case
    maturity_date: date
    issue_date: date
    rating: str
    sector: str
    state: str
    payment_frequency: int | None = None
    day_count: str | None = None
    vendor_yield: float | None = None  # annual decimal


@dataclass(frozen=True)
class Position:
    portfolio: str
    cusip: str
    par: float
    acquisition_date: date | None = None


@dataclass(frozen=True)
class PricePoint:
    cusip: str
    price_date: date
    price: float
    convention: str = "clean"


@dataclass
class ScreenInput:
    as_of: date
    positions: list[Position]
    primary: dict[str, SecurityRecord]                     # cusip -> primary vendor record
    secondary: dict[str, SecurityRecord] = field(default_factory=dict)
    history: dict[str, list[PricePoint]] = field(default_factory=dict)


@dataclass(frozen=True)
class Flag:
    rule: str
    cusip: str
    severity: int                     # 0-100
    message: str
    inputs: dict[str, Any]
    computed: dict[str, Any]


@dataclass
class ScreenResult:
    flags: list[Flag]
    implied_yields: dict[str, float | None]
    config: dict[str, Any]

    def flagged_cusips(self) -> set[str]:
        return {f.cusip for f in self.flags}

    def by_cusip(self) -> dict[str, list[Flag]]:
        out: dict[str, list[Flag]] = {}
        for f in self.flags:
            out.setdefault(f.cusip, []).append(f)
        return out
