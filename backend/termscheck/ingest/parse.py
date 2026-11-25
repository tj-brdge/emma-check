"""Parse and validate uploaded CSVs into typed screen records.

A file with ANY row error is rejected as a whole; the caller gets a row-level error report.
Nothing is ever partially or silently ingested.
"""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date, datetime

from termscheck.core.records import ABSENT, BLANK, VALUE, Position, PricePoint, SecurityRecord
from termscheck.core.identifiers import cusip_check_digit
from termscheck.ingest import csv_schema as S


@dataclass
class RowError:
    row: int          # 1-based data row number (header = row 0)
    column: str | None
    message: str


@dataclass
class ParseResult:
    kind: str
    sha256: str
    row_count: int
    positions: list[Position] = field(default_factory=list)
    records: list[SecurityRecord] = field(default_factory=list)
    prices: list[PricePoint] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    warnings: list[RowError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class _RowParser:
    def __init__(self, row: dict[str, str], n: int, errors: list[RowError]):
        self.row, self.n, self.errors = row, n, errors
        self.states: dict[str, str] = {}
        self.raws: dict[str, str] = {}

    def _err(self, col: str, msg: str):
        self.errors.append(RowError(self.n, col, msg))

    def raw(self, col: str) -> str | None:
        v = self.row.get(col)
        if v is None:
            return None
        v = v.strip()
        return None if v.lower() in S.NULL_TOKENS else v

    def term(self, col: str, parse, *args, **kw):
        """Optional term cell: record value / blank / absent and the raw text. Never coerces."""
        if col not in self.row:
            self.states[col] = ABSENT
            return None
        self.raws[col] = self.row.get(col) or ""
        if self.raw(col) is None:
            self.states[col] = BLANK
            return None
        before = len(self.errors)
        v = parse(col, *args, required=False, **kw)
        if len(self.errors) == before:
            self.states[col] = VALUE
        return v

    def text(self, col: str, required: bool = True) -> str | None:
        v = self.raw(col)
        if v is None and required:
            self._err(col, "required value missing")
        return v

    def num(self, col: str, required: bool = True, lo: float | None = None, hi: float | None = None):
        v = self.raw(col)
        if v is None:
            if required:
                self._err(col, "required value missing")
            return None
        try:
            x = float(v.replace(",", "").replace("$", "").rstrip("%"))
        except ValueError:
            self._err(col, f"not a number: {v!r}")
            return None
        if lo is not None and x < lo or hi is not None and x > hi:
            self._err(col, f"{x} outside allowed range [{lo}, {hi}]")
            return None
        return x

    def day(self, col: str, required: bool = True) -> date | None:
        v = self.raw(col)
        if v is None:
            if required:
                self._err(col, "required value missing")
            return None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(v, fmt).date()
            except ValueError:
                pass
        self._err(col, f"unrecognised date: {v!r}")
        return None

    def choice(self, col: str, allowed: set[str], required: bool = True) -> str | None:
        v = self.raw(col)
        if v is None:
            if required:
                self._err(col, "required value missing")
            return None
        v = v.lower()
        if v not in allowed:
            self._err(col, f"{v!r} not one of {sorted(allowed)}")
            return None
        return v

    def cusip(self) -> str | None:
        v = self.text("cusip")
        if v is None:
            return None
        v = v.upper()
        if len(v) != 9 or not v.isalnum():
            self._err("cusip", f"CUSIP must be 9 alphanumeric characters: {v!r}")
            return None
        if cusip_check_digit(v[:8]) != v[8]:
            self._err("cusip", f"CUSIP check digit invalid: {v!r}")
            return None
        return v


def _read(text: str, required: list[str], optional: list[str]) -> tuple[list[dict], list[RowError]]:
    if text.startswith("﻿"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return [], [RowError(0, None, "file is empty")]
    mapping = {}
    for h in reader.fieldnames:
        k = (h or "").strip().lower().replace(" ", "_")
        mapping[h] = S.ALIASES.get(k, k)
    missing = [c for c in required if c not in mapping.values()]
    if missing:
        return [], [RowError(0, c, "required column missing") for c in missing]
    rows = [{mapping[k]: v for k, v in r.items() if k in mapping} for r in reader]
    return rows, []


def _int_choice(p: _RowParser, col: str, allowed: set[int], required: bool = False) -> int | None:
    x = p.num(col, required=required)
    if x is None:
        return None
    if x != int(x) or int(x) not in allowed:
        p._err(col, f"must be one of {sorted(allowed)}: {x:g}")
        return None
    return int(x)


def _security(p: _RowParser, vendor: str, role: str) -> SecurityRecord | None:
    before = len(p.errors)
    cusip = p.cusip()
    ac_raw = p.raw("asset_class")
    if "asset_class" in p.row and ac_raw is None:
        p._err("asset_class", "asset_class column present but blank")
    asset_class = "muni"
    if ac_raw is not None:
        asset_class = S.ASSET_CLASSES.get(ac_raw.strip().lower(), "")
        if not asset_class:
            p._err("asset_class", f"unknown asset class {ac_raw!r}")
    rec = dict(
        vendor=vendor, cusip=cusip, description=p.text("description"),
        price=p.num("price", lo=0.0001, hi=10000), maturity_date=p.day("maturity_date"),
        price_convention=p.term("price_convention", p.choice, S.PRICE_CONVENTIONS),
        coupon=p.term("coupon", p.num, lo=0, hi=30),
        accrual_type=p.term("accrual_type", p.choice, S.ACCRUAL_TYPES),
        issue_date=p.term("issue_date", p.day),
        rating=p.term("rating", p.text), sector=p.term("sector", p.text), state=p.term("state", p.text),
        payment_frequency=p.term("payment_frequency", lambda c, required: _int_choice(p, c, S.PAYMENT_FREQUENCIES)),
        day_count=p.term("day_count", p.choice, S.DAY_COUNTS),
        vendor_yield=p.term("vendor_yield", p.num, lo=-20, hi=100),
        product_type=p.term("product_type", p.choice, S.PRODUCT_TYPES),
        factor=p.term("factor", p.num, lo=0, hi=1.5),
        factor_date=p.term("factor_date", p.day),
        payment_delay_days=p.term("payment_delay_days",
                                  lambda c, required: _int_choice(p, c, set(range(0, 121)))),
        rate_type=p.term("rate_type", p.choice, S.RATE_TYPES),
        asset_class=asset_class, source_role=role, source_row=p.n,
        states=dict(p.states), raw=dict(p.raws),
    )
    if rec["maturity_date"] and rec["issue_date"] and rec["maturity_date"] <= rec["issue_date"]:
        p._err("maturity_date", "maturity_date must be after issue_date")
    if len(p.errors) > before:
        return None
    if rec["coupon"] is not None:
        rec["coupon"] = rec["coupon"] / 100.0           # percent -> decimal; 0 stays 0, None stays None
    if rec["vendor_yield"] is not None:
        rec["vendor_yield"] = rec["vendor_yield"] / 100.0
    if rec["day_count"]:
        rec["day_count"] = rec["day_count"].upper()
    if rec["state"]:
        rec["state"] = rec["state"].upper()
    return SecurityRecord(**rec)


def _dupes(result: ParseResult, keys: list[tuple[int, str]]):
    seen: dict[str, int] = {}
    for n, k in keys:
        if k in seen:
            result.errors.append(RowError(n, "cusip", f"duplicate of row {seen[k]}: {k}"))
        else:
            seen[k] = n


def parse_holdings(text: str, vendor: str = "FundAccounting") -> ParseResult:
    res = ParseResult("holdings", hashlib.sha256(text.encode()).hexdigest(), 0)
    rows, errs = _read(text, S.HOLDINGS_REQUIRED, S.HOLDINGS_OPTIONAL)
    res.errors += errs
    res.row_count = len(rows)
    keys = []
    for n, row in enumerate(rows, start=1):
        p = _RowParser(row, n, res.errors)
        rec = _security(p, vendor, "book")
        par = p.num("par", lo=0.01)
        acq = p.day("acquisition_date", required=False)
        portfolio = p.text("portfolio", required=False) or "DEFAULT"
        if rec is None or par is None:
            continue
        res.records.append(rec)
        res.positions.append(Position(portfolio, rec.cusip, par, acq))
        keys.append((n, f"{portfolio}/{rec.cusip}"))
    _dupes(res, keys)
    if not res.errors and not rows:
        res.errors.append(RowError(0, None, "no data rows"))
    return res


def parse_vendor(text: str, vendor: str) -> ParseResult:
    res = ParseResult("vendor_secondary", hashlib.sha256(text.encode()).hexdigest(), 0)
    rows, errs = _read(text, S.VENDOR_REQUIRED, S.VENDOR_OPTIONAL)
    res.errors += errs
    res.row_count = len(rows)
    keys = []
    for n, row in enumerate(rows, start=1):
        rec = _security(_RowParser(row, n, res.errors), vendor, "vendor")
        if rec is not None:
            res.records.append(rec)
            keys.append((n, rec.cusip))
    _dupes(res, keys)
    return res


def parse_price_history(text: str) -> ParseResult:
    res = ParseResult("price_history", hashlib.sha256(text.encode()).hexdigest(), 0)
    rows, errs = _read(text, S.HISTORY_REQUIRED, S.HISTORY_OPTIONAL)
    res.errors += errs
    res.row_count = len(rows)
    for n, row in enumerate(rows, start=1):
        p = _RowParser(row, n, res.errors)
        before = len(res.errors)
        c = p.cusip()
        d = p.day("price_date")
        px = p.num("price", lo=0.0001, hi=10000)
        conv = p.choice("price_convention", S.PRICE_CONVENTIONS, required=False) or "clean"
        if len(res.errors) == before:
            res.prices.append(PricePoint(c, d, px, conv))
    return res
