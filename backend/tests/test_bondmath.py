"""Bond math tests against hand-calculated values.

Each expected value is derived in the comment beside it; literals were computed by hand
from the closed-form expressions shown (powers evaluated to 8+ significant digits).
"""
from datetime import date

import pytest

from termscheck.bondmath import (
    DayCount, InterestTerms, InterestType, VendorView, accreted_value, accretion_schedule,
    accrued_interest, cash_flows, compute_treatment, days_30_360, dirty_price_from_yield,
    economic_income, yield_from_dirty_price,
)

D = date
approx = lambda x, tol=1e-6: pytest.approx(x, abs=tol)  # noqa: E731


# ---------------------------------------------------------------- 30/360 (MSRB G-33)
@pytest.mark.parametrize("d1,d2,expected", [
    (D(2026, 1, 15), D(2026, 7, 15), 180),      # 6 months * 30
    (D(2026, 1, 31), D(2026, 3, 1), 31),        # D1 31->30: 2*30 + (1-30) = 31
    (D(2026, 2, 28), D(2026, 3, 31), 30),       # D1 last Feb ->30; D2 31 & D1>=30 ->30: 30+0
    (D(2024, 2, 29), D(2025, 2, 28), 360),      # both last day of Feb: D1, D2 -> 30
    (D(2026, 3, 30), D(2026, 3, 31), 0),        # D2 31 & D1 30 -> D2 30
    (D(2026, 3, 15), D(2026, 3, 31), 16),       # D1=15 so D2 stays 31
    (D(2026, 6, 1), D(2026, 8, 15), 74),        # 2*30 + 14
])
def test_days_30_360(d1, d2, expected):
    assert days_30_360(d1, d2) == expected


# ---------------------------------------------------------------- current pay accrued
CP = InterestTerms(InterestType.CURRENT_PAY, 0.05, D(2020, 6, 1), D(2040, 6, 1))


def test_accrued_current_pay_30_360():
    # last coupon 2026-06-01; 74 days 30/360 -> 5 * 74/360 = 1.0277777...
    assert accrued_interest(CP, D(2026, 8, 15)) == approx(5 * 74 / 360)
    assert accrued_interest(CP, D(2026, 8, 15)) == approx(1.0277778, 1e-6)


def test_accrued_current_pay_act_act():
    t = InterestTerms(InterestType.CURRENT_PAY, 0.05, D(2020, 6, 1), D(2040, 6, 1),
                      day_count=DayCount.ACT_ACT)
    # 75 actual days / (2 * 183 days in Jun1-Dec1 period) * 5 = 375/366 = 1.0245902
    assert accrued_interest(t, D(2026, 8, 15)) == approx(1.0245902, 1e-6)


def test_accrued_zero_on_coupon_date():
    assert accrued_interest(CP, D(2026, 6, 1)) == approx(0.0)


# ---------------------------------------------------------------- CAB accretion
# 6% compounded semiannually, dated 2020-06-01, maturity 2030-06-01 -> 20 periods.
CAB = InterestTerms(InterestType.CAPITAL_APPRECIATION, 0.06, D(2020, 6, 1), D(2030, 6, 1))


def test_cab_initial_and_maturity_value():
    # initial = 100 / 1.03^20 = 55.3675754
    assert accreted_value(CAB, D(2020, 6, 1)) == approx(55.3675754)
    assert accreted_value(CAB, D(2030, 6, 1)) == approx(100.0)


def test_cab_value_on_compounding_dates():
    # 2026-06-01 is 8 periods before maturity: 100 / 1.03^8 = 100 / 1.26677008 = 78.9409234
    assert accreted_value(CAB, D(2026, 6, 1)) == approx(78.9409234)
    # 2026-12-01: 100 / 1.03^7 = 100 / 1.22987387 = 81.3091511
    assert accreted_value(CAB, D(2026, 12, 1)) == approx(81.3091511)


def test_cab_linear_interpolation_between_compounding_dates():
    # 2026-09-01 is 90/180 = 0.5 through the period: (78.9409234 + 81.3091511) / 2 = 80.1250373
    assert accreted_value(CAB, D(2026, 9, 1)) == approx(80.1250373)


def test_cab_schedule_has_all_compounding_dates():
    sched = accretion_schedule(CAB)
    assert len(sched) == 21  # dated date + 20 compounding dates
    assert sched[0].value == approx(55.3675754)
    assert sched[-1].value == approx(100.0)
    assert all(a.value < b.value for a, b in zip(sched, sched[1:]))


def test_cab_short_first_period():
    # dated 2020-03-01, first compounding 2020-06-01. Regular period Dec1-Jun1; at Mar1
    # 90/180 = 0.5 elapsed, so the stub is 0.5 period: n = 20.5; initial = 100/1.03^20.5
    t = InterestTerms(InterestType.CAPITAL_APPRECIATION, 0.06, D(2020, 3, 1), D(2030, 6, 1))
    assert accreted_value(t, D(2020, 3, 1)) == approx(54.5552931)
    assert accreted_value(t, D(2026, 6, 1)) == approx(78.9409234)  # unaffected by stub
    assert accrued_interest(t, D(2026, 9, 1)) == 0.0                # CAB: no accrued interest


