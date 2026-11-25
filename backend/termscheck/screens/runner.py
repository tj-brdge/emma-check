"""Run shared screens on every security and each plugin's screens on its own asset class."""
from __future__ import annotations

from dataclasses import replace

from termscheck.core.plugin import all_plugins
from termscheck.core.records import ScreenInput, ScreenResult
from termscheck.screens.base import Screen, ScreenContext
from termscheck.screens.config import ScreenConfig
from termscheck.screens.cash_reconciliation import CashReconciliationScreen
from termscheck.screens.frequency_contradiction import FrequencyContradictionScreen
from termscheck.screens.null_vs_zero import NullVsZeroScreen
from termscheck.screens.vendor_disagreement import VendorDisagreementScreen

SHARED_SCREENS: tuple[Screen, ...] = (CashReconciliationScreen(), NullVsZeroScreen(),
                                      FrequencyContradictionScreen(), VendorDisagreementScreen())


def run_screens(data: ScreenInput, config: ScreenConfig | None = None) -> ScreenResult:
    config = config or ScreenConfig()
    held = {p.cusip for p in data.positions} or set(data.primary)
    data = ScreenInput(as_of=data.as_of, positions=data.positions,
                       primary={c: r for c, r in data.primary.items() if c in held},
                       secondary=data.secondary, history=data.history, vendors=data.vendors,
                       ledger=data.ledger, observations=data.observations)
    ctx = ScreenContext(implied_yields={})
    subsets: dict[str, ScreenInput] = {}
    for key, plugin in all_plugins().items():
        sub = ScreenInput(as_of=data.as_of, positions=[p for p in data.positions
                                                        if data.primary.get(p.cusip) and data.primary[p.cusip].asset_class == key],
                          primary={c: r for c, r in data.primary.items() if r.asset_class == key},
                          secondary=data.secondary, history=data.history, vendors=data.vendors,
                          ledger=[e for e in data.ledger if data.primary.get(e.cusip)
                                  and data.primary[e.cusip].asset_class == key],
                          observations=data.observations)
        if sub.primary:
            subsets[key] = sub
            hook = getattr(plugin, "prepare_context", None)   # optional: plugin-computed shared values
            if hook:
                hook(sub, ctx)
    def stamped(screen, flags):
        return [replace(f, confidence=getattr(screen, "confidence", 0.5)) for f in flags]

    flags = [f for s in SHARED_SCREENS for f in stamped(s, s.run(data, config, ctx))]
    for key, sub in subsets.items():
        flags += [f for s in all_plugins()[key].screens for f in stamped(s, s.run(sub, config, ctx))]
    flags.sort(key=lambda f: (-f.priority, -f.severity, f.cusip, f.rule))
    return ScreenResult(flags=flags, implied_yields=ctx.implied_yields, config=config.as_dict())
