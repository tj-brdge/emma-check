from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from termscheck.audit import record
from termscheck.db.models import LedgerRow, Computation, Extraction, Finding, Holding, ScreenFlag, ScreenRun, VendorTerms
from termscheck.core.plugin import get_plugin
from termscheck.core.records import LedgerEntry
from termscheck.screens import Position
from termscheck.services.extraction import citation_index
from termscheck.services.screening import latest_disclosures, to_record
from termscheck.services.serialize import jsonable


class FindingError(ValueError):
    pass


def create_finding(session: Session, *, screen_run_id: int, extraction_id: int, user: str) -> Finding:
    run = session.get(ScreenRun, screen_run_id)
    ex = session.get(Extraction, extraction_id)
    if run is None or ex is None:
        raise FindingError("screen run or extraction not found")
    if ex.status == "failed" or not ex.interest_terms:
        raise FindingError(f"extraction {ex.id} has no usable terms ({ex.status}): {ex.error or ex.problems}")
    vt = session.scalars(select(VendorTerms).where(VendorTerms.batch_id == run.holdings_batch_id,
                                                   VendorTerms.cusip == ex.cusip)).first()
    holdings = session.scalars(select(Holding).where(Holding.batch_id == run.holdings_batch_id,
                                                     Holding.cusip == ex.cusip)).all()
    if vt is None or not holdings:
        raise FindingError(f"{ex.cusip} is not held in screen run {run.id}")
    rules = sorted({f.rule for f in session.scalars(
        select(ScreenFlag).where(ScreenFlag.run_id == run.id, ScreenFlag.cusip == ex.cusip))})
    plugin = get_plugin(ex.asset_class)
    terms = plugin.terms_from_json(ex.interest_terms)
    cites = citation_index(ex)
    draft = plugin.build_finding(to_record(vt), [Position(h.portfolio, h.cusip, h.par, h.acquisition_date)
                                                 for h in holdings], terms, run.as_of, citations=cites, rules=rules,
                                 ledger=ledger_for(session, run, ex.cusip),
                                 context={"observations": latest_disclosures(session, {ex.cusip}, run.as_of)[0]
                                          .get(ex.cusip, []),
                                          "sources": sources_for(session, run, ex.cusip)})
    finding = Finding(
        cusip=ex.cusip, asset_class=ex.asset_class, description=vt.description, as_of=run.as_of, screen_run_id=run.id,
        extraction_id=ex.id, income_impact_usd=round(draft.income_impact_usd, 2),
        run_rate_gap_usd=round(draft.run_rate_gap_usd, 2), headline=draft.headline,
        narrative={"vendor_says": draft.vendor_says, "document_says": draft.document_says,
                   "correct_treatment": draft.correct_treatment, "impact": draft.impact,
                   "extraction_status": ex.status, "extraction_problems": ex.problems or [],
                   "metrics": jsonable(draft.metrics),
                   "schedule": jsonable(draft.schedule), "schedule_label": draft.schedule_label,
                   "notes": draft.notes},
        comparison=draft.comparison, rules=rules, status="open", created_by=user)
    session.add(finding)
    session.flush()
    comps = []
    for h, pi in zip(holdings, draft.positions):  # plugin returns positions in input order
        comps.append(Computation(
            finding_id=finding.id, extraction_id=ex.id, holding_id=h.id, as_of=run.as_of,
            inputs=jsonable({"terms": ex.interest_terms, "vendor": {
                "price": vt.price, "price_convention": vt.price_convention, "coupon": vt.coupon,
                "accrual_type": vt.accrual_type}, "par": h.par, "acquisition_date": h.acquisition_date}),
            outputs=pi.outputs,
            bondmath_version=plugin.math_version))
    session.add_all(comps)
    session.flush()
    for c in comps:
        record(session, actor=user, event_type="computation.created", entity_type="computation", entity_id=c.id,
               payload={"finding_id": finding.id, "cusip": finding.cusip, "holding_id": c.holding_id,
                        "as_of": c.as_of, "bondmath_version": c.bondmath_version, "inputs": c.inputs,
                        "outputs": c.outputs})
    record(session, actor=user, event_type="finding.created", entity_type="finding", entity_id=finding.id,
           payload={"cusip": finding.cusip, "screen_run_id": run.id, "extraction_id": ex.id,
                    "income_impact_usd": finding.income_impact_usd, "run_rate_gap_usd": finding.run_rate_gap_usd,
                    "headline": finding.headline, "rules": rules, "computation_ids": [c.id for c in comps]})
    return finding


def ledger_for(session: Session, run: ScreenRun, cusip: str) -> list[LedgerEntry]:
    """Cash ledger entries for the CUSIP from the run's ledger batch."""
    if run.ledger_batch_id is None:
        return []
    return [LedgerEntry(r.portfolio, r.cusip, r.entry_date, r.cash, r.kind, r.booked_income)
            for r in session.scalars(select(LedgerRow).where(LedgerRow.batch_id == run.ledger_batch_id,
                                                             LedgerRow.cusip == cusip).order_by(LedgerRow.id))]


def sources_for(session: Session, run: ScreenRun, cusip: str) -> list:
    """Book record plus every vendor record for the CUSIP that the run screened."""
    out = []
    for bid in [run.holdings_batch_id, run.secondary_batch_id, *(run.vendor_batch_ids or [])]:
        if bid is None:
            continue
        v = session.scalars(select(VendorTerms).where(VendorTerms.batch_id == bid, VendorTerms.cusip == cusip)).first()
        if v is not None:
            out.append(to_record(v))
    return out
