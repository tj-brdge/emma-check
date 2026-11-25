"""Agency MBS bond math against hand calculations (derivations in comments)."""
from datetime import date

import pytest

from termscheck.plugins.agency_mbs.bondmath import (MBSTerms, MonthObservation, RateType, accrual_month_paid_on,
                                                    accrued_through, implied_rate, interest_receivable,
                                                    month_row, payment_date, schedule, settlement_accrued)

D = date
approx = lambda x, tol=1e-6: pytest.approx(x, abs=tol)  # noqa: E731
OF = 1_000_000.0


def obs(*rows):
    return tuple(MonthObservation(D(*m), f, r) for m, f, r in rows)


FIXED = MBSTerms(RateType.FIXED, 0.05, 45, D(2024, 1, 1), D(2054, 1, 1),
                 observations=obs(((2026, 10, 1), 0.86, None), ((2026, 11, 1), 0.85, None),
                                  ((2026, 12, 1), 0.84, None)))
WAC = MBSTerms(RateType.WAC, None, 45, D(2024, 1, 1), D(2054, 1, 1),
               observations=obs(((2026, 9, 1), 0.87, 0.04810), ((2026, 10, 1), 0.86, 0.04795),
                                ((2026, 11, 1), 0.85, 0.04773)))


# ---------------------------------------------------------------- payment delay
@pytest.mark.parametrize("month,delay,expected", [
    ((2026, 1, 1), 45, (2026, 2, 15)),   # (45-1) = 1 month + 14 days -> 15th of next month
    ((2026, 1, 1), 55, (2026, 2, 25)),   # 1 month + 24 days -> 25th
    ((2026, 1, 1), 50, (2026, 2, 20)),
    ((2026, 1, 1), 75, (2026, 3, 15)),   # 2 months + 14 days -> 15th two months out
    ((2026, 2, 1), 45, (2026, 3, 15)),   # February accrual: still the 15th (30/360 day count)
    ((2026, 12, 1), 45, (2027, 1, 15)),  # year roll
])
def test_payment_date(month, delay, expected):
    assert payment_date(D(*month), delay) == D(*expected)
    assert accrual_month_paid_on(D(*expected), delay) == D(*month)


# ---------------------------------------------------------------- monthly interest and principal
def test_month_interest_on_current_face():
    # Nov 2026: face = 1,000,000 x 0.85 = 850,000; interest = 850,000 x 5% / 12 = 3,541.6667
    r = month_row(FIXED, OF, D(2026, 11, 1))
    assert r.face == approx(850_000) and r.interest == approx(3_541.666667)
    assert r.payment_date == D(2026, 12, 15)


def test_principal_paydown():
    # Oct principal = 1,000,000 x (0.86 - 0.85) = 10,000, paid with Oct interest on Nov 15
    r = month_row(FIXED, OF, D(2026, 10, 1))
    assert r.principal == approx(10_000) and r.payment_date == D(2026, 11, 15)
    # Dec has no Jan factor observation: principal unknown (None), never 0
    assert month_row(FIXED, OF, D(2026, 12, 1)).principal is None


def test_wac_rate_changes_monthly():
    # Nov: 850,000 x 4.773% / 12 = 3,380.875 ; Oct: 860,000 x 4.795% / 12 = 3,436.4167
    assert month_row(WAC, OF, D(2026, 11, 1)).interest == approx(3_380.875)
    assert month_row(WAC, OF, D(2026, 10, 1)).interest == approx(3_436.416667)


def test_missing_month_carried_forward_and_reported():
    r = month_row(WAC, OF, D(2026, 12, 1))
    assert r.rate == 0.04773 and r.factor == 0.85
    assert any("carried forward" in a for a in r.assumptions)


def test_implied_rate_from_cash():
    # 3,380.875 x 12 / 850,000 = 4.773%
    assert implied_rate(3_380.875, OF, 0.85) == approx(0.04773)


# ---------------------------------------------------------------- accrual and receivable
def test_settlement_accrued():
    # Settle Nov 16: 15 days (30/360 from the 1st, exclusive): 850,000 x 5% x 15/360 = 1,770.8333
    assert settlement_accrued(FIXED, OF, D(2026, 11, 16)) == approx(1_770.833333)


def test_accrued_through_month_end_is_full_month():
    # Through Nov 30 inclusive = 30 days = one full month = 3,541.6667
    a, _ = accrued_through(FIXED, OF, D(2026, 11, 30))
    assert a == approx(3_541.666667)


def test_receivable_45_day_delay_month_end():
    # As of Nov 30: Oct interest paid Nov 15 (settled); Nov accrued in full, paid Dec 15 -> 3,541.6667
    r, unpaid, _ = interest_receivable(FIXED, OF, D(2026, 11, 30))
    assert r == approx(3_541.666667) and unpaid == []


def test_receivable_45_day_delay_mid_month_spans_two_months():
    # As of Nov 10: Oct unpaid (pays Nov 15): 860,000 x 5%/12 = 3,583.3333
    #   + Nov through Nov 10 inclusive: 850,000 x 5% x 10/360 = 1,180.5556  -> 4,763.8889
    r, unpaid, _ = interest_receivable(FIXED, OF, D(2026, 11, 10))
    assert [u.month for u in unpaid] == [D(2026, 10, 1)]
    assert r == approx(4_763.888889)


def test_receivable_75_day_delay_month_end():
    # 75-day delay: Oct pays Dec 15, so as of Nov 30 both Oct (3,583.3333) and Nov (3,541.6667) are unpaid
    t = MBSTerms(RateType.FIXED, 0.05, 75, D(2024, 1, 1), D(2054, 1, 1), observations=FIXED.observations)
    r, unpaid, _ = interest_receivable(t, OF, D(2026, 11, 30))
    assert [u.month for u in unpaid] == [D(2026, 10, 1)] and r == approx(7_125.0)


def test_schedule_rows():
    rows = schedule(WAC, OF, D(2026, 9, 1), D(2026, 11, 1))
    assert [r.payment_date for r in rows] == [D(2026, 10, 15), D(2026, 11, 15), D(2026, 12, 15)]
    assert [round(r.principal, 2) for r in rows[:2]] == [10_000.0, 10_000.0]


def test_terms_validation():
    with pytest.raises(ValueError):
        MBSTerms(RateType.FIXED, None, 45, D(2024, 1, 1), D(2054, 1, 1))
    with pytest.raises(ValueError):
        MBSTerms(RateType.WAC, None, 200, D(2024, 1, 1), D(2054, 1, 1))
