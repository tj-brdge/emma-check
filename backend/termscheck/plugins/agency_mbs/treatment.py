"""Correct income treatment for an agency MBS position vs. what the book of record accrues.
Pure: inputs are document terms (with disclosure observations), the book record and the ledger."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from termscheck.core.daycount import add_months, days_30_360
from termscheck.core.records import LedgerEntry, Position, SecurityRecord
from termscheck.plugins.agency_mbs.bondmath import (MBSTerms, accrual_month_paid_on, implied_rate,
                                                    interest_receivable, month_row, month_start, payment_date,
                                                    settlement_accrued)

TREATMENT_VERSION = "mbs-1.0.0"


@dataclass
class MBSTreatment:
    as_of: date
    window_start: date
    months: int
    current_factor: float
    current_face: float
    current_rate: float | None
    book_rate: float | None             # None = BLANK / not supplied in the book
    book_factor: float | None
    receivable_document: float | None
    receivable_book: float
    unbooked_window_usd: float           # (document - booked) over the window, incl. current month to date
    run_rate_document: float | None      # next 12 months on current face at the current rate
    run_rate_book: float
    run_rate_gap_usd: float
    cash_window: float
    expected_cash_window: float | None
    cash_implied_rate: float | None
    accrued_per_100: float | None        # settlement accrued per 100 current face
    clean_per_100: float
    full_per_100: float
    schedule: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def compute_mbs_treatment(terms: MBSTerms, rec: SecurityRecord, pos: Position, as_of: date,
                          ledger: list[LedgerEntry] | None = None) -> MBSTreatment:
    notes: list[str] = []
    led = sorted((e for e in (ledger or []) if e.kind == "interest" and e.portfolio == pos.portfolio
                  and e.cusip == pos.cusip and e.entry_date <= as_of), key=lambda e: e.entry_date)
    delay = terms.payment_delay_days
    cash_by_month: dict[date, float] = {}
    for e in led:
        m = accrual_month_paid_on(e.entry_date, delay)
        cash_by_month[m] = cash_by_month.get(m, 0.0) + e.cash

    if pos.acquisition_date:
        start = month_start(pos.acquisition_date)
        why = "acquisition date"
    elif cash_by_month:
        start = min(cash_by_month)
        why = "first interest receipt in the ledger"
    else:
        start = month_start(as_of)
        why = "as-of month (no acquisition date or ledger)"
    start = max(start, month_start(terms.issue_date))
    notes.append(f"Income window starts {start:%Y-%m} ({why}).")

    book_rate = rec.coupon
    if book_rate is None:
        notes.append("Book coupon is BLANK (not zero): no interest can be accrued from it; booked income is nil.")
    book_factor = rec.factor

    rows, unbooked = [], 0.0
    m, cur = start, month_start(as_of)
    while m <= cur:
        r = month_row(terms, pos.par, m, fallback_factor=rec.factor)
        notes += [a for a in r.assumptions if a not in notes]
        frac = 1.0 if m < cur else min(days_30_360(m, as_of + timedelta(days=1)), 30) / 30.0
        doc_int = None if r.interest is None else r.interest * frac
        bf = book_factor if book_factor is not None else r.factor
        booked = 0.0 if book_rate is None else pos.par * bf * book_rate / 12.0 * frac
        cash = cash_by_month.get(m)
        if doc_int is not None:
            unbooked += doc_int - booked
        rows.append({"date": m.isoformat(), "payment_date": payment_date(m, delay).isoformat(), "factor": r.factor,
                     "face": r.face, "rate": r.rate, "interest": doc_int, "booked": booked, "cash": cash,
                     "cash_minus_expected": None if cash is None or doc_int is None or frac < 1 else cash - doc_int})
        m = add_months(m, 1)

    cur_row = month_row(terms, pos.par, as_of, fallback_factor=rec.factor)
    rec_doc, _, n2 = interest_receivable(terms, pos.par, as_of, fallback_factor=rec.factor)
    notes += [a for a in n2 if a not in notes]
    # Book receivable: same delay structure, book rate and book factor.
    rec_book = 0.0
    if book_rate is not None:
        book_delay = rec.payment_delay_days if rec.payment_delay_days is not None else delay
        bf = book_factor if book_factor is not None else cur_row.factor
        k = add_months(month_start(as_of), -1)
        while payment_date(k, book_delay) > as_of:
            rec_book += pos.par * bf * book_rate / 12.0
            k = add_months(k, -1)
        rec_book += pos.par * bf * book_rate * min(days_30_360(month_start(as_of), as_of + timedelta(days=1)), 30) / 360.0
    rr_doc = None if cur_row.rate is None else cur_row.face * cur_row.rate
    bf_now = book_factor if book_factor is not None else cur_row.factor
    rr_book = 0.0 if book_rate is None else pos.par * bf_now * book_rate
    cash_total = sum(cash_by_month.values())
    full_months = [r for r in rows if r["cash"] is not None and r["cash_minus_expected"] is not None]
    expected = sum(r["interest"] for r in full_months) if full_months else None
    implied = None
    if full_months:
        implied = sum(implied_rate(r["cash"], pos.par, r["factor"]) for r in full_months) / len(full_months)
    acc = settlement_accrued(terms, pos.par, as_of, fallback_factor=rec.factor)
    acc100 = None if acc is None else acc / cur_row.face * 100.0
    conv = (rec.price_convention or "").lower()
    if conv == "dirty":
        full = rec.price
        clean = rec.price - acc100 if acc100 is not None else rec.price
    else:
        clean = rec.price
        full = rec.price + (acc100 if acc100 is not None else 0.0)
        if not conv:
            notes.append("Price convention BLANK; agency MBS quotes are clean, so the price is treated as clean.")
    return MBSTreatment(as_of, start, len(rows), cur_row.factor, cur_row.face, cur_row.rate, book_rate, book_factor,
                        rec_doc, rec_book, unbooked, rr_doc, rr_book,
                        (rr_doc - rr_book) if rr_doc is not None else 0.0, cash_total, expected, implied, acc100,
                        clean, full, rows, notes)
