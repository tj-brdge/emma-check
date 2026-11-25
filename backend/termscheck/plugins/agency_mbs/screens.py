"""Agency MBS screens that compare the book of record with the pool disclosure (deterministic)."""
from __future__ import annotations

from termscheck.core.records import Flag, ScreenInput
from termscheck.screens.base import ScreenContext, clamp_severity
from termscheck.screens.config import ScreenConfig


def _latest(obs, as_of, attr):
    cands = [o for o in obs if o.month <= as_of.replace(day=1) and getattr(o, attr) is not None]
    return max(cands, key=lambda o: o.month) if cands else None


class FactorMismatchScreen:
    confidence = 0.8
    rule = "factor_mismatch"

    def run(self, data: ScreenInput, config: ScreenConfig, ctx: ScreenContext) -> list[Flag]:
        flags = []
        for cusip, rec in data.primary.items():
            obs = data.observations.get(cusip, [])
            disc = _latest(obs, data.as_of, "factor")
            if disc is None:
                continue
            if rec.factor is None:
                flags.append(Flag(self.rule, cusip, 45, f"Book factor {'BLANK' if rec.is_blank('factor') else 'not supplied'}; "
                                  f"disclosure shows {disc.factor:.8f} for {disc.month:%Y-%m}.",
                                  {"book_factor": None, "book_factor_date": None},
                                  {"disclosed_factor": disc.factor, "disclosed_month": disc.month.isoformat(),
                                   "locator": disc.source}))
                continue
            rel = abs(rec.factor - disc.factor) / disc.factor if disc.factor else 1.0
            if rel > 0.0005:
                stale = rec.factor_date is not None and rec.factor_date.replace(day=1) < disc.month
                flags.append(Flag(self.rule, cusip, clamp_severity(40 + 300 * rel),
                                  f"Book factor {rec.factor:.8f}{' (as of ' + rec.factor_date.strftime('%Y-%m') + ')' if rec.factor_date else ''} "
                                  f"vs disclosed {disc.factor:.8f} for {disc.month:%Y-%m}"
                                  f"{': stale factor' if stale else ''} ({rel:.1%} of face).",
                                  {"book_factor": rec.factor, "book_factor_date": rec.factor_date and rec.factor_date.isoformat()},
                                  {"disclosed_factor": disc.factor, "disclosed_month": disc.month.isoformat(),
                                   "relative_difference": rel, "stale": stale, "locator": f"{disc.source} · factor"}))
        return flags


class RateVsDisclosureScreen:
    confidence = 0.85
    rule = "rate_vs_disclosure"
    tolerance_bp = 5.0

    def run(self, data: ScreenInput, config: ScreenConfig, ctx: ScreenContext) -> list[Flag]:
        flags = []
        for cusip, rec in data.primary.items():
            disc = _latest(data.observations.get(cusip, []), data.as_of, "net_coupon")
            if disc is None:
                continue
            book = rec.coupon
            book_txt = ("BLANK" if rec.is_blank("coupon") else "not supplied") if book is None else f"{book:.3%}"
            gap = None if book is None else (disc.net_coupon - book) * 1e4
            if gap is None or abs(gap) > self.tolerance_bp:
                sev = 95 if book is None or book == 0 else clamp_severity(45 + abs(gap) / 4)
                flags.append(Flag(self.rule, cusip, sev,
                                  f"Book coupon {book_txt} vs disclosed net coupon {disc.net_coupon:.3%} for "
                                  f"{disc.month:%Y-%m}" + ("" if gap is None else f" ({gap:+.0f} bp)") + ".",
                                  {"book_coupon": book_txt if book is None else book, "rate_type": rec.rate_type},
                                  {"disclosed_net_coupon": disc.net_coupon, "disclosed_month": disc.month.isoformat(),
                                   "gap_bp": gap, "locator": f"{disc.source} · net coupon"}))
        return flags
