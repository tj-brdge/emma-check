from dataclasses import replace
from datetime import date

import pytest

from termscheck.core.records import BLANK, LedgerEntry, Position, ScreenInput, SecurityRecord
from termscheck.screens import ScreenConfig, run_screens

AS_OF = date(2026, 11, 30)


def rec(vendor="FundAccounting", role="book", **kw) -> SecurityRecord:
    base = dict(vendor=vendor, cusip="TEST00001", description="t", price=100.0, price_convention="clean",
                coupon=0.05, accrual_type="fixed", maturity_date=date(2036, 6, 1), issue_date=date(2016, 6, 1),
                rating="AA", sector="General Obligation", state="NY", payment_frequency=2, day_count="30/360",
                source_role=role)
    base.update(kw)
    return SecurityRecord(**base)


def blank(r: SecurityRecord, *names) -> SecurityRecord:
    return replace(r, **{n: None for n in names}, states={**r.states, **{n: BLANK for n in names}},
                   raw={**r.raw, **{n: "" for n in names}})


def run(book, vendors=(), ledger=(), config=None, par=1_000_000.0):
    data = ScreenInput(AS_OF, [Position("P", book.cusip, par)], {book.cusip: book},
                       vendors={v.vendor: {v.cusip: v} for v in vendors}, ledger=list(ledger))
    return run_screens(data, config)


def rules(res, rule):
    return [f for f in res.flags if f.rule == rule]


# ---------------------------------------------------------------- null vs zero
def test_blank_in_one_source_zero_in_another():
    res = run(rec(coupon=0.0), [blank(rec("FactSet", "vendor"), "coupon")])
    (f,) = rules(res, "null_vs_zero")
    assert f.severity >= 90 and f.confidence == 0.9
    c = f.computed["conflicts"]["coupon"]
    assert c["blank_in"] == ["FactSet"] and c["zero_in"] == ["FundAccounting"]
    assert c["values"] == {"FundAccounting": 0.0, "FactSet": "BLANK"} and c["raw"]["FactSet"] == ""


def test_blank_alone_is_low_severity_and_zero_alone_is_not_null_vs_zero():
    f = rules(run(blank(rec(), "coupon")), "null_vs_zero")
    assert len(f) == 1 and f[0].severity == ScreenConfig().blank_alone_severity
    assert not rules(run(rec(coupon=0.0), [rec("FactSet", "vendor", coupon=0.0)]), "null_vs_zero")


# ---------------------------------------------------------------- frequency contradiction
@pytest.mark.parametrize("kw,expected", [
    (dict(coupon=None, states={"coupon": BLANK}, payment_frequency=12), 70),
    (dict(coupon=0.0, payment_frequency=12, accrual_type="fixed"), 70),
    (dict(coupon=0.0, payment_frequency=2, accrual_type="zero"), 25),        # labelled non-paying: low
    (dict(coupon=0.0, payment_frequency=12, accrual_type="fixed", product_type="po"), 25),
    (dict(coupon=0.0, payment_frequency=0, accrual_type="zero"), None),
    (dict(coupon=0.0, payment_frequency=None, accrual_type="zero"), None),
    (dict(coupon=0.05, payment_frequency=2), None),
])
def test_frequency_contradiction(kw, expected):
    f = rules(run(rec(**kw)), "frequency_contradiction")
    assert (f[0].severity if f else None) == expected


# ---------------------------------------------------------------- cash reconciliation (muni path)
COUPON_DATES = [date(2025, 12, 1), date(2026, 6, 1)]


def receipts(amount=25_000.0, booked=None):
    # 5% on 1,000,000 semiannual = 25,000 per coupon
    return [LedgerEntry("P", "TEST00001", d, amount, "interest", booked) for d in COUPON_DATES]


def test_cash_matches_book_no_flag():
    assert not rules(run(rec(), ledger=receipts()), "cash_reconciliation")


def test_cash_with_blank_book_coupon_is_flagged_highest_priority():
    res = run(blank(rec(), "coupon"), ledger=receipts())
    (f,) = rules(res, "cash_reconciliation")
    assert f.severity == 100 and f.confidence == 0.95
    assert f.computed["booked_total"] == 0 and f.computed["cash_total"] == 50_000
    assert f.computed["implied_rate"] == pytest.approx(0.05)          # 25,000 / (1,000,000 x 0.5)
    assert f.computed["book_rate"] == "BLANK"
    assert all(r["basis"].startswith("book coupon BLANK") for r in f.computed["receipts"])
    assert res.flags[0].rule == "cash_reconciliation"                 # ranks first by priority


def test_cash_with_zero_book_coupon_is_flagged():
    (f,) = rules(run(rec(coupon=0.0), ledger=receipts()), "cash_reconciliation")
    assert f.computed["book_rate"] == 0.0 and f.computed["direction"] == "understated"


def test_materially_lower_booked_income_flagged():
    (f,) = rules(run(rec(coupon=0.02), ledger=receipts()), "cash_reconciliation")
    assert f.computed["shortfall_pct"] == pytest.approx(0.6)
    assert f.computed["rate_gap_bp"] == pytest.approx(300)


def test_small_differences_tolerated():
    assert not rules(run(rec(coupon=0.0495), ledger=receipts()), "cash_reconciliation")


def test_ledger_booked_income_takes_precedence():
    assert not rules(run(blank(rec(), "coupon"), ledger=receipts(booked=25_000.0)), "cash_reconciliation")
    (f,) = rules(run(rec(), ledger=receipts(booked=0.0)), "cash_reconciliation")
    assert f.computed["receipts"][0]["basis"] == "ledger"


def test_over_accrual_flagged_as_overstated():
    (f,) = rules(run(rec(coupon=0.08), ledger=receipts()), "cash_reconciliation")
    assert f.computed["direction"] == "overstated" and f.severity < 100


def test_principal_cash_and_old_receipts_ignored():
    led = [LedgerEntry("P", "TEST00001", date(2026, 6, 1), 50_000.0, "principal"),
           LedgerEntry("P", "TEST00001", date(2020, 6, 1), 25_000.0, "interest")]
    assert not rules(run(blank(rec(), "coupon"), ledger=led), "cash_reconciliation")
