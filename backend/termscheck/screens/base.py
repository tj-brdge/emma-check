"""Screen protocol. A screen is a pure function of (input, config, shared context) -> flags."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from termscheck.screens.config import ScreenConfig
from termscheck.core.records import Flag, ScreenInput


@dataclass
class ScreenContext:
    implied_yields: dict[str, float | None]


class Screen(Protocol):
    rule: str

    def run(self, data: ScreenInput, config: ScreenConfig, ctx: ScreenContext) -> list[Flag]: ...


def clamp_severity(x: float) -> int:
    return int(max(0, min(100, round(x))))
