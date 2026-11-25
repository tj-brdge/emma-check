"""Asset-class-neutral finding draft produced by a plugin and persisted by the service layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class Metric:
    label: str
    value: float | None
    fmt: str = "num4"          # num4 | num2 | pct | usd
    emphasis: bool = False


@dataclass
class PositionResult:
    portfolio: str
    par: float
    unbooked_income_usd: float
    run_rate_gap_usd: float
    unbooked_window_usd: float | None
    outputs: dict[str, Any]    # full plugin computation outputs (JSON-able)


@dataclass
class FindingDraft:
    cusip: str
    asset_class: str
    description: str
    as_of: date
    income_impact_usd: float
    run_rate_gap_usd: float
    headline: str
    vendor_says: str
    document_says: str
    correct_treatment: str
    impact: str
    comparison: list[dict[str, Any]]
    positions: list[PositionResult]
    metrics: list[Metric]
    schedule: list[dict[str, Any]] = field(default_factory=list)
    schedule_label: str = ""
    notes: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    treatment: Any = None       # plugin-specific detail object (per-unit treatment)
