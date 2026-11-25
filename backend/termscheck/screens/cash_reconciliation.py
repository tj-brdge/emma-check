"""Cash reconciliation: interest cash received vs income booked for the same accrual periods.

This is the highest-confidence screen: cash is observed, not modelled. For each interest
receipt the security's plugin identifies the accrual period it pays and the face outstanding,
which gives the rate the cash implies. Booked income for the period comes from the ledger's
``booked_income`` when supplied, otherwise from the book-of-record terms (a BLANK book coupon
can book nothing - stated explicitly in the flag, never treated as a zero value).
"""
from __future__ import annotations

from datetime import timedelta

from termscheck.core.plugin import all_plugins
from termscheck.core.records import Flag, LedgerEntry, ScreenInput
from termscheck.screens.base import ScreenContext, clamp_severity
from termscheck.screens.config import ScreenConfig


class CashReconciliationScreen:
    confidence = 0.95
    rule = "cash_reconciliation"

    def run(self, data: ScreenInput, config: ScreenConfig, ctx: ScreenContext) -> list[Flag]:
        plugins = all_plugins()
        start = data.as_of - timedelta(days=config.cash_lookback_days)
        by_pos: dict[tuple[str, str], list[LedgerEntry]] = {}
        for e in data.ledger:
            if e.kind == "interest" and start <= e.entry_date <= data.as_of:
                by_pos.setdefault((e.portfolio, e.cusip), []).append(e)
        positions = {(p.portfolio, p.cusip): p for p in data.positions}
        flags: list[Flag] = []
        for key, entries in sorted(by_pos.items()):
            pos, rec = positions.get(key), data.primary.get(key[1])
            if pos is None or rec is None:
                continue
            plugin = plugins.get(rec.asset_class)
            period_fn = getattr(plugin, "cash_period", None)
            if period_fn is None:
                continue
            rows, assumptions = [], set()
            for e in sorted(entries, key=lambda x: x.entry_date):
                per = period_fn(rec, pos, e, data)
                assumptions.update(per.assumptions)
                implied = e.cash / (per.face * per.years) if per.face and per.years else None
                if e.booked_income is not None:
                    booked, basis = e.booked_income, "ledger"
                elif rec.coupon is None:
                    booked, basis = 0.0, "book coupon BLANK: nothing bookable"
                else:
                    booked, basis = rec.coupon * per.face * per.years, "book terms"
                rows.append({"date": e.entry_date.isoformat(), "cash": e.cash, "booked": booked, "basis": basis,
                             "period_start": per.start.isoformat(), "period_end": per.end.isoformat(),
                             "face": per.face, "implied_rate": implied})
            cash = sum(r["cash"] for r in rows)
            booked = sum(r["booked"] for r in rows)
            if cash <= 0:
                continue
            rates = [r["implied_rate"] for r in rows if r["implied_rate"] is not None]
            implied = sum(rates) / len(rates) if rates else None
            book_rate = rec.coupon
            gap_bp = None if implied is None or book_rate is None else (implied - book_rate) * 1e4
            short = (cash - booked) / cash
            computed = {"receipts": rows, "cash_total": cash, "booked_total": booked, "shortfall_pct": short,
                        "implied_rate": implied, "book_rate": "BLANK" if book_rate is None and rec.is_blank("coupon")
                        else book_rate, "rate_gap_bp": gap_bp, "assumptions": sorted(assumptions)}
            inputs = {"portfolio": pos.portfolio, "par": pos.par, "receipts": len(rows)}
            rate_txt = "n/a" if implied is None else f"{implied:.3%}"
            if booked == 0 or (short > config.cash_shortfall_pct
                               and (gap_bp is None or abs(gap_bp) > config.cash_rate_gap_bp)):
                sev = clamp_severity(80 + 20 * min(1.0, short))
                what = "no income booked" if booked == 0 else f"booked ${booked:,.2f} ({short:.0%} short)"
                flags.append(Flag(self.rule, cusip_of(key), sev,
                                  f"{len(rows)} interest receipts totalling ${cash:,.2f} but {what}; cash implies a "
                                  f"{rate_txt} rate vs book coupon {computed['book_rate'] if book_rate is None else f'{book_rate:.3%}'}.",
                                  inputs, computed | {"direction": "understated"}))
            elif -short > config.cash_overbooked_pct:
                flags.append(Flag(self.rule, cusip_of(key), clamp_severity(55 + 30 * min(1.0, -short)),
                                  f"Booked ${booked:,.2f} vs interest cash ${cash:,.2f} ({-short:.0%} over); cash implies "
                                  f"{rate_txt}.", inputs, computed | {"direction": "overstated"}))
        return flags


def cusip_of(key: tuple[str, str]) -> str:
    return key[1]
