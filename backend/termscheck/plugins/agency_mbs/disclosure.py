"""Pool disclosure data files -> monthly factor / net coupon observations. Deterministic (no LLM).

Real Freddie Mac disclosure layouts were not available, so columns are matched through a
configurable alias mapping (DEFAULT_MAPPING). Supporting a real file means adding its column
names here (or passing a mapping), not changing code. Blank values stay None and every value
keeps a ``file:row:column`` locator so a reviewer can trace it.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date

from termscheck.core.identifiers import is_valid_cusip
from termscheck.core.records import PeriodObservation

DEFAULT_MAPPING: dict[str, tuple[str, ...]] = {
    "cusip": ("cusip", "security_identifier", "security_cusip"),
    "month": ("factor_month", "period", "reporting_period", "as_of_month", "factor_date", "month"),
    "factor": ("factor", "pool_factor", "current_factor", "security_factor"),
    "net_coupon": ("net_coupon", "current_coupon", "net_rate", "security_rate", "pass_through_rate"),
    "wac": ("wac", "weighted_average_coupon", "current_wac"),
}
NULLS = {"", "na", "n/a", "#n/a", "null", "none", "-", "--"}


@dataclass
class DisclosureRow:
    cusip: str
    obs: PeriodObservation
    row_no: int
    raw: dict[str, str]


@dataclass
class DisclosureParse:
    rows: list[DisclosureRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    columns: dict[str, str] = field(default_factory=dict)   # canonical -> header used

    def by_cusip(self) -> dict[str, list[PeriodObservation]]:
        out: dict[str, list[PeriodObservation]] = {}
        for r in self.rows:
            out.setdefault(r.cusip, []).append(r.obs)
        for v in out.values():
            v.sort(key=lambda o: o.month)
        return out


def _month(s: str) -> date | None:
    s = s.strip()
    for pat, fn in ((r"^(\d{4})-(\d{2})(-\d{2})?$", lambda m: (int(m[1]), int(m[2]))),
                    (r"^(\d{4})(\d{2})$", lambda m: (int(m[1]), int(m[2]))),
                    (r"^(\d{1,2})/(\d{4})$", lambda m: (int(m[2]), int(m[1]))),
                    (r"^(\d{1,2})/\d{1,2}/(\d{4})$", lambda m: (int(m[2]), int(m[1])))):
        m = re.match(pat, s)
        if m:
            y, mo = fn(m)
            if 1 <= mo <= 12:
                return date(y, mo, 1)
    return None


def parse_pool_disclosure(filename: str, text: str, mapping: dict[str, tuple[str, ...]] | None = None
                          ) -> DisclosureParse:
    mapping = mapping or DEFAULT_MAPPING
    out = DisclosureParse()
    if text.startswith("﻿"):
        text = text[1:]
    sample = text[:2048]
    delim = "|" if sample.count("|") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    headers = {("" if h is None else h).strip().lower().replace(" ", "_"): h for h in (reader.fieldnames or [])}
    for canon, aliases in mapping.items():
        for a in aliases:
            if a in headers:
                out.columns[canon] = headers[a]
                break
    for need in ("cusip", "month", "factor"):
        if need not in out.columns:
            out.errors.append(f"required column for {need!r} not found (accepted: {', '.join(mapping[need])})")
    if out.errors:
        return out
    for n, row in enumerate(reader, start=1):
        def cell(canon):
            h = out.columns.get(canon)
            v = None if h is None else row.get(h)
            return None if v is None or v.strip().lower() in NULLS else v.strip()

        cusip = (cell("cusip") or "").upper()
        if not is_valid_cusip(cusip):
            out.errors.append(f"row {n}: invalid CUSIP {cusip!r}")
            continue
        month = _month(cell("month") or "")
        if month is None:
            out.errors.append(f"row {n}: unrecognised month {cell('month')!r}")
            continue
        vals = {}
        for k in ("factor", "net_coupon", "wac"):
            c = cell(k)
            if c is None:
                vals[k] = None
                continue
            try:
                vals[k] = float(c.rstrip("%"))
            except ValueError:
                out.errors.append(f"row {n}: {k} not a number: {c!r}")
                vals[k] = None
        if vals["factor"] is not None and not 0 <= vals["factor"] <= 1.5:
            out.errors.append(f"row {n}: factor {vals['factor']} out of range")
        loc = f"{filename}:row {n}:{out.columns.get('net_coupon', out.columns['factor'])}"
        out.rows.append(DisclosureRow(cusip, PeriodObservation(
            month, vals["factor"], None if vals["net_coupon"] is None else vals["net_coupon"] / 100.0, loc),
            n, {k: v for k, v in row.items() if k is not None}))
    if not out.rows and not out.errors:
        out.errors.append("no data rows")
    return out
