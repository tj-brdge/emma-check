"""Seeded synthetic agency MBS positions with planted defects.

All CUSIPs and terms are generated (fictional prefixes, random collateral). Defect M01 mirrors
the *pattern* of the motivating case (WAC-based non-round net coupon; book coupon 0%; one vendor
blank; monthly interest cash in the ledger) but none of the real security's terms.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from termscheck.core.daycount import add_months
from termscheck.core.identifiers import cusip_check_digit
from termscheck.core.records import BLANK, LedgerEntry, PeriodObservation, Position, SecurityRecord
from termscheck.plugins.agency_mbs.bondmath import MBSTerms, RateType, month_row, payment_date

AS_OF = date(2026, 11, 30)
SEED = 31350
HISTORY_MONTHS = 14            # disclosure months ending one month after AS_OF
PROGRAMS = [("FHLMC 45-day", 45, 0.45), ("UMBS 55-day", 55, 0.40), ("GNMA II 50-day", 50, 0.15)]


@dataclass
class MBSHolding:
    position: Position
    terms: MBSTerms
    book: SecurityRecord
    vendors: dict[str, SecurityRecord]
    ledger: list[LedgerEntry]
    observations: list[PeriodObservation]
    meta: dict = field(default_factory=dict)     # generation details used by the sample documents


@dataclass
class MBSDefect:
    defect_id: str
    cusip: str
    expected_rules: list[str]
    description: str


@dataclass
class MBSDataset:
    as_of: date
    holdings: list[MBSHolding]
    defects: list[MBSDefect] = field(default_factory=list)
    traps: dict[str, str] = field(default_factory=dict)     # cusip -> why it must not be flagged

    @property
    def defect_cusips(self) -> set[str]:
        return {d.cusip for d in self.defects}


def business_day(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


class _Gen:
    def __init__(self, seed: int):
        self.r = random.Random(seed)
        self.used: set[str] = set()

    def cusip(self) -> str:
        alnum = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        while True:
            base = "3" + "".join(self.r.choice(alnum) for _ in range(7))
            if base.startswith("31350A"):
                continue
            c = base + cusip_check_digit(base)
            if c not in self.used:
                self.used.add(c)
                return c


def _months(n: int) -> list[date]:
    last = add_months(AS_OF.replace(day=1), 1)
    return [add_months(last, -k) for k in range(n - 1, -1, -1)]


def _pool(g: _Gen, *, rate_type: RateType, coupon: float | None = None, delay: int | None = None,
          program: str | None = None, product: str = "pass_through"):
    r = g.r
    if delay is None:
        program, delay, _ = r.choices(PROGRAMS, weights=[w for *_, w in PROGRAMS])[0]
    issue = date(r.randint(2019, 2024), r.randint(1, 12), 1)
    maturity = add_months(issue, 12 * r.choice([15, 20, 30]))
    months = _months(HISTORY_MONTHS)
    age = (months[0].year - issue.year) * 12 + months[0].month - issue.month
    cpr = r.uniform(0.05, 0.15)
    smm = 1 - (1 - cpr) ** (1 / 12)
    f = (1 - smm) ** max(age, 0) * r.uniform(0.92, 1.0)
    obs = []
    meta: dict = {"program": program}
    if rate_type is RateType.FIXED:
        rates = [coupon] * len(months)
    elif rate_type is RateType.WAC:
        wac = r.uniform(5.2, 5.7) / 100
        fee = r.choice([0.0055, 0.0065, 0.0075])
        meta.update(fee=fee, initial_rate=round(wac + r.uniform(0.0008, 0.002) - fee, 5))
        rates = []
        for _ in months:
            wac -= r.uniform(0.0, 0.00025)                  # collateral WAC drifts as loans prepay
            rates.append(round(wac - fee, 5))               # non-round net coupon, 3 dp in percent
    else:                                                   # ARM: annual reset
        reset_k = r.randint(2, len(months) - 4)
        before, after = round(r.uniform(2.75, 3.75), 3) / 100, round(r.uniform(4.75, 5.6), 3) / 100
        rates = [before if k < reset_k else after for k in range(len(months))]
    for m, rt in zip(months, rates):
        obs.append(PeriodObservation(m, round(f, 10), rt if product != "po" else None))
        f *= (1 - smm)
    terms = MBSTerms(rate_type if product != "po" else RateType.FIXED,
                     rates[-1] if product != "po" else 0.0, delay, issue, maturity, observations=tuple(obs))
    return terms, obs, program, meta


def _records(g: _Gen, cusip: str, terms: MBSTerms, obs, program: str, product: str, *, book_coupon,
             book_factor, book_delay, rate_type_label: str, price: float):
    cur = next(o for o in obs if o.month == AS_OF.replace(day=1))
    desc = f"{program.split()[0]} Pool {cusip[1:7]} {'PO' if product == 'po' else ''}{rate_type_label.upper()} {terms.maturity_date:%m/%Y}"
    base = dict(cusip=cusip, description=" ".join(desc.split()), price=round(price, 3), price_convention="clean",
                coupon=book_coupon, accrual_type="zero" if product == "po" else "fixed", maturity_date=terms.maturity_date,
                issue_date=terms.issue_date, rating=None, sector="Agency MBS", state=None, payment_frequency=12,
                day_count="30/360", asset_class="agency_mbs", product_type=product, factor=book_factor,
                factor_date=cur.month, payment_delay_days=book_delay, rate_type=rate_type_label)
    book = SecurityRecord(vendor="FundAccounting", source_role="book", **base)
    vend = {"FactSet": SecurityRecord(vendor="FactSet", **{**base, "coupon": cur.net_coupon if product != "po" else 0.0,
                                                           "factor": cur.factor, "payment_delay_days": terms.payment_delay_days}),
            "PricingVendor": SecurityRecord(vendor="PricingVendor", **{**base, "coupon": cur.net_coupon if product != "po" else 0.0,
                                                                       "factor": cur.factor,
                                                                       "payment_delay_days": terms.payment_delay_days,
                                                                       "price": round(price + g.r.uniform(-0.2, 0.2), 3)})}
    return book, vend


def _ledger(g: _Gen, pos: Position, terms: MBSTerms, product: str, rounding: float = 0.0) -> list[LedgerEntry]:
    out = []
    for o in terms.observations:
        pay = payment_date(o.month, terms.payment_delay_days)
        if pay > AS_OF or pay <= AS_OF - timedelta(days=365):
            continue
        row = month_row(terms, pos.par, o.month)
        d = business_day(pay)
        if product != "po" and row.interest:
            out.append(LedgerEntry(pos.portfolio, pos.cusip, d, round(row.interest + rounding, 2), "interest"))
        if row.principal:
            out.append(LedgerEntry(pos.portfolio, pos.cusip, d, round(row.principal, 2), "principal"))
    return out


def _blank(rec: SecurityRecord, name: str) -> SecurityRecord:
    return replace(rec, **{name: None}, states={**rec.states, name: BLANK}, raw={**rec.raw, name: ""})


def generate(seed: int = SEED, n_clean: int = 41) -> MBSDataset:
    g = _Gen(seed)
    r = g.r
    ds = MBSDataset(AS_OF, [])

    def add(defect=None, expected=(), why="", *, rate_type=RateType.FIXED, coupon=None, product="pass_through",
            book_coupon="true", book_factor="true", book_delay="true", vendor_blank=(), vendor_zero=(),
            rounding=0.0, trap=None, delay=None, program=None):
        if coupon is None and rate_type is RateType.FIXED and product != "po":
            coupon = r.choice([2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5]) / 100
        terms, obs, program, meta = _pool(g, rate_type=rate_type, coupon=coupon, product=product, delay=delay,
                                          program=program)
        cusip = g.cusip()
        cur = next(o for o in obs if o.month == AS_OF.replace(day=1))
        true_rate = 0.0 if product == "po" else cur.net_coupon
        price = 70 + r.uniform(-3, 3) if product == "po" else 100 + (true_rate - 0.05) * 400 + r.uniform(-1, 1)
        pos = Position(r.choice(["MBS-01", "MBS-02"]), cusip, float(r.randint(100, 2000) * 5000))
        bc = true_rate if book_coupon == "true" else book_coupon
        bf = cur.factor if book_factor == "true" else book_factor
        bd = terms.payment_delay_days if book_delay == "true" else book_delay
        label = "zero" if product == "po" else rate_type.value
        book, vendors = _records(g, cusip, terms, obs, program, product, book_coupon=bc, book_factor=bf,
                                 book_delay=bd, rate_type_label=label, price=price)
        if book_coupon is None:
            book = _blank(book, "coupon")
        for v in vendor_blank:
            vendors[v] = _blank(vendors[v], "coupon")
        for v in vendor_zero:
            vendors[v] = replace(vendors[v], coupon=0.0)
        ledger = _ledger(g, pos, terms, product, rounding)
        ds.holdings.append(MBSHolding(pos, terms, book, vendors, ledger, obs, meta))
        if defect:
            ds.defects.append(MBSDefect(defect, cusip, list(expected), why))
        if trap:
            ds.traps[cusip] = trap
        return cusip

    for _ in range(n_clean):
        add(rate_type=r.choices([RateType.FIXED, RateType.WAC, RateType.ARM], weights=[80, 12, 8])[0])
    add(trap=None, rounding=0.03)   # servicer rounding: cents per payment, must not flag
    ds.traps[ds.holdings[-1].position.cusip] = "cash differs from expected by cents (servicer rounding)"
    add(product="po", trap="principal-only strip: zero coupon by design, no interest cash")

    add("M01-blank-became-zero", ["null_vs_zero", "frequency_contradiction", "cash_reconciliation",
                                   "rate_vs_disclosure"],
        "WAC-based net coupon (non-round, from generated collateral). Fund accounting carries 0%, FactSet "
        "carries the coupon BLANK; monthly interest cash arrives in the ledger. Mirrors the motivating pattern "
        "without its terms.",
        rate_type=RateType.WAC, book_coupon=0.0, vendor_blank=("FactSet",), program="FHLMC 45-day", delay=45)
    add("M02-coupon-mistyped", ["cash_reconciliation", "rate_vs_disclosure"],
        "Fixed 5.5% pool booked at 3.5% (mistyped rate); cash shows 5.5%.",
        coupon=0.055, book_coupon=0.035, program="FHLMC 45-day", delay=45)
    add("M03-stale-factor", ["factor_mismatch", "cash_reconciliation"],
        "Book carries the factor from issue (1.0); income over-accrued on face that has paid down.",
        coupon=0.045, book_factor=1.0)
    add("M04-wrong-delay", ["vendor_disagreement"],
        "Book payment delay 0 days vs 55 stated (vendors agree on 55): receivable timing is wrong.",
        coupon=0.04, book_delay=0, program="UMBS 55-day", delay=55)
    add("M05-vendor-blank-vs-zero", ["null_vs_zero"],
        "Book correct; FactSet coupon BLANK while PricingVendor sends 0%. No income impact yet - a feed "
        "defect waiting to propagate.",
        coupon=0.05, vendor_blank=("FactSet",), vendor_zero=("PricingVendor",))
    add("M06-arm-reset-missed", ["rate_vs_disclosure", "cash_reconciliation"],
        "ARM reset to a higher rate; book still carries the pre-reset rate.",
        rate_type=RateType.ARM, book_coupon="pre_reset")
    add("M07-blank-in-book", ["null_vs_zero", "frequency_contradiction", "cash_reconciliation",
                               "rate_vs_disclosure"],
        "Book coupon BLANK (not zero) with interest cash arriving; vendors carry the coupon.",
        coupon=0.035, book_coupon=None)
    # M06: book coupon = pre-reset rate
    h = next(x for x in ds.holdings if x.position.cusip == ds.defects[5].cusip)
    pre = h.observations[0].net_coupon
    h.book = replace(h.book, coupon=pre)
    return ds


def to_screen_input(ds: MBSDataset):
    from termscheck.core.records import ScreenInput
    vendors: dict[str, dict[str, SecurityRecord]] = {}
    for h in ds.holdings:
        for name, rec in h.vendors.items():
            vendors.setdefault(name, {})[rec.cusip] = rec
    return ScreenInput(ds.as_of, [h.position for h in ds.holdings], {h.book.cusip: h.book for h in ds.holdings},
                       vendors=vendors, ledger=[e for h in ds.holdings for e in h.ledger],
                       observations={h.position.cusip: [o for o in h.observations if o.month <= add_months(
                           ds.as_of.replace(day=1), 1)] for h in ds.holdings})


def disclosure_csv(ds: MBSDataset) -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["cusip", "factor_month", "factor", "net_coupon"])
    for h in ds.holdings:
        for o in h.observations:
            w.writerow([h.position.cusip, f"{o.month:%Y-%m}", f"{o.factor:.10f}",
                        "" if o.net_coupon is None else f"{o.net_coupon * 100:.3f}"])
    return buf.getvalue()
