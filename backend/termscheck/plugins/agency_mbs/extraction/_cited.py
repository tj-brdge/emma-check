"""Cited field types for the MBS schema (same shape as the muni schema, kept plugin-local)."""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class _Cited(BaseModel):
    page: int | None = Field(description="1-based page number from the <page number=...> tag")
    excerpt: str | None = Field(description="Verbatim text copied from that page (<= 40 words)")


class CitedText(_Cited):
    value: str | None


class CitedNumber(_Cited):
    value: float | None


class CitedInt(_Cited):
    value: int | None


class CitedDate(_Cited):
    value: str | None = Field(description="ISO date YYYY-MM-DD")


class DayCountValue(StrEnum):
    thirty_360 = "30/360"
    act_360 = "ACT/360"
    act_365 = "ACT/365"
    act_act = "ACT/ACT"


class CitedDayCount(_Cited):
    value: DayCountValue | None
