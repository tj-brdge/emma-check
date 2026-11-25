"""Seeded synthetic muni holdings with planted defects.

Produces ~200 holdings (vendor A), a secondary vendor (B), monthly price history and a
manifest of planted defects with their ground-truth terms. Every CUSIP is synthetic (valid
check digit, fictional issuer); nothing is copied from real securities.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from .bondmath import (DayCount, InterestTerms, InterestType, accrued_interest, cash_flows,
                       dirty_price_from_yield)
from .bondmath.daycount import add_months
from .screens.models import Position, PricePoint, SecurityRecord

AS_OF = date(2026, 11, 30)
SEED = 20261125

SECTORS = {  # sector -> spread (decimal)
    "General Obligation": 0.0, "Water & Sewer": 0.0010, "Transportation": 0.0030,
    "Hospital": 0.0070, "Higher Education": 0.0040, "Housing": 0.0035,
    "Public Power": 0.0015, "Special Assessment": 0.0150,
}
RATINGS = [("AAA", 0.0, 8), ("AA+", 0.001, 10), ("AA", 0.0015, 14), ("AA-", 0.002, 12),
           ("A+", 0.004, 10), ("A", 0.005, 10), ("A-", 0.006, 8), ("BBB+", 0.009, 6),
           ("BBB", 0.011, 6), ("BBB-", 0.013, 4), ("BB", 0.022, 2), ("NR", 0.020, 4)]
STATES = ["CA", "NY", "TX", "FL", "IL", "PA", "OH", "MA", "WA", "NJ", "CO", "GA", "AZ", "MI"]
PLACES = ["Alder", "Briar", "Cedar", "Dunmore", "Elmwood", "Fairhaven", "Granite", "Harlow",
          "Ironwood", "Juniper", "Kestrel", "Larkspur", "Millbrook", "Northgate", "Oakridge",
          "Pinecrest", "Quarry", "Redfield", "Stonebridge", "Thornton", "Upland", "Vale",
          "Westfield", "Yarrow"]
COUPON_MONTHS = [(6, 1), (1, 1), (2, 15), (3, 1), (4, 1), (5, 1)]


def cusip_check_digit(base8: str) -> str:
    total = 0
    for i, ch in enumerate(base8):
        if ch.isdigit():
            v = int(ch)
        elif ch.isalpha():
            v = ord(ch.upper()) - 55
        else:
            v = {"*": 36, "@": 37, "#": 38}[ch]
        if i % 2 == 1:
            v *= 2
        total += v // 10 + v % 10
    return str((10 - total % 10) % 10)


@dataclass
class SyntheticHolding:
    position: Position
    true_terms: InterestTerms
    vendor_a: SecurityRecord
    vendor_b: SecurityRecord | None
    history: list[PricePoint]
    market_yield: float


@dataclass
class PlantedDefect:
    defect_id: str
    cusip: str
    expected_rules: list[str]
    description: str
    true_terms: InterestTerms


@dataclass
class SyntheticDataset:
    as_of: date
    holdings: list[SyntheticHolding]
    defects: list[PlantedDefect] = field(default_factory=list)

    @property
    def defect_cusips(self) -> set[str]:
        return {d.cusip for d in self.defects}


def curve_yield(years: float) -> float:
    return 0.025 + 0.0011 * min(years, 25)


def clean_price(terms: InterestTerms, y: float, d: date) -> float:
    dirty = dirty_price_from_yield(cash_flows(terms, d), d, y, anchor=terms.maturity_date,
                                   frequency=terms.payment_frequency if terms.interest_type is InterestType.CURRENT_PAY else 2,
                                   day_count=terms.day_count)
    return dirty - accrued_interest(terms, d)


def dirty_value(terms: InterestTerms, y: float, d: date) -> float:
    return dirty_price_from_yield(cash_flows(terms, d), d, y, anchor=terms.maturity_date,
                                  day_count=terms.day_count)


class _Gen:
    def __init__(self, seed: int):
        self.r = random.Random(seed)
        self.used: set[str] = set()
        # Shared market rate path (monthly changes), oldest first, ending at 0 on AS_OF.
        steps = [self.r.gauss(0, 0.0012) for _ in range(11)]
        self.market = [sum(steps[i:]) for i in range(11)] + [0.0]

    def cusip(self) -> str:
        alnum = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        while True:
            issuer = "".join(self.r.choice(alnum) for _ in range(6))
            if issuer.startswith("34077"):
                continue
            base = issuer + self.r.choice("0123456789ABCDEFGH") + self.r.choice("0123456789")
            c = base + cusip_check_digit(base)
            if c not in self.used:
                self.used.add(c)
                return c

    def par(self, lo: int = 50, hi: int = 1000) -> float:
        return float(self.r.randint(lo, hi) * 5000)

    def history(self, cusip: str, price_fn, y_end: float, sigma: float, noise: float = 0.0) -> list[PricePoint]:
        """12 month-end points ending at AS_OF: shared market factor + idiosyncratic walk."""
        dates = [add_months(AS_OF, -k) for k in range(11, -1, -1)]
        idio = [0.0]
        for _ in range(11):
            idio.append(idio[-1] + self.r.gauss(0, sigma))
        idio.reverse()
        ys = [y_end + m + i for m, i in zip(self.market, idio)]
        return [PricePoint(cusip, d, round(price_fn(yv, d) + self.r.gauss(0, noise), 3))
                for d, yv in zip(dates, ys)]


def _record(vendor: str, cusip: str, desc: str, price: float, coupon: float, accrual: str,
            terms: InterestTerms, rating: str, sector: str, state: str, vy: float | None,
            convention: str = "clean", freq: int | None = 2) -> SecurityRecord:
    return SecurityRecord(vendor=vendor, cusip=cusip, description=desc, price=round(price, 3),
                          price_convention=convention, coupon=coupon, accrual_type=accrual,
                          maturity_date=terms.maturity_date, issue_date=terms.dated_date,
                          rating=rating, sector=sector, state=state, payment_frequency=freq,
                          day_count="30/360", vendor_yield=None if vy is None else round(vy, 5))


def _desc(g: _Gen, sector: str, coupon: float, mat: date, kind: str = "") -> str:
    place = g.r.choice(PLACES)
    word = {"General Obligation": "GO", "Water & Sewer": "Water & Swr Rev",
            "Transportation": "Transn Rev", "Hospital": "Hosp Rev", "Higher Education": "Univ Rev",
            "Housing": "Hsg Rev", "Public Power": "Pwr Rev", "Special Assessment": "Spl Assmt"}[sector]
    return f"{place} {word} {kind}{coupon * 100:.3f}% {mat:%m/%d/%Y}".replace("  ", " ")


def _clean_holding(g: _Gen, portfolio: str) -> SyntheticHolding:
    r = g.r
    sector = r.choice(list(SECTORS))
    rating, rspread, _ = r.choices(RATINGS, weights=[w for *_, w in RATINGS])[0]
    years = r.uniform(1.5, 30)
    m, d = r.choice(COUPON_MONTHS)
    mat_year = AS_OF.year + int(years) + (1 if (m, d) < (AS_OF.month, AS_OF.day) else 0)
    maturity = date(mat_year, m, d)
    orig_term = r.choice([10, 15, 20, 25, 30])
    issue = add_months(maturity, -12 * orig_term)
    if issue > AS_OF - timedelta(days=200):
        issue = add_months(maturity, -12 * (int((maturity - AS_OF).days / 365.25) + r.randint(1, 5)))
    yrs = (maturity - AS_OF).days / 365.25
    y = curve_yield(yrs) + rspread + SECTORS[sector] + r.gauss(0, 0.0008)
    is_cab = r.random() < 0.08
    if is_cab:
        terms = InterestTerms(InterestType.CAPITAL_APPRECIATION, round(y + r.uniform(-0.01, 0.01), 4),
                              issue, maturity)
        coupon, accrual = 0.0, "zero"
    else:
        coupon = r.choices([0.05, 0.04, 0.03, 0.025, 0.0525], weights=[50, 25, 12, 8, 5])[0]
        terms = InterestTerms(InterestType.CURRENT_PAY, coupon, issue, maturity)
        accrual = "fixed"
    cusip = g.cusip()
    price = clean_price(terms, y, AS_OF)
    desc = _desc(g, sector, coupon, maturity, "Cap Apprec " if is_cab else "")
    vy = None if r.random() < 0.1 else y
    state = r.choice(STATES)
    a = _record("VendorA", cusip, desc, price, coupon, accrual, terms, rating, sector, state, vy)
    b = None
    if r.random() < 0.95:
        b = replace(a, vendor="VendorB", price=round(price + r.uniform(-0.4, 0.4), 3),
                    accrual_type=accrual.upper(), vendor_yield=None)
    hist = g.history(cusip, lambda yv, dd: clean_price(terms, yv, dd), y, sigma=0.0002)
    return SyntheticHolding(Position(portfolio, cusip, g.par()), terms, a, b, hist, y)


def generate(seed: int = SEED, n_clean: int = 188) -> SyntheticDataset:
    g = _Gen(seed)
    holdings: list[SyntheticHolding] = []
    for i in range(n_clean):
        holdings.append(_clean_holding(g, "MUNI-NATL-02" if i % 3 else "MUNI-HY-01"))
    defects: list[PlantedDefect] = []

    def plant(defect_id, expected, description, terms, y, *, coupon, accrual, rating, sector, state,
              vy, par, b_overrides=None, b_present=True, price=None, hist_noise=0.02,
              hist_sigma=0.0002, desc_kind="", convention="clean"):
        cusip = g.cusip()
        p = price if price is not None else (
            dirty_value(terms, y, AS_OF) if terms.interest_type is InterestType.DEFERRED_INTEREST
            else clean_price(terms, y, AS_OF))
        desc = _desc(g, sector, coupon if coupon else terms.rate, terms.maturity_date, desc_kind)
        a = _record("VendorA", cusip, desc, p, coupon, accrual, terms, rating, sector, state, vy,
                    convention=convention)
        b = None
        if b_present:
            b = replace(a, vendor="VendorB", price=round(p + g.r.uniform(-0.25, 0.25), 3), vendor_yield=None,
                        **(b_overrides or {}))
        fn = ((lambda yv, dd: dirty_value(terms, yv, dd))
              if terms.interest_type is InterestType.DEFERRED_INTEREST
              else (lambda yv, dd: clean_price(terms, yv, dd)))
        hist = g.history(cusip, fn, y, sigma=hist_sigma, noise=hist_noise)
        if price is not None:  # history consistent with a mis-keyed final price
            hist[-1] = PricePoint(cusip, AS_OF, round(price, 3))
        holdings.append(SyntheticHolding(Position("MUNI-HY-01", cusip, par), terms, a, b, hist, y))
        defects.append(PlantedDefect(defect_id, cusip, expected, description, terms))

    D = date
    plant("D01-deferred-zero-clean",
          ["yield_coupon_impossibility", "zero_coupon_sanity", "price_drift"],
          "Mirrors the motivating case: vendor coupon 0, price labelled clean, but the bond "
          "accrues 11% compounded semiannually and pays all interest at maturity; ~11% yield.",
          InterestTerms(InterestType.DEFERRED_INTEREST, 0.11, D(2019, 7, 1), D(2034, 7, 1)),
          0.11, coupon=0.0, accrual="zero", rating="NR", sector="Special Assessment", state="FL",
          vy=0.11, par=4_000_000.0, desc_kind="Def Int ")
    plant("D02-coupon-understated", ["yield_coupon_impossibility"],
          "Vendor coupon 1.00% vs document 5.75% current pay; reported yield 6.25% impossible "
          "for a 1% coupon at this price.",
          InterestTerms(InterestType.CURRENT_PAY, 0.0575, D(2018, 12, 1), D(2041, 12, 1)),
          0.0625, coupon=0.01, accrual="fixed", rating="BBB", sector="Hospital", state="PA",
          vy=0.0625, par=2_500_000.0)
    plant("D03-deferred-drift", ["price_drift"],
          "Deferred-interest bond (6% compounded semiannually) carried as zero coupon with no "
          "vendor yield, priced below 95 so the zero-coupon screen is silent; the 'clean' price "
          "climbs with the embedded accrual.",
          InterestTerms(InterestType.DEFERRED_INTEREST, 0.06, D(2024, 6, 1), D(2033, 6, 1)),
          0.095, coupon=0.0, accrual="zero", rating="NR", sector="Housing", state="NV",
          vy=None, par=2_750_000.0, b_present=False, hist_sigma=0.0002, desc_kind="Def Int ")
    plant("D04-credit-outlier", ["peer_outlier"],
          "Terms are correct; yield 9.5% vs A-rated hospital peers near 5% (credit event, not a "
          "terms defect - expected reviewer rejection).",
          InterestTerms(InterestType.CURRENT_PAY, 0.05, D(2017, 6, 1), D(2039, 6, 1)),
          0.095, coupon=0.05, accrual="fixed", rating="A", sector="Hospital", state="OH",
          vy=0.095, par=1_000_000.0, hist_sigma=0.0002)
    plant("D05-price-typo", ["peer_outlier"],
          "Price mis-keyed as 72.000 (fair ~103); no vendor yield, implied yield far above peers.",
          InterestTerms(InterestType.CURRENT_PAY, 0.04, D(2020, 9, 1), D(2034, 9, 1)),
          0.0345, coupon=0.04, accrual="fixed", rating="AA", sector="General Obligation", state="WA",
          vy=None, par=1_500_000.0, price=72.0, hist_sigma=0.0002)
    plant("D06-vendor-coupon", ["vendor_disagreement"],
          "Vendor B carries coupon 0 / zero accrual; vendor A and document say 5% current pay.",
          InterestTerms(InterestType.CURRENT_PAY, 0.05, D(2019, 6, 1), D(2044, 6, 1)),
          0.042, coupon=0.05, accrual="fixed", rating="AA-", sector="Water & Sewer", state="TX",
          vy=0.042, par=2_000_000.0, b_overrides={"coupon": 0.0, "accrual_type": "zero"},
          hist_sigma=0.0002)
    plant("D07-vendor-convention", ["vendor_disagreement"],
          "Vendor B labels price dirty and accrual deferred; vendor A clean / fixed.",
          InterestTerms(InterestType.CURRENT_PAY, 0.04, D(2016, 3, 1), D(2036, 3, 1)),
          0.035, coupon=0.04, accrual="fixed", rating="AA", sector="Transportation", state="NY",
          vy=0.035, par=1_000_000.0,
          b_overrides={"price_convention": "dirty", "accrual_type": "deferred"}, hist_sigma=0.0002)
    plant("D08-vendor-schedule", ["vendor_disagreement"],
          "Vendor B pays annually; vendor A semiannually.",
          InterestTerms(InterestType.CURRENT_PAY, 0.05, D(2022, 1, 1), D(2047, 1, 1)),
          0.044, coupon=0.05, accrual="fixed", rating="A+", sector="Public Power", state="AZ",
          vy=0.044, par=750_000.0, b_overrides={"payment_frequency": 1}, hist_sigma=0.0002)
    plant("D09-zero-near-par", ["zero_coupon_sanity"],
          "Deferred-interest bond (4.5% compounded) carried as zero coupon priced above par with "
          "13 years to maturity; no vendor yield.",
          InterestTerms(InterestType.DEFERRED_INTEREST, 0.045, D(2025, 1, 1), D(2040, 1, 1)),
          0.0475, coupon=0.0, accrual="zero", rating="BBB-", sector="Housing", state="CO",
          vy=None, par=1_250_000.0, b_present=False, desc_kind="Def Int ")
    plant("D10-deferred-low-coupon", ["yield_coupon_impossibility"],
          "Deferred-interest bond (7% compounded) carried with a 2% coupon at ~196; a 2% coupon "
          "cannot yield 7.2% at that price.",
          InterestTerms(InterestType.DEFERRED_INTEREST, 0.07, D(2016, 6, 1), D(2036, 6, 1)),
          0.072, coupon=0.02, accrual="fixed", rating="BB", sector="Special Assessment", state="TX",
          vy=0.072, par=1_800_000.0, desc_kind="Def Int ")
    plant("D11-cab-as-current-pay", ["yield_coupon_impossibility"],
          "CAB (5.25% accreting) carried as a 5.25% current-pay bond; fund books coupon accrual "
          "that does not exist (income overstated).",
          InterestTerms(InterestType.CAPITAL_APPRECIATION, 0.0525, D(2015, 8, 1), D(2036, 8, 1)),
          0.0525, coupon=0.0525, accrual="fixed", rating="A-", sector="Higher Education", state="IL",
          vy=0.0525, par=2_200_000.0, desc_kind="Cap Apprec ")

    plant("D12-ccab-as-zero", ["peer_outlier"],
          "Convertible CAB (5.5% accreting to 2031 conversion, then current pay) carried as a "
          "zero-coupon bond with no vendor yield: implied yield ~1.4% vs peers ~5.5%.",
          InterestTerms(InterestType.CONVERTIBLE_CAB, 0.055, D(2021, 12, 1), D(2045, 12, 1),
                        conversion_date=D(2031, 12, 1)),
          0.055, coupon=0.0, accrual="zero", rating="A", sector="Higher Education", state="CA",
          vy=None, par=3_000_000.0, b_present=False, hist_sigma=0.0002, desc_kind="Conv Cap Apprec ")

    return SyntheticDataset(AS_OF, holdings, defects)


def to_screen_input(ds: SyntheticDataset):
    from .screens.models import ScreenInput
    return ScreenInput(
        as_of=ds.as_of,
        positions=[h.position for h in ds.holdings],
        primary={h.vendor_a.cusip: h.vendor_a for h in ds.holdings},
        secondary={h.vendor_b.cusip: h.vendor_b for h in ds.holdings if h.vendor_b},
        history={h.vendor_a.cusip: h.history for h in ds.holdings},
    )
