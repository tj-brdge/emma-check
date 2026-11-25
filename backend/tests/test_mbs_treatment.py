"""MBS treatment and finding on the 'blank coupon became zero' pattern (hand-calculated)."""
from datetime import date

import pytest

from termscheck.core.records import BLANK, LedgerEntry, PeriodObservation, Position, SecurityRecord
from termscheck.plugins.agency_mbs.findings import build_mbs_finding

D = date
C = "3137MBS09"
OBS = [PeriodObservation(D(2026, 9, 1), 0.87, 0.04810, "pool.csv:row 1"),
       PeriodObservation(D(2026, 10, 1), 0.86, 0.04795, "pool.csv:row 2"),
       PeriodObservation(D(2026, 11, 1), 0.85, 0.04773, "pool.csv:row 3")]
TERMS = {"rate_type": "wac", "net_coupon": 0.04810, "payment_delay_days": 45, "issue_date": "2021-01-01",
         "maturity_date": "2051-01-01", "day_count": "30/360", "reset_rule": "WAC less 0.65%"}
# Sep interest 870,000 x 4.810%/12 = 3,487.25 (paid Oct 15); Oct 860,000 x 4.795%/12 = 3,436.4167 (paid Nov 16)
LEDGER = [LedgerEntry("MBS-01", C, D(2026, 10, 15), 3487.25, "interest"),
          LedgerEntry("MBS-01", C, D(2026, 11, 16), 3436.42, "interest")]


def book(**kw):
    base = dict(vendor="FundAccounting", cusip=C, description="FHLMC pool", price=101.25, price_convention="clean",
                coupon=0.0, accrual_type="fixed", maturity_date=D(2051, 1, 1), issue_date=D(2021, 1, 1), rating=None,
                sector=None, state=None, payment_frequency=12, asset_class="agency_mbs", factor=0.85,
                factor_date=D(2026, 11, 1), payment_delay_days=45, rate_type="fixed", source_role="book")
    base.update(kw)
    return SecurityRecord(**base)


def build(rec, ledger=LEDGER, pos=Position("MBS-01", C, 1_000_000.0), sources=None):
    return build_mbs_finding(rec, [pos], TERMS, D(2026, 11, 30), ledger=ledger, observations=OBS,
                             sources=sources or [rec])


def test_zero_book_coupon_unbooked_over_window():
    f = build(book())
    t = f.treatment
    # Window Sep..Nov (first receipt pays Sep). Sep 3,487.25 + Oct 3,436.416667 + Nov 850,000 x 4.773%/12 = 3,380.875
    assert t.window_start == D(2026, 9, 1) and t.months == 3
    assert f.income_impact_usd == pytest.approx(10_304.541667, abs=1e-4)
    assert t.receivable_document == pytest.approx(3_380.875) and t.receivable_book == 0.0
    # cash-implied: Sep 3,487.25 x 12 / 870,000 = 4.81%; Oct 3,436.42 x 12 / 860,000 = 4.79500%
    assert t.cash_implied_rate == pytest.approx((0.0481 + 3436.42 * 12 / 860_000) / 2, abs=1e-9)
    assert t.current_rate == 0.04773 and t.current_face == pytest.approx(850_000)
    # run-rate: 850,000 x 4.773% = 40,570.50 a year vs 0 booked
    assert f.run_rate_gap_usd == pytest.approx(40_570.5)
    assert "confirmed by cash" in f.headline and "0.000%" in f.headline
    row = f.schedule[0]
    assert row["cash"] == 3487.25 and row["cash_minus_expected"] == pytest.approx(0.0)


def test_blank_book_coupon_is_reported_as_blank_not_zero():
    rec = book(coupon=None, states={"coupon": BLANK})
    vendor = book(vendor="FactSet", coupon=None, states={"coupon": BLANK}, source_role="vendor")
    f = build(rec, sources=[rec, vendor])
    assert "BLANK" in f.headline and "0.000%" not in f.headline
    assert "Book coupon is BLANK (not zero)" in " ".join(f.notes)
    assert "FactSet: coupon BLANK" in f.vendor_says
    assert f.income_impact_usd == pytest.approx(10_304.541667, abs=1e-4)


def test_correct_book_has_small_or_no_impact_and_stale_factor_overstates():
    ok = build(book(coupon=0.04773, rate_type="wac"))
    # Book at the current rate on the current factor still differs in Sep/Oct (different rates/factors).
    assert abs(ok.income_impact_usd) < 200
    stale = build(book(coupon=0.04773, factor=1.0))          # book uses factor 1.0 instead of 0.85-0.87
    assert stale.income_impact_usd < -1_000 and "Overbooked" in stale.headline


def test_no_ledger_uses_as_of_month_window():
    f = build(book(), ledger=[])
    assert f.treatment.months == 1 and f.income_impact_usd == pytest.approx(3_380.875)
    assert f.treatment.cash_implied_rate is None