# ---------------------------------------------------------------- deferred interest
# 11% compounded semiannually, dated 2019-07-01, paid at maturity 2034-07-01 (the
# "zero coupon, clean price, accretes and pays at maturity" pattern).
DEF = InterestTerms(InterestType.DEFERRED_INTEREST, 0.11, D(2019, 7, 1), D(2034, 7, 1))


def test_deferred_value_on_compounding_date():
    # 14 periods: 100 * 1.055^14 = 100 * 2.11609146 = 211.6091462
    assert accreted_value(DEF, D(2026, 7, 1)) == approx(211.6091462)
    # Entire excess over principal is accrued-but-unpaid interest
    assert accrued_interest(DEF, D(2026, 7, 1)) == approx(111.6091462)


def test_deferred_value_between_compounding_dates():
    # 2026-11-30: 30/360 days from Jul 1 = 4*30 + 29 = 149 -> 149/180 of the way from
    # 100*1.055^14 = 211.6091462 to 100*1.055^15 = 223.2476492:
    # 211.6091462 + 11.6385030 * 149/180 = 221.2432404
    assert accreted_value(DEF, D(2026, 11, 30)) == approx(221.2432404)


def test_deferred_simple_interest():
    # 5% simple from 2020-01-01: 3.5 years -> 100 * (1 + 0.05 * 3.5) = 117.5
    t = InterestTerms(InterestType.DEFERRED_INTEREST, 0.05, D(2020, 1, 1), D(2030, 1, 1),
                      compounding_frequency=0)
    assert accreted_value(t, D(2023, 7, 1)) == approx(117.5)
    assert accrued_interest(t, D(2023, 7, 1)) == approx(17.5)
    # single cash flow at maturity: 100 * (1 + 0.05 * 10) = 150
    cfs = cash_flows(t, D(2023, 7, 1))
    assert len(cfs) == 1 and cfs[0].amount == approx(150.0)


def test_deferred_single_cash_flow_at_maturity():
    cfs = cash_flows(DEF, D(2026, 7, 1))
    # 30 periods: 100 * 1.055^30
    assert len(cfs) == 1 and cfs[0].date == D(2034, 7, 1)
    assert cfs[0].amount == approx(100 * 1.055 ** 30)


# ---------------------------------------------------------------- convertible CAB
CCAB = InterestTerms(InterestType.CONVERTIBLE_CAB, 0.05, D(2020, 6, 1), D(2040, 6, 1),
                     conversion_date=D(2025, 6, 1))


def test_ccab_accretes_to_par_then_pays_current():
    # 10 periods to conversion: 100 / 1.025^10 = 78.1198402
    assert accreted_value(CCAB, D(2020, 6, 1)) == approx(78.1198402)
    assert accreted_value(CCAB, D(2025, 6, 1)) == approx(100.0)
    assert accrued_interest(CCAB, D(2024, 9, 1)) == 0.0
    # after conversion: 5 * 74/360 on 2026-08-15
    assert accrued_interest(CCAB, D(2026, 8, 15)) == approx(1.0277778, 1e-6)
    cfs = cash_flows(CCAB, D(2026, 8, 15))
    assert cfs[0].date == D(2026, 12, 1) and cfs[0].amount == approx(2.5)
    assert cfs[-1].amount == approx(102.5)


def test_ccab_economic_income_spans_conversion():
    # 2025-01-01 .. 2025-12-01: accretion to conversion + coupon accrual after.
    # accretion: 100 - V(2025-01-01); V(2025-01-01) is 30/180 into the Dec1-Jun1 period
    v_dec = 100 / 1.025
    v_jan = v_dec + (100 - v_dec) * 30 / 180
    coupon = 100 * 0.05 * 180 / 360  # Jun1 -> Dec1 = 2.5
    assert economic_income(CCAB, D(2025, 1, 1), D(2025, 12, 1)) == approx(100 - v_jan + coupon)


# ---------------------------------------------------------------- yields
def test_zero_coupon_yield_round_trip():
    cfs = cash_flows(CAB, D(2020, 6, 1))
    y = yield_from_dirty_price(cfs, D(2020, 6, 1), 55.3675754, anchor=CAB.maturity_date)
    assert y == approx(0.06, 1e-8)


def test_par_bond_yields_coupon():
    cfs = cash_flows(CP, D(2026, 6, 1))
    assert yield_from_dirty_price(cfs, D(2026, 6, 1), 100.0, anchor=CP.maturity_date) == approx(0.05, 1e-8)


def test_mid_period_dirty_price():
    # 5% bond at 5% yield, halfway through a period (2026-09-01, 90/180):
    # value at next coupon date incl. coupon = 102.5; dirty = 102.5 / 1.025^0.5 = 101.2422837
    cfs = cash_flows(CP, D(2026, 9, 1))
    p = dirty_price_from_yield(cfs, D(2026, 9, 1), 0.05, anchor=CP.maturity_date)
    assert p == approx(101.2422837)
    assert yield_from_dirty_price(cfs, D(2026, 9, 1), p, anchor=CP.maturity_date) == approx(0.05, 1e-8)


