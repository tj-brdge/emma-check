from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Document, DocumentPage, Extraction
from ..extraction import ExtractionLLMError, extract_terms_from_pages
from ..extraction.llm import ExtractionLLM
from ..extraction.pdf import extract_pages
from ..extraction.sources import UploadSource
from ..settings import settings
from .serialize import jsonable


def register_document(session: Session, store: UploadSource, *, cusip: str, filename: str,
                      content: bytes, user: str) -> Document:
    ref = store.put(cusip, filename, content)
    pages = extract_pages(content)
    doc = Document(cusip=cusip.upper(), source=store.name, source_ref=ref.ref, filename=filename,
                   sha256=ref.ref, page_count=len(pages), storage_path=str(store.root / f"{ref.ref}.pdf"),
                   uploaded_by=user)
    session.add(doc)
    session.flush()
    for i, t in enumerate(pages, start=1):
        session.add(DocumentPage(document_id=doc.id, page_no=i, text=t))
    session.flush()
    return doc


def document_pages(session: Session, document_id: int) -> list[str]:
    rows = session.scalars(select(DocumentPage).where(DocumentPage.document_id == document_id)
                           .order_by(DocumentPage.page_no)).all()
    return [r.text for r in rows]


def run_extraction(session: Session, *, document_id: int, llm: ExtractionLLM, user: str,
                   cusip: str | None = None, model: str | None = None) -> Extraction:
    doc = session.get(Document, document_id)
    if doc is None:
        raise ValueError(f"document {document_id} not found")
    cusip = (cusip or doc.cusip).upper()
    model = model or settings.extraction_model
    pages = document_pages(session, document_id)
    ex = Extraction(document_id=doc.id, cusip=cusip, model_requested=model, created_by=user,
                    prompt_version="", status="failed")
    try:
        res = extract_terms_from_pages(pages, cusip, llm, model=model,
                                       max_tokens=settings.extraction_max_tokens,
                                       max_pages=settings.extraction_max_pages)
    except ExtractionLLMError as e:
        from ..extraction.prompt import PROMPT_VERSION
        ex.prompt_version = PROMPT_VERSION
        ex.error = str(e)
        session.add(ex)
        session.flush()
        return ex
    ex.prompt_version = res.prompt_version
    ex.model_served = res.model
    ex.status = res.status
    ex.terms = res.raw_json
    ex.citation_checks = [c.as_dict() for c in res.checks]
    ex.interest_terms = jsonable(res.interest_terms) if res.interest_terms else None
    ex.problems = res.problems
    ex.page_selection = jsonable(res.selection)
    ex.llm_meta = jsonable(res.llm_meta)
    session.add(ex)
    session.flush()
    return ex


def citation_index(ex: Extraction) -> dict[str, dict]:
    """field -> {page, excerpt, status} for findings and the review UI."""
    out: dict[str, dict] = {}
    checks = {c["field"]: c for c in (ex.citation_checks or [])}
    for name, v in (ex.terms or {}).items():
        if isinstance(v, dict) and "page" in v:
            out[name] = {"page": v.get("page"), "excerpt": v.get("excerpt"),
                         "status": checks.get(name, {}).get("status")}
    return out
