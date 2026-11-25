"""Null vs zero: a term left blank by one source and reported as 0 by another.

This is the signature of a feed that turned "unknown" into "zero" somewhere downstream. A blank
on its own (no zero anywhere) is reported at low severity, for visibility.
"""
from __future__ import annotations

from termscheck.core.records import Flag, ScreenInput
from termscheck.screens.base import ScreenContext, clamp_severity
from termscheck.screens.config import ScreenConfig

FIELDS = {"coupon": 90, "payment_frequency": 60, "factor": 70, "payment_delay_days": 50, "vendor_yield": 40}


class NullVsZeroScreen:
    confidence = 0.9
    rule = "null_vs_zero"

    def run(self, data: ScreenInput, config: ScreenConfig, ctx: ScreenContext) -> list[Flag]:
        flags: list[Flag] = []
        for cusip in data.primary:
            recs = data.sources_for(cusip)
            conflicts, blanks_only = {}, {}
            for name, weight in FIELDS.items():
                blank = [r.vendor for r in recs if r.is_blank(name)]
                zero = [r.vendor for r in recs if r.is_zero(name)]
                if blank and zero:
                    conflicts[name] = {"blank_in": blank, "zero_in": zero,
                                       "values": {r.vendor: _show(r, name) for r in recs},
                                       "raw": {r.vendor: r.raw.get(name) for r in recs if name in r.raw}}
                elif blank and name in config.blank_alone_fields:
                    blanks_only[name] = {"blank_in": blank, "values": {r.vendor: _show(r, name) for r in recs}}
            if conflicts:
                sev = clamp_severity(max(FIELDS[k] for k in conflicts) + 5 * (len(conflicts) - 1))
                msg = "; ".join(f"{k} BLANK in {', '.join(v['blank_in'])} but 0 in {', '.join(v['zero_in'])}"
                                for k, v in conflicts.items())
                flags.append(Flag(self.rule, cusip, sev, msg + " - a blank became zero downstream.",
                                  {"sources": [r.vendor for r in recs]},
                                  {"conflicts": conflicts, "blank_only": blanks_only}))
            elif blanks_only:
                flags.append(Flag(self.rule, cusip, config.blank_alone_severity,
                                  "Blank (not zero): " + "; ".join(f"{k} in {', '.join(v['blank_in'])}"
                                                                   for k, v in blanks_only.items()) + ".",
                                  {"sources": [r.vendor for r in recs]},
                                  {"conflicts": {}, "blank_only": blanks_only}))
        return flags


def _show(rec, name):
    v = getattr(rec, name)
    return "BLANK" if v is None and rec.is_blank(name) else v
