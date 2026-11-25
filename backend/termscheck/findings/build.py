"""Build a finding for one CUSIP: vendor data vs. document terms, correct treatment, and the
income impact across positions. Pure functions; narratives are deterministic templates over
computed numbers (no LLM), so every figure in a finding is reproducible."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..bondmath import InterestTerms, InterestType, Treatment, VendorView, compute_treatment
from ..screens.models import Position, SecurityRecord

TYPE_LABEL = {
    InterestType.CURRENT_PAY: "current-pay",
    InterestType.CAPITAL_APPRECIATION: "capital appreciation (CAB)",
    InterestType.DEFERRED_INTEREST: "deferred-interest",
    InterestType.CONVERTIBLE_CAB: "convertible capital appreciation",
}
FREQ = {0: "simple (no compounding)", 1: "annually", 2: "semiannually", 4: "quarterly", 12: "monthly"}


@dataclass
class PositionImpact:
    portfolio: str
    par: float
    treatment: Treatment


@dataclass
class FindingDraft:
    cusip: str
    description: str
    as_of: date
    income_impact_usd: float
    run_rate_gap_usd: float
    headline: str
    vendor_says: str
    document_says: str
    correct_treatment: str
    impact: str
    comparison: list[dict[str, Any]]
    positions: list[PositionImpact]
    treatment: Treatment                  # per-100 treatment (identical across positions)
    rules: list[str] = field(default_factory=list)


def vendor_interest_type(rec: SecurityRecord) -> str:
    label = rec.accrual_type.lower()
    if label in ("deferred", "deferred_interest"):
        return "deferred_interest"
    if label in ("cab", "accreting", "capital_appreciation"):
        return "capital_appreciation"
    if rec.coupon <= 0 or label == "zero":
        return "zero coupon"
    return "current_pay"


def _cite(citations: dict[str, dict] | None, f: str) -> str:
    if not citations or f not in citations or not citations[f].get("page"):
        return ""
    return f" (p. {citations[f]['page']})"


def comparison_rows(rec: SecurityRecord, terms: InterestTerms, citations: dict | None) -> list[dict]:
    c = citations or {}

    def row(name, vendor, doc, field_name, match=None):
        if match is None:
            match = vendor == doc
        return {"field": name, "vendor": vendor, "document": doc, "match": match,
                "page": c.get(field_name, {}).get("page"), "excerpt": c.get(field_name, {}).get("excerpt"),
                "citation_status": c.get(field_name, {}).get("status")}

    pays_current = terms.interest_type in (InterestType.CURRENT_PAY, InterestType.CONVERTIBLE_CAB)
    return [
        row("Interest type", vendor_interest_type(rec), terms.interest_type.value, "interest_type"),
        row("Coupon / accretion rate", f"{rec.coupon * 100:.3f}%", f"{terms.rate * 100:.3f}%",
            "interest_rate_pct", abs(rec.coupon - terms.rate) < 1e-9),
        row("Compounding", "n/a", FREQ.get(terms.compounding_frequency, "?") if not
            terms.interest_type is InterestType.CURRENT_PAY else "n/a", "compounding_frequency", None),
        row("Day count", rec.day_count or "not supplied", terms.day_count.value, "day_count",
            (rec.day_count or terms.day_count.value).upper() == terms.day_count.value.upper()),
        row("Accrual start", rec.issue_date.isoformat(), terms.dated_date.isoformat(), "accrual_start_date"),
        row("Maturity", rec.maturity_date.isoformat(), terms.maturity_date.isoformat(), "maturity_date"),
        row("Payment frequency", str(rec.payment_frequency or "not supplied"),
            str(terms.payment_frequency) if pays_current else "at maturity", "payment_frequency",
            (str(rec.payment_frequency) == str(terms.payment_frequency)) if pays_current else rec.coupon == 0),
        row("Conversion date", "n/a", terms.conversion_date.isoformat() if terms.conversion_date else "n/a",
            "conversion_date", terms.conversion_date is None),
    ]


def _treatment_text(t: Treatment, terms: InterestTerms, rec: SecurityRecord) -> str:
    it = terms.interest_type
    if it is InterestType.DEFERRED_INTEREST:
        return (f"Interest accrues from {terms.dated_date:%b %d, %Y} at {terms.rate:.3%}, compounding "
                f"{FREQ[terms.compounding_frequency]}, and is paid only at maturity. At {t.as_of:%b %d, %Y} "
                f"the accreted value is {t.accreted_value:.4f} per 100, of which {t.true_accrued:.4f} is "
                f"accrued, unpaid interest. The vendor price {rec.price:.3f} ({rec.price_convention}) is a "
                f"full price: correct clean price {t.correct_clean:.4f} plus accrued {t.true_accrued:.4f}. "
                "Fund accounting should accrue the interest as tax-exempt income and carry it as interest "
                "receivable, not as unrealized appreciation.")
    if it is InterestType.CAPITAL_APPRECIATION:
        return (f"No periodic interest. The bond accretes from {terms.dated_date:%b %d, %Y} at "
                f"{terms.rate:.3%} compounding {FREQ[terms.compounding_frequency]}; accreted value at "
                f"{t.as_of:%b %d, %Y} is {t.accreted_value:.4f} per 100 of maturity value. There is no "
                "accrued coupon: income is recognised by accreting the discount. Any coupon accrual booked "
                f"from vendor terms ({t.vendor_accrued:.4f} per 100) should be reversed.")
    if it is InterestType.CONVERTIBLE_CAB:
        conv = terms.conversion_date
        phase = ("accreting" if t.as_of < conv else "paying current interest")
        return (f"Accretes at {terms.rate:.3%} compounding {FREQ[terms.compounding_frequency]} until the "
                f"{conv:%b %d, %Y} conversion date, then pays {terms.rate:.3%} on par "
                f"{terms.payment_frequency}x a year. At {t.as_of:%b %d, %Y} the bond is {phase}; accreted "
                f"value {t.accreted_value:.4f} per 100, accrued coupon {t.true_accrued:.4f}. Income before "
                "conversion is recognised as accretion (original-issue schedule).")
    return (f"Current-pay {terms.rate:.3%} coupon, {terms.payment_frequency}x a year, "
            f"{terms.day_count.value}. Accrued interest at {t.as_of:%b %d, %Y} is {t.true_accrued:.4f} per "
            f"100; correct clean price {t.correct_clean:.4f}.")


def build_finding(rec: SecurityRecord, positions: list[Position], terms: InterestTerms, as_of: date,
                  *, citations: dict[str, dict] | None = None, rules: list[str] | None = None) -> FindingDraft:
    if not positions:
        raise ValueError(f"no positions held in {rec.cusip}")
    vendor = VendorView(rec.price, rec.price_convention, rec.coupon, rec.accrual_type)
    impacts = [PositionImpact(p.portfolio, p.par, compute_treatment(terms, vendor, p.par, as_of,
                                                                    window_start=p.acquisition_date))
               for p in positions]
    total_par = sum(p.par for p in positions)
    t = compute_treatment(terms, vendor, 100.0, as_of)  # per-100 view for narrative
    usd = sum(i.treatment.unbooked_income_usd for i in impacts)

    yv = t.yield_vendor_terms
    vendor_says = (f"{rec.vendor} carries {rec.cusip} as {vendor_interest_type(rec).replace('_', ' ')} "
                   f"with a {rec.coupon:.3%} coupon (accrual type '{rec.accrual_type}'), price "
                   f"{rec.price:.3f} labelled {rec.price_convention}. Under those terms the price implies "
                   f"a {'n/a' if yv is None else f'{yv:.2%}'} yield"
                   + (f"; the vendor reports {rec.vendor_yield:.2%}." if rec.vendor_yield is not None else ".")
                   + f" Accrued interest booked from vendor terms: {t.vendor_accrued:.4f} per 100.")
    c = citations
    doc_bits = [f"a {TYPE_LABEL[terms.interest_type]} bond{_cite(c, 'interest_type')}",
                f"rate {terms.rate:.3%}{_cite(c, 'interest_rate_pct')}"]
    if terms.interest_type is not InterestType.CURRENT_PAY:
        doc_bits.append(f"compounding {FREQ[terms.compounding_frequency]}{_cite(c, 'compounding_frequency')}")
    doc_bits += [f"accruing from {terms.dated_date:%b %d, %Y}{_cite(c, 'accrual_start_date')}",
                 f"maturing {terms.maturity_date:%b %d, %Y}{_cite(c, 'maturity_date')}",
                 f"day count {terms.day_count.value}{_cite(c, 'day_count')}"]
    if terms.conversion_date:
        doc_bits.append(f"converting {terms.conversion_date:%b %d, %Y}{_cite(c, 'conversion_date')}")
    yd = t.yield_document_terms
    document_says = ("The official statement describes " + ", ".join(doc_bits) + ". "
                     + (f"At the vendor's price, document terms imply a {yd:.2%} yield." if yd is not None else ""))

    vt = vendor_interest_type(rec)
    if vt == terms.interest_type.value and abs(rec.coupon - terms.rate) > 1e-9:
        what = f"coupon {rec.coupon:.3%} vs document {terms.rate:.3%}"
    else:
        what = f"{vt.replace('_', ' ')} vs {TYPE_LABEL[terms.interest_type]}"
    if abs(usd) < 0.5:
        impact = (f"No income impact: document terms and vendor terms produce the same accrual on "
                  f"${total_par:,.0f} par.")
        headline = "Vendor terms consistent with document; no income impact"
    elif usd > 0:
        impact = (f"Income understated by ${usd:,.0f} on ${total_par:,.0f} par "
                  f"({t.unbooked_per_100:.4f} per 100): that amount sits in the vendor price but is "
                  "carried as principal / unrealized appreciation instead of accrued interest income.")
        headline = f"Unbooked income ${usd:,.0f}: {what}"
    else:
        impact = (f"Income overstated by ${-usd:,.0f} on ${total_par:,.0f} par "
                  f"({-t.unbooked_per_100:.4f} per 100): accrual booked from vendor terms does not exist "
                  "under the document terms.")
        headline = f"Overbooked income ${-usd:,.0f}: {what}"
    rr = sum(i.treatment.run_rate_gap_usd for i in impacts)
    if abs(rr) >= 0.5:
        impact += (f" Next 12 months: document terms earn {t.income_next_12m_document:.4f} per 100 vs "
                   f"{t.income_next_12m_vendor:.4f} booked from vendor terms, a run-rate "
                   f"{'shortfall' if rr > 0 else 'overstatement'} of ${abs(rr):,.0f}.")
        if abs(usd) < 0.5:
            headline = f"Income run-rate {'understated' if rr > 0 else 'overstated'} ${abs(rr):,.0f}/yr: {what}"
    windows = [i for i in impacts if i.treatment.unbooked_window_usd is not None]
    if windows:
        w = sum(i.treatment.unbooked_window_usd for i in windows)
        impact += f" Since acquisition: ${w:,.0f} for positions with an acquisition date."

    return FindingDraft(rec.cusip, rec.description, as_of, usd, rr, headline, vendor_says, document_says,
                        _treatment_text(t, terms, rec), impact, comparison_rows(rec, terms, citations),
                        impacts, t, rules or [])
