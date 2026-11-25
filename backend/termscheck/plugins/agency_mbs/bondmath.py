"""Agency MBS bond math. Pure functions, no I/O.

Conventions (documented and unit-tested):
- Accrual period = calendar month M on a 30/360 basis; one month = 30/360 of a year.
- factor[M] = fraction of original face outstanding during accrual month M.
- Interest for M = original face x factor[M] x rate[M] / 12.
- Principal for M = original face x (factor[M] - factor[M+1]).
- Both are paid on M's payment date: the stated delay D counts 30/360 days from the 1st of M,
  the 1st being day 1, so D=45 -> 15th of M+1, D=55 -> 25th of M+1, D=75 -> 15th of M+2.
  No holiday calendar is applied.
- Variable (WAC-based / ARM) net coupons come from a per-month table. A missing month never
  becomes zero: the last known value is carried forward and reported as an assumption.
- Accounting accrual is through the as-of date inclusive. Settlement accrued (for the clean/dirty
  split) counts 30/360 days from the 1st up to, not including, the settlement date.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

from termscheck.core.daycount import DayCount, add_months, days_30_360
from termscheck.core.records import PeriodObservation


class RateType(StrEnum):
    FIXED = "fixed"
    WAC = "wac"          # net coupon = weighted-average coupon of the collateral less fees; resets monthly
    ARM = "arm"          # index + margin with caps; resets on a schedule


MonthObservation = PeriodObservation   # first day of the accrual month; factor; net coupon; locator


@dataclass(frozen=True)
class MBSTerms:
    rate_type: RateType
    net_coupon: float | None             # fixed rate, or the rate stated in the offering document
    payment_delay_days: int
    issue_date: date                     # first day of the first accrual month
    maturity_date: date
    day_count: DayCount = DayCount.THIRTY_360
    reset_rule: str | None = None        # text from the offering document (variable rates)
    observations: tuple[MonthObservation, ...] = ()   # factors / net coupons by month

    def __post_init__(self) -> None:
        if self.payment_delay_days < 0 or self.payment_delay_days > 120:
            raise ValueError("payment_delay_days must be between 0 and 120")
        if self.rate_type is RateType.FIXED and self.net_coupon is None:
            raise ValueError("a fixed-rate security needs a net coupon")
        if self.day_count is not DayCount.THIRTY_360:
            raise ValueError("only 30/360 monthly accrual is implemented for agency MBS")


@dataclass
class MonthRow:
    month: date
    payment_date: date
    factor: float
    face: float
    rate: float | None
    interest: float | None
    principal: float | None
    assumptions: list[str] = field(default_factory=list)


def month_start(d: date) -> date:
    return d.replace(day=1)


def payment_date(accrual_month: date, delay_days: int) -> date:
    """Payment date for accrual month starting ``accrual_month`` (1st) with a stated delay."""
    if delay_days <= 0:
        return accrual_month
    months, day = divmod(delay_days - 1, 30)
    target = add_months(month_start(accrual_month), months)
    last = (add_months(target, 1) - timedelta(days=1)).day
    return target.replace(day=min(day + 1, last))


def accrual_month_paid_on(pay: date, delay_days: int) -> date:
    """Inverse of payment_date: the accrual month a scheduled payment on ``pay`` belongs to."""
    months, _ = divmod(max(delay_days, 1) - 1, 30)
    return add_months(month_start(pay), -months)


def _lookup(obs: dict[date, MonthObservation], month: date, attr: str) -> tuple[float | None, str | None]:
    if month in obs and getattr(obs[month], attr) is not None:
        return getattr(obs[month], attr), None
    prior = [m for m in obs if m < month and getattr(obs[m], attr) is not None]
    if prior:
        m = max(prior)
        return getattr(obs[m], attr), f"{attr} for {month:%Y-%m} not supplied; carried forward from {m:%Y-%m}"
    return None, f"{attr} for {month:%Y-%m} not available"


def rate_for(terms: MBSTerms, month: date) -> tuple[float | None, str | None]:
    if terms.rate_type is RateType.FIXED:
        return terms.net_coupon, None
    obs = {o.month: o for o in terms.observations}
    r, why = _lookup(obs, month, "net_coupon")
    if r is None and terms.net_coupon is not None:
        return terms.net_coupon, f"no monthly net coupon for {month:%Y-%m}; offering-document rate used"
    return r, why


def factor_for(terms: MBSTerms, month: date, fallback: float | None = None) -> tuple[float | None, str | None]:
    obs = {o.month: o for o in terms.observations}
    f, why = _lookup(obs, month, "factor")
    if f is None and fallback is not None:
        return fallback, f"factor for {month:%Y-%m} not supplied; position factor used"
    return f, why


def month_row(terms: MBSTerms, original_face: float, month: date, fallback_factor: float | None = None) -> MonthRow:
    month = month_start(month)
    notes = []
    f, w1 = factor_for(terms, month, fallback_factor)
    f_next, _ = factor_for(terms, add_months(month, 1))
    r, w2 = rate_for(terms, month)
    notes += [w for w in (w1, w2) if w]
    if f is None:
        raise ValueError(f"no factor available for {month:%Y-%m}")
    face = original_face * f
    interest = None if r is None else face * r / 12.0
    principal = None if f_next is None or (add_months(month, 1) not in {o.month for o in terms.observations}) \
        else original_face * (f - f_next)
    return MonthRow(month, payment_date(month, terms.payment_delay_days), f, face, r, interest, principal, notes)


def schedule(terms: MBSTerms, original_face: float, first: date, last: date,
             fallback_factor: float | None = None) -> list[MonthRow]:
    out, m = [], month_start(first)
    while m <= month_start(last):
        out.append(month_row(terms, original_face, m, fallback_factor))
        m = add_months(m, 1)
    return out


def accrued_through(terms: MBSTerms, original_face: float, as_of: date, fallback_factor: float | None = None
                    ) -> tuple[float | None, list[str]]:
    """Interest accrued in the current month through ``as_of`` inclusive (accounting view)."""
    row = month_row(terms, original_face, as_of, fallback_factor)
    if row.rate is None:
        return None, row.assumptions
    days = days_30_360(row.month, as_of + timedelta(days=1))
    return row.face * row.rate * min(days, 30) / 360.0, row.assumptions


def settlement_accrued(terms: MBSTerms, original_face: float, settle: date,
                       fallback_factor: float | None = None) -> float | None:
    """Accrued interest a buyer pays at settlement (30/360 days from the 1st, exclusive of settle)."""
    row = month_row(terms, original_face, settle, fallback_factor)
    return None if row.rate is None else row.face * row.rate * days_30_360(row.month, settle) / 360.0


def interest_receivable(terms: MBSTerms, original_face: float, as_of: date, fallback_factor: float | None = None
                        ) -> tuple[float | None, list[MonthRow], list[str]]:
    """Earned but unpaid interest at ``as_of``: completed months whose payment date is after
    ``as_of`` plus the current month accrued through ``as_of``. With a 45-55 day delay this is
    up to about two months of interest; with 75 days, up to about three."""
    cur = month_start(as_of)
    unpaid, notes = [], []
    m = add_months(cur, -1)
    while payment_date(m, terms.payment_delay_days) > as_of and m >= month_start(terms.issue_date):
        unpaid.append(month_row(terms, original_face, m, fallback_factor))
        m = add_months(m, -1)
    partial, n2 = accrued_through(terms, original_face, as_of, fallback_factor)
    notes += n2 + [a for r in unpaid for a in r.assumptions]
    if partial is None or any(r.interest is None for r in unpaid):
        return None, unpaid, notes
    return partial + sum(r.interest for r in unpaid), list(reversed(unpaid)), notes


def implied_rate(cash: float, original_face: float, factor: float) -> float:
    """Annual rate implied by one month's interest cash on the outstanding face."""
    return cash * 12.0 / (original_face * factor)
