from datetime import date

import pytest

from termscheck.ingest import parse_holdings, parse_price_history, parse_vendor
from termscheck.screens import run_screens
from termscheck.synthetic import to_screen_input

HEADER = ("CUSIP,Description,Par,Market Price,Convention,Vendor Coupon,Vendor Accrual Type,"
          "Maturity Date,Issue Date,Rating,Sector,State,Yield\n")
GOOD = "Q4TWLP484,Test Def Int 11% 2034,4000000,221.199,clean,0,zero,07/01/2034,2019-07-01,NR,Special Assessment,fl,11.0\n"


def test_round_trip_matches_generator(dataset, synthetic_csvs):
    h = parse_holdings(synthetic_csvs["holdings"])
    v = parse_vendor(synthetic_csvs["vendor_secondary"], "VendorB")
    p = parse_price_history(synthetic_csvs["price_history"])
    assert h.ok and v.ok and p.ok
    assert len(h.records) == len(dataset.holdings) == len(h.positions)
    assert len(p.prices) == 12 * len(dataset.holdings)
    by = {r.cusip: r for r in h.records}
    for x in dataset.holdings:
        r = by[x.vendor_a.cusip]
        assert r.coupon == pytest.approx(x.vendor_a.coupon)
        assert r.price == pytest.approx(x.vendor_a.price)
        assert r.maturity_date == x.vendor_a.maturity_date


def test_screens_identical_after_csv_round_trip(dataset, synthetic_csvs, screen_result):
    from termscheck.screens import ScreenInput
    h = parse_holdings(synthetic_csvs["holdings"])
    v = parse_vendor(synthetic_csvs["vendor_secondary"], "VendorB")
    p = parse_price_history(synthetic_csvs["price_history"])
    hist = {}
    for pt in p.prices:
        hist.setdefault(pt.cusip, []).append(pt)
    data = ScreenInput(dataset.as_of, h.positions, {r.cusip: r for r in h.records},
                       {r.cusip: r for r in v.records}, hist)
    got = {(f.cusip, f.rule) for f in run_screens(data).flags}
    assert got == {(f.cusip, f.rule) for f in screen_result.flags}


def test_aliases_percent_and_date_formats():
    r = parse_holdings(HEADER + GOOD)
    assert r.ok, r.errors
    rec = r.records[0]
    assert rec.coupon == 0.0 and rec.vendor_yield == pytest.approx(0.11)
    assert rec.maturity_date == date(2034, 7, 1) and rec.state == "FL"
    assert r.positions[0].portfolio == "DEFAULT"


def test_missing_required_column_rejected():
    r = parse_holdings("cusip,description,par\nQ4TWLP484,x,100\n")
    assert not r.ok
    assert {e.column for e in r.errors} >= {"price", "coupon", "maturity_date"}


@pytest.mark.parametrize("bad,column", [
    ("Q4TWLP485", "cusip"),        # wrong check digit
    ("Q4TWLP48", "cusip"),         # too short
])
def test_bad_cusip_rejected(bad, column):
    r = parse_holdings(HEADER + GOOD.replace("Q4TWLP484", bad))
    assert not r.ok and r.errors[0].column == column and r.errors[0].row == 1


def test_whole_file_rejected_on_any_row_error():
    bad = GOOD.replace("clean", "sorta-clean").replace("Q4TWLP484", "21A0SG596")
    r = parse_holdings(HEADER + GOOD + bad)
    assert not r.ok
    assert [(e.row, e.column) for e in r.errors] == [(2, "price_convention")]


def test_duplicate_positions_rejected():
    r = parse_holdings(HEADER + GOOD + GOOD)
    assert not r.ok and "duplicate" in r.errors[0].message


def test_maturity_before_issue_rejected():
    r = parse_holdings(HEADER + GOOD.replace("07/01/2034", "01/01/2018"))
    assert not r.ok and r.errors[0].column == "maturity_date"
