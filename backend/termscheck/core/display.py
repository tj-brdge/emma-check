"""Rendering helpers that keep blank distinct from zero in every user-facing string."""
from __future__ import annotations

from termscheck.core.records import BLANK, SecurityRecord


def show(rec: SecurityRecord, name: str, fmt: str = "{}") -> str:
    v = getattr(rec, name)
    if v is None:
        return "BLANK" if rec.state_of(name) == BLANK else "not supplied"
    return fmt.format(v)


def pct(rec: SecurityRecord, name: str, digits: int = 3) -> str:
    return show(rec, name, "{:." + str(digits) + "%}")
