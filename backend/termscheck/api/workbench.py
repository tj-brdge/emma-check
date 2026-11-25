"""Endpoints that stitch the pipeline together for the UI."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from termscheck.db.models import (Document, Extraction, Finding, Holding, ScreenFlag, ScreenRun, VendorTerms)
from termscheck.extraction.llm import ExtractionLLM
from termscheck.extraction.sources import UploadSource
from termscheck.services.extraction import register_document, run_extraction
from termscheck.services.findings import FindingError, create_finding
from termscheck.api.deps import current_user, get_llm, get_session, get_store
from termscheck.api.documents import doc_json, extraction_json
from termscheck.api.findings import finding_json

router = APIRouter(prefix="/api", tags=["workbench"])


@router.get("/screen-runs/{run_id}/cusips")
def flagged_cusips(run_id: int, session: Session = Depends(get_session)):
    run = session.get(ScreenRun, run_id)
    if run is None:
        raise HTTPException(404, "screen run not found")
    flags = session.scalars(select(ScreenFlag).where(ScreenFlag.run_id == run_id)).all()
    by: dict[str, list[ScreenFlag]] = {}
    for f in flags:
        by.setdefault(f.cusip, []).append(f)
    vts = {v.cusip: v for v in session.scalars(select(VendorTerms).where(
        VendorTerms.batch_id == run.holdings_batch_id, VendorTerms.cusip.in_(list(by))))}
    pars: dict[str, float] = {}
    for h in session.scalars(select(Holding).where(Holding.batch_id == run.holdings_batch_id,
                                                   Holding.cusip.in_(list(by)))):
        pars[h.cusip] = pars.get(h.cusip, 0.0) + h.par
    out = []
    for cusip, fl in by.items():
        v = vts[cusip]
        doc = session.scalars(select(Document).where(Document.cusip == cusip).order_by(Document.id.desc())).first()
        ex = session.scalars(select(Extraction).where(Extraction.cusip == cusip).order_by(Extraction.id.desc())).first()
        fi = session.scalars(select(Finding).where(Finding.cusip == cusip, Finding.screen_run_id == run_id)
                             .order_by(Finding.id.desc())).first()
        out.append({
            "cusip": cusip, "description": v.description, "par": pars.get(cusip, 0.0),
            "price": v.price, "price_convention": v.price_convention, "coupon": v.coupon,
            "accrual_type": v.accrual_type, "vendor_yield": v.vendor_yield, "rating": v.rating,
            "sector": v.sector, "max_severity": max(f.severity for f in fl),
            "flags": [{"rule": f.rule, "severity": f.severity, "message": f.message} for f in
                      sorted(fl, key=lambda x: -x.severity)],
            "document_id": doc.id if doc else None,
            "extraction_id": ex.id if ex else None, "extraction_status": ex.status if ex else None,
            "finding_id": fi.id if fi else None, "finding_status": fi.status if fi else None,
            "income_impact_usd": fi.income_impact_usd if fi else None,
        })
    out.sort(key=lambda r: (-r["max_severity"], -len(r["flags"]), -r["par"]))
    return {"run": {"id": run.id, "as_of": run.as_of.isoformat(), "flag_count": run.flag_count}, "cusips": out}


@router.get("/cusips/{cusip}/flags")
def cusip_flags(cusip: str, run_id: int, session: Session = Depends(get_session)):
    return [{"rule": f.rule, "severity": f.severity, "message": f.message, "inputs": f.inputs,
             "computed": f.computed} for f in session.scalars(
        select(ScreenFlag).where(ScreenFlag.run_id == run_id, ScreenFlag.cusip == cusip.upper())
        .order_by(ScreenFlag.severity.desc()))]


@router.post("/screen-runs/{run_id}/cusips/{cusip}/official-statement")
async def analyse_official_statement(run_id: int, cusip: str, file: UploadFile = File(...),
                                     user: str = Depends(current_user), session: Session = Depends(get_session),
                                     store: UploadSource = Depends(get_store), llm: ExtractionLLM = Depends(get_llm)):
    """Upload the OS for a flagged CUSIP, extract terms, and build the finding in one step.
    Each step is persisted (and audited) on its own; a failed extraction is kept for review."""
    cusip = cusip.upper()
    content = await file.read()
    try:
        doc = register_document(session, store, cusip=cusip, filename=file.filename or "os.pdf",
                                content=content, user=user)
    except ValueError as e:
        session.rollback()
        raise HTTPException(422, str(e))
    session.commit()
    ex = run_extraction(session, document_id=doc.id, llm=llm, user=user, cusip=cusip)
    session.commit()
    out = {"document": doc_json(doc), "extraction": extraction_json(ex), "finding": None, "error": None}
    if ex.status != "failed":
        try:
            f = create_finding(session, screen_run_id=run_id, extraction_id=ex.id, user=user)
            session.commit()
            out["finding"] = finding_json(f, detail=True)
        except FindingError as e:
            session.rollback()
            out["error"] = str(e)
    else:
        out["error"] = ex.error
    return out
