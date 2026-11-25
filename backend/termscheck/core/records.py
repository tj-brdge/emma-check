"""Typed inputs and outputs for the screening layer (no DB, no LLM)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


# Field states. A blank cell is never the same thing as zero.
VALUE, BLANK, ABSENT = "value", "blank", "absent"   # absent = column not supplied by this source

TERM_FIELDS = ("price_convention", "coupon", "accrual_type", "issue_date", "rating", "sector", "state",
               "payment_frequency", "day_count", "vendor_yield", "product_type", "factor", "factor_date",
               "payment_delay_days", "rate_type")


@dataclass(frozen=True)
class SecurityRecord:
    """One source's reference data for a security (the fund-accounting book or a vendor).

    Term fields are None when the source left them blank or did not supply them; ``states``
    says which, and ``raw`` keeps the original cell text. Nothing downstream may read None as 0.
    """

    vendor: str                         # source name, e.g. "FundAccounting", "FactSet"
    cusip: str
    description: str
    price: float                        # per 100 par (current face for MBS)
    price_convention: str | None        # "clean" | "dirty"
    coupon: float | None                # annual decimal
    accrual_type: str | None            # vendor label, lower-case
    maturity_date: date
    issue_date: date | None
    rating: str | None
    sector: str | None
    state: str | None
    payment_frequency: int | None = None
    day_count: str | None = None
    vendor_yield: float | None = None   # annual decimal
    asset_class: str = "muni"
    product_type: str | None = None     # MBS: pass_through | arm | po | io ...
    factor: float | None = None         # MBS: current factor
    factor_date: date | None = None     # MBS: month the factor applies to
    payment_delay_days: int | None = None
    rate_type: str | None = None        # MBS: fixed | wac | arm
    source_role: str = "vendor"         # "book" (fund accounting) | "vendor"
    source_row: int | None = None       # 1-based data row in the source file
    states: dict[str, str] = field(default_factory=dict, compare=False, hash=False)
    raw: dict[str, str] = field(default_factory=dict, compare=False, hash=False)

    def state_of(self, name: str) -> str:
        if name in self.states:
            return self.states[name]
        return VALUE if getattr(self, name) is not None else ABSENT

    def is_blank(self, name: str) -> bool:
        return self.state_of(name) == BLANK

    def is_zero(self, name: str) -> bool:
        v = getattr(self, name)
        return v is not None and not isinstance(v, (str, date)) and v == 0


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


@dataclass(frozen=True)
class LedgerEntry:
    portfolio: str
    cusip: str
    entry_date: date
    cash: float                       # currency amount received
    kind: str                         # "interest" | "principal"
    booked_income: float | None = None  # optional fund-accounting booked income for the period


@dataclass(frozen=True)
class CashPeriod:
    """The accrual period a cash receipt pays, as determined by the security's plugin."""
    start: date
    end: date
    face: float                      # face outstanding during the period (currency)
    years: float                     # accrual period length in years on the security's basis
    assumptions: tuple[str, ...] = ()


@dataclass
class ScreenInput:
    as_of: date
    positions: list[Position]
    primary: dict[str, SecurityRecord]                     # cusip -> book-of-record terms
    secondary: dict[str, SecurityRecord] = field(default_factory=dict)  # legacy: one vendor
    history: dict[str, list[PricePoint]] = field(default_factory=dict)
    vendors: dict[str, dict[str, SecurityRecord]] = field(default_factory=dict)  # source -> cusip -> record
    ledger: list[LedgerEntry] = field(default_factory=list)

    def vendor_sources(self) -> dict[str, dict[str, SecurityRecord]]:
        """All non-book sources (legacy ``secondary`` folded in under its vendor name)."""
        out = dict(self.vendors)
        if self.secondary:
            name = next(iter(self.secondary.values())).vendor
            out.setdefault(name, self.secondary)
        return out

    def sources_for(self, cusip: str) -> list[SecurityRecord]:
        recs = [self.primary[cusip]] if cusip in self.primary else []
        return recs + [v[cusip] for v in self.vendor_sources().values() if cusip in v]


@dataclass(frozen=True)
class Flag:
    rule: str
    cusip: str
    severity: int                     # 0-100
    message: str
    inputs: dict[str, Any]
    computed: dict[str, Any]
    confidence: float = 0.5           # rule-level prior that a flag is a real data defect

    @property
    def priority(self) -> float:
        return self.severity * self.confidence


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