def test_no_yield_for_impossible_price():
    cfs = cash_flows(CAB, D(2026, 6, 1))
    assert yield_from_dirty_price(cfs, D(2026, 6, 1), 0.0, anchor=CAB.maturity_date) is None


# ---------------------------------------------------------------- treatment
def test_treatment_deferred_interest_with_zero_vendor_coupon():
    """Vendor: coupon 0, 'clean', price = full value. Document: 11% deferred interest."""
    as_of = D(2026, 7, 1)
    full = 211.6091462  # = accreted value; at an 11% yield the price equals accreted value
    vendor = VendorView(price=full, price_convention="clean", coupon=0.0, accrual_type="fixed")
    t = compute_treatment(DEF, vendor, par=1_000_000, as_of=as_of)
    assert t.vendor_accrued == 0.0
    assert t.full_value == approx(full)
    assert t.true_accrued == approx(111.6091462)
    assert t.correct_clean == approx(100.0)
    assert t.correct_dirty == approx(full)
    assert t.vendor_clean == approx(full)
    # 111.6091462 per 100 * 1,000,000 / 100 = 1,116,091.46
    assert t.unbooked_income_usd == approx(1_116_091.462, 1e-2)
    assert t.yield_document_terms == approx(0.11, 1e-6)
    # vendor view: 100 at maturity (16 periods) for 211.609 -> 2*((100/211.609)^(1/16)-1)
    assert t.yield_vendor_terms == approx(2 * ((100 / full) ** (1 / 16) - 1), 1e-6)
    assert t.yield_vendor_terms < 0
    assert t.schedule[0].value == approx(100.0)


def test_treatment_window_since_acquisition():
    # acquired 2026-01-01; income Jan1->Jul1 = 100*1.055^14 - 100*1.055^13 = 11.0317564 per 100
    vendor = VendorView(price=211.6091462, price_convention="clean", coupon=0.0, accrual_type="fixed")
    t = compute_treatment(DEF, vendor, par=1_000_000, as_of=D(2026, 7, 1), window_start=D(2026, 1, 1))
    assert t.unbooked_window_usd == approx(110_317.564, 1e-2)


def test_treatment_correct_vendor_has_no_impact():
    vendor = VendorView(price=99.5, price_convention="clean", coupon=0.05, accrual_type="fixed")
    t = compute_treatment(CP, vendor, par=500_000, as_of=D(2026, 8, 15))
    assert t.vendor_accrued == approx(1.0277778, 1e-6)
    assert t.full_value == approx(99.5 + 1.0277778, 1e-6)
    assert t.correct_clean == approx(99.5)
    assert t.unbooked_income_usd == approx(0.0)


def test_treatment_cab_vendor_zero_coupon_is_consistent():
    vendor = VendorView(price=78.9409234, price_convention="clean", coupon=0.0, accrual_type="zero")
    t = compute_treatment(CAB, vendor, par=1_000_000, as_of=D(2026, 6, 1))
    assert t.unbooked_income_usd == approx(0.0)
    assert t.yield_document_terms == approx(0.06, 1e-6)
    assert t.accreted_value == approx(78.9409234)


def test_treatment_dirty_convention_not_double_counted():
    vendor = VendorView(price=211.6091462, price_convention="dirty", coupon=0.0, accrual_type="fixed")
    t = compute_treatment(DEF, vendor, par=100, as_of=D(2026, 7, 1))
    assert t.full_value == approx(211.6091462)
    assert t.correct_clean == approx(100.0)


def test_invalid_terms_rejected():
    with pytest.raises(ValueError):
        InterestTerms(InterestType.CONVERTIBLE_CAB, 0.05, D(2020, 1, 1), D(2030, 1, 1))
    with pytest.raises(ValueError):
        InterestTerms(InterestType.CURRENT_PAY, 0.05, D(2030, 1, 1), D(2020, 1, 1))


def test_forward_run_rate():
    # Deferred 11% from 2026-07-01: next 12 months = V(2027-07-01) - V(2026-07-01)
    #   = 100*1.055^16 - 100*1.055^14 = 100*1.055^14*(1.055^2 - 1) = 211.6091462 * 0.113025 = 23.9171237
    vendor = VendorView(price=211.6091462, price_convention="clean", coupon=0.0, accrual_type="zero")
    t = compute_treatment(DEF, vendor, par=100, as_of=D(2026, 7, 1))
    assert t.income_next_12m_document == approx(23.9171237, 1e-6)
    # vendor zero: constant-yield at the vendor-implied (negative) yield -> negative "income"
    yv = t.yield_vendor_terms
    assert t.income_next_12m_vendor == approx(211.6091462 * ((1 + yv / 2) ** 2 - 1), 1e-6)
    assert t.run_rate_gap_usd == approx(t.income_next_12m_document - t.income_next_12m_vendor)
