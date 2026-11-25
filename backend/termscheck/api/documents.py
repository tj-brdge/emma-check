from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from termscheck.db.models import Document, Extraction
from termscheck.extraction.llm import ExtractionLLM
from termscheck.extraction.sources import UploadSource
from termscheck.services.extraction import document_pages, register_document, run_extraction
from termscheck.api.deps import current_user, get_llm, get_session, get_store, read_limited
from termscheck.settings import settings

router = APIRouter(prefix="/api", tags=["documents"])


def doc_json(d: Document) -> dict:
    return {"id": d.id, "cusip": d.cusip, "doc_kind": d.doc_kind, "asset_class": d.asset_class, "source": d.source, "filename": d.filename, "sha256": d.sha256,
            "page_count": d.page_count, "uploaded_by": d.uploaded_by,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None}


def extraction_json(e: Extraction) -> dict:
    return {"id": e.id, "document_id": e.document_id, "cusip": e.cusip, "status": e.status,
            "model_requested": e.model_requested, "model_served": e.model_served,
            "prompt_version": e.prompt_version, "terms": e.terms, "citation_checks": e.citation_checks,
            "interest_terms": e.interest_terms, "problems": e.problems, "page_selection": e.page_selection,
            "llm_meta": e.llm_meta, "error": e.error, "created_by": e.created_by,
            "created_at": e.created_at.isoformat() if e.created_at else None}


@router.post("/documents")
def upload_document(cusip: str = Form(...), file: UploadFile = File(...),
                          doc_kind: str | None = Form(None), asset_class: str | None = Form(None),
                          user: str = Depends(current_user), session: Session = Depends(get_session),
                          store: UploadSource = Depends(get_store)):
    content = read_limited(file, max(settings.max_pdf_bytes, settings.max_data_bytes))
    try:
        doc = register_document(session, store, cusip=cusip.strip().upper(),
                                filename=file.filename or "official_statement.pdf", content=content, user=user,
                                doc_kind=doc_kind, asset_class=asset_class)
    except (ValueError, KeyError) as e:
        session.rollback()
        raise HTTPException(422, str(e))
    session.commit()
    return doc_json(doc)


@router.get("/documents")
def list_documents(cusip: str | None = None, session: Session = Depends(get_session)):
    q = select(Document).order_by(Document.id.desc())
    if cusip:
        q = q.where(Document.cusip == cusip.upper())
    return [doc_json(d) for d in session.scalars(q)]


@router.get("/documents/{doc_id}/pages/{page_no}")
def get_page(doc_id: int, page_no: int, session: Session = Depends(get_session)):
    pages = document_pages(session, doc_id)
    if not 1 <= page_no <= len(pages):
        raise HTTPException(404, "page not found")
    return {"document_id": doc_id, "page_no": page_no, "text": pages[page_no - 1]}


@router.get("/documents/{doc_id}/file")
def get_file(doc_id: int, session: Session = Depends(get_session), store: UploadSource = Depends(get_store)):
    d = session.get(Document, doc_id)
    if d is None:
        raise HTTPException(404, "document not found")
    content = (store.root / f"{d.sha256}.pdf").read_bytes()
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{d.filename}"'})


class ExtractionRequest(BaseModel):
    document_id: int
    cusip: str | None = None
    model: str | None = None


@router.post("/extractions")
def create_extraction(req: ExtractionRequest, user: str = Depends(current_user),
                      session: Session = Depends(get_session), llm: ExtractionLLM = Depends(get_llm)):
    try:
        ex = run_extraction(session, document_id=req.document_id, llm=llm, user=user, cusip=req.cusip,
                            model=req.model)
    except ValueError as e:
        session.rollback()
        raise HTTPException(422 if 'data file' in str(e) else 404, str(e))
    session.commit()
    return extraction_json(ex)


@router.get("/extractions/{ex_id}")
def get_extraction(ex_id: int, session: Session = Depends(get_session)):
    e = session.get(Extraction, ex_id)
    if e is None:
        raise HTTPException(404, "extraction not found")
    return extraction_json(e)


@router.get("/extractions")
def list_extractions(cusip: str | None = None, session: Session = Depends(get_session)):
    q = select(Extraction).order_by(Extraction.id.desc())
    if cusip:
        q = q.where(Extraction.cusip == cusip.upper())
    return [extraction_json(e) for e in session.scalars(q)]


@router.get("/cusips/{cusip}/disclosures")
def cusip_disclosures(cusip: str, session: Session = Depends(get_session)):
    from ..db.models import DisclosureObservation
    rows = session.scalars(select(DisclosureObservation).where(DisclosureObservation.cusip == cusip.upper())
                           .order_by(DisclosureObservation.document_id.desc(), DisclosureObservation.month)).all()
    return [{"document_id": r.document_id, "month": r.month.isoformat(), "factor": r.factor,
             "net_coupon": r.net_coupon, "locator": r.locator} for r in rows]
