from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record
from ..bondmath import BONDMATH_VERSION
from ..db.models import Computation, Extraction, Finding, Holding, ScreenFlag, ScreenRun, VendorTerms
from ..findings import build_finding
from ..screens import Position
from .extraction import citation_index
from .screening import to_record
from .serialize import jsonable, terms_from_dict


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
    terms = terms_from_dict(ex.interest_terms)
    cites = citation_index(ex)
    draft = build_finding(to_record(vt), [Position(h.portfolio, h.cusip, h.par, h.acquisition_date)
                                          for h in holdings], terms, run.as_of, citations=cites, rules=rules)
    finding = Finding(
        cusip=ex.cusip, description=vt.description, as_of=run.as_of, screen_run_id=run.id,
        extraction_id=ex.id, income_impact_usd=round(draft.income_impact_usd, 2),
        run_rate_gap_usd=round(draft.run_rate_gap_usd, 2), headline=draft.headline,
        narrative={"vendor_says": draft.vendor_says, "document_says": draft.document_says,
                   "correct_treatment": draft.correct_treatment, "impact": draft.impact,
                   "extraction_status": ex.status, "extraction_problems": ex.problems or [],
                   "per_100": jsonable({k: getattr(draft.treatment, k) for k in (
                       "accreted_value", "true_accrued", "vendor_accrued", "full_value", "correct_clean",
                       "correct_dirty", "vendor_clean", "yield_document_terms", "yield_vendor_terms",
                       "unbooked_per_100", "income_next_12m_document", "income_next_12m_vendor")}),
                   "schedule": jsonable(draft.treatment.schedule),
                   "notes": draft.treatment.notes},
        comparison=draft.comparison, rules=rules, status="open", created_by=user)
    session.add(finding)
    session.flush()
    comps = []
    for h, pi in zip(holdings, draft.positions):
        comps.append(Computation(
            finding_id=finding.id, extraction_id=ex.id, holding_id=h.id, as_of=run.as_of,
            inputs=jsonable({"terms": ex.interest_terms, "vendor": {
                "price": vt.price, "price_convention": vt.price_convention, "coupon": vt.coupon,
                "accrual_type": vt.accrual_type}, "par": h.par, "acquisition_date": h.acquisition_date}),
            outputs=jsonable({k: v for k, v in vars(pi.treatment).items() if k != "schedule"}),
            bondmath_version=BONDMATH_VERSION))
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
