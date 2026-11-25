"""Agency MBS finding: book vs offering document and pool disclosure, cash evidence, income impact.
Narratives are templates over computed numbers (no LLM)."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any

from termscheck.core.display import pct, show
from termscheck.core.findings import FindingDraft, Metric, PositionResult
from termscheck.core.records import LedgerEntry, PeriodObservation, Position, SecurityRecord
from termscheck.plugins.agency_mbs.extraction.spec import terms_from_json
from termscheck.plugins.agency_mbs.treatment import compute_mbs_treatment

RATE_LABEL = {"fixed": "fixed net coupon", "wac": "WAC-based variable net coupon", "arm": "ARM (index + margin)"}


def _jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_jsonable(v) for v in x]
    if isinstance(x, date):
        return x.isoformat()
    return x


def _cite(c: dict | None, f: str) -> str:
    if c and c.get(f, {}).get("page"):
        return f" (p. {c[f]['page']})"
    return ""


def build_mbs_finding(rec: SecurityRecord, positions: list[Position], terms_json: dict, as_of: date, *,
                      citations: dict | None = None, rules: list[str] | None = None,
                      ledger: list[LedgerEntry] | None = None, observations: list[PeriodObservation] | None = None,
                      sources: list[SecurityRecord] | None = None) -> FindingDraft:
    if not positions:
        raise ValueError(f"no positions held in {rec.cusip}")
    terms = terms_from_json(terms_json, observations or ())
    treated = [(p, compute_mbs_treatment(terms, rec, p, as_of, ledger)) for p in positions]
    t = treated[0][1]
    usd = sum(tr.unbooked_window_usd for _, tr in treated)
    rr = sum(tr.run_rate_gap_usd for _, tr in treated)
    cash = sum(tr.cash_window for _, tr in treated)
    face = sum(tr.current_face for _, tr in treated)
    rt = terms_json["rate_type"]
    disc_rate = next((o for o in sorted(observations or [], key=lambda o: o.month, reverse=True)
                      if o.net_coupon is not None and o.month <= as_of.replace(day=1)), None)

    others = [s for s in (sources or []) if s.vendor != rec.vendor]
    vendor_says = (f"{rec.vendor} (book of record) carries {rec.cusip} with coupon {pct(rec, 'coupon')}, rate type "
                   f"{show(rec, 'rate_type')}, payment frequency {show(rec, 'payment_frequency')}, delay "
                   f"{show(rec, 'payment_delay_days', '{} days')}, factor {show(rec, 'factor', '{:.8f}')}. "
                   + " ".join(f"{s.vendor}: coupon {pct(s, 'coupon')}." for s in others)
                   + f" Income booked from these terms over the window: ${sum(sum(r['booked'] for r in tr.schedule) for _, tr in treated):,.2f}.")
    c = citations
    bits = [f"a {RATE_LABEL.get(rt, rt)}{_cite(c, 'rate_type')}"]
    if terms_json.get("net_coupon") is not None:
        bits.append(f"stated net coupon {terms_json['net_coupon']:.3%}{_cite(c, 'net_coupon_pct')}")
    if terms_json.get("reset_rule"):
        bits.append(f"reset rule: “{terms_json['reset_rule']}”{_cite(c, 'reset_rule')}")
    bits.append(f"{terms_json['payment_delay_days']}-day payment delay{_cite(c, 'payment_delay_days')}")
    bits.append(f"30/360 monthly accrual{_cite(c, 'day_count')}")
    document_says = "The offering circular supplement describes " + ", ".join(bits) + "."
    if disc_rate is not None:
        document_says += (f" The pool disclosure shows a net coupon of {disc_rate.net_coupon:.3%} for "
                          f"{disc_rate.month:%b %Y} and factor {t.current_factor:.8f} ({disc_rate.source}).")
    if t.cash_implied_rate is not None:
        document_says += (f" Interest cash received over {t.months} months (${cash:,.2f}) implies "
                          f"{t.cash_implied_rate:.3%} on current face.")

    rec_docs = [tr.receivable_document for _, tr in treated]
    rec_doc_txt = "unknown (missing rate or factor)" if any(v is None for v in rec_docs) else f"${sum(rec_docs):,.2f}"
    treatment_txt = (f"Interest accrues monthly on current face (original face x factor = ${face:,.2f}) at the "
                     f"month's net coupon ({'n/a' if t.current_rate is None else f'{t.current_rate:.3%}'} for "
                     f"{as_of:%b %Y}) on a 30/360 basis, and is paid {terms.payment_delay_days} days after the start "
                     f"of the accrual month. At {as_of:%b %d, %Y} interest receivable is "
                     f"{rec_doc_txt} "
                     f"vs ${sum(tr.receivable_book for _, tr in treated):,.2f} accrued by the book. Fund accounting should "
                     f"carry the {'monthly-reset ' if rt != 'fixed' else ''}net coupon from the pool disclosure and accrue "
                     "interest monthly; interest cash should be applied against interest receivable, not principal.")
    if usd > 0.5:
        impact = (f"Income understated by ${usd:,.2f} from {t.window_start:%b %Y} through {as_of:%b %d, %Y} "
                  f"({t.months} accrual months) on ${face:,.0f} current face.")
        headline_amt = f"Unbooked income ${usd:,.0f}"
    elif usd < -0.5:
        impact = f"Income overstated by ${-usd:,.2f} from {t.window_start:%b %Y} through {as_of:%b %d, %Y}."
        headline_amt = f"Overbooked income ${-usd:,.0f}"
    else:
        impact = "No income impact: book accrual matches the document terms over the window."
        headline_amt = "No income impact"
    if abs(rr) >= 0.5:
        impact += f" Forward 12-month run-rate {'shortfall' if rr > 0 else 'overstatement'}: ${abs(rr):,.0f}."
    if t.expected_cash_window is not None:
        impact += (f" Cash check: ${t.cash_window:,.2f} received vs ${t.expected_cash_window:,.2f} expected under "
                   "document terms for the same months.")
    book_txt = pct(rec, "coupon")
    doc_txt = "n/a" if t.current_rate is None else f"{t.current_rate:.3%}"
    headline = f"{headline_amt}: book coupon {book_txt} vs {RATE_LABEL.get(rt, rt)} {doc_txt}" + \
               (" (confirmed by cash)" if t.cash_implied_rate is not None and t.current_rate is not None
                and abs(t.cash_implied_rate - t.current_rate) < 0.0015 else "")

    def row(name, vendor, doc, field_name, match, locator=None):
        cc = (c or {}).get(field_name, {})
        return {"field": name, "vendor": vendor, "document": doc, "match": match, "page": cc.get("page"),
                "excerpt": cc.get("excerpt"), "citation_status": cc.get("status"), "locator": locator,
                "other_sources": {s.vendor: show(s, field_name if field_name in ("coupon", "factor") else "coupon")
                                  for s in others} if field_name in ("coupon",) else None}

    comparison = [
        row("Net coupon (current month)", book_txt, doc_txt, "net_coupon_pct",
            rec.coupon is not None and t.current_rate is not None and abs(rec.coupon - t.current_rate) < 5e-5,
            disc_rate.source if disc_rate else None),
        row("Rate type", show(rec, "rate_type"), rt, "rate_type", (rec.rate_type or "") == rt),
        row("Payment delay", show(rec, "payment_delay_days", "{} days"), f"{terms.payment_delay_days} days",
            "payment_delay_days", rec.payment_delay_days == terms.payment_delay_days),
        row("Payment frequency", show(rec, "payment_frequency"), "12", "payment_frequency", rec.payment_frequency == 12),
        row("Day count", show(rec, "day_count"), "30/360", "day_count", (rec.day_count or "30/360") == "30/360"),
        row("Factor", show(rec, "factor", "{:.8f}"), f"{t.current_factor:.8f}", "current_factor",
            rec.factor is not None and abs(rec.factor - t.current_factor) < 5e-7),
        row("Maturity", rec.maturity_date.isoformat(), terms.maturity_date.isoformat(), "maturity_date",
            rec.maturity_date == terms.maturity_date),
    ]
    pos = [PositionResult(p.portfolio, p.par, tr.unbooked_window_usd, tr.run_rate_gap_usd, tr.unbooked_window_usd,
                          _jsonable({k: v for k, v in asdict(tr).items() if k != "schedule"}) |
                          {"unbooked_income_usd": tr.unbooked_window_usd, "par": p.par})
           for p, tr in treated]
    metrics = [
        Metric("Unbooked over window", usd, "usd", True),
        Metric("Interest receivable · document", t.receivable_document, "usd"),
        Metric("Interest receivable · book", t.receivable_book, "usd"),
        Metric("Net coupon · document", t.current_rate, "pct"),
        Metric("Coupon · book", t.book_rate, "pct"),
        Metric("Cash-implied rate", t.cash_implied_rate, "pct"),
        Metric("Current factor", t.current_factor, "num4"),
        Metric("Current face", face, "usd"),
        Metric("Accrued per 100 (settlement)", t.accrued_per_100, "num4"),
        Metric("Clean / full per 100", t.full_per_100, "num4"),
    ]
    return FindingDraft(rec.cusip, "agency_mbs", rec.description, as_of, usd, rr, headline, vendor_says, document_says,
                        treatment_txt, impact, comparison, pos, metrics, schedule=t.schedule,
                        schedule_label="Monthly accrual vs book vs cash", notes=t.notes, rules=rules or [], treatment=t)
