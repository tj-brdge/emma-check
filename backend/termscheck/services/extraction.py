from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from termscheck.audit import record
from termscheck.db.models import DisclosureObservation, Document, DocumentPage, Extraction
from termscheck.core.plugin import get_plugin
from termscheck.db.models import VendorTerms
from termscheck.extraction import ExtractionLLMError, extract_terms_from_pages
from termscheck.extraction.llm import ExtractionLLM
from termscheck.extraction.pdf import extract_pages
from termscheck.extraction.sources import UploadSource
from termscheck.settings import settings
from termscheck.services.serialize import jsonable


def asset_class_of(session: Session, cusip: str) -> str:
    """Asset class from the most recent reference data for the CUSIP (munis if unknown)."""
    v = session.scalars(select(VendorTerms.asset_class).where(VendorTerms.cusip == cusip.upper())
                        .order_by(VendorTerms.id.desc())).first()
    return v or "muni"


def register_document(session: Session, store: UploadSource, *, cusip: str, filename: str,
                      content: bytes, user: str, asset_class: str | None = None,
                      doc_kind: str = "official_statement") -> Document:
    asset_class = asset_class or asset_class_of(session, cusip)
    plugin = get_plugin(asset_class)
    is_data = doc_kind in getattr(plugin, "data_document_kinds", ())
    parsed = None
    if is_data:
        text = content.decode("utf-8-sig") if content[:4] != b"%PDF" else ""
        if not text:
            raise ValueError(f"{doc_kind} must be a UTF-8 data file")
        parsed = plugin.parse_data_document(doc_kind, filename, text)
        if parsed.errors:
            raise ValueError(f"{doc_kind} rejected: " + "; ".join(parsed.errors[:20]))
        pages = [text]
    ref = store.put(cusip, filename, content, data_file=is_data)
    if not is_data:
        pages = extract_pages(content)
    doc = Document(cusip=cusip.upper(), source=store.name, source_ref=ref.ref, filename=filename,
                   sha256=ref.ref, page_count=len(pages), storage_path=str(store.root / f"{ref.ref}.pdf"),
                   uploaded_by=user, asset_class=asset_class, doc_kind=doc_kind)
    session.add(doc)
    session.flush()
    for i, t in enumerate(pages, start=1):
        session.add(DocumentPage(document_id=doc.id, page_no=i, text=t))
    if parsed is not None:
        for r in parsed.rows:
            session.add(DisclosureObservation(document_id=doc.id, cusip=r.cusip, month=r.obs.month,
                                              factor=r.obs.factor, net_coupon=r.obs.net_coupon, row_no=r.row_no,
                                              locator=r.obs.source, raw=r.raw))
    session.flush()
    record(session, actor=user, event_type="document.registered", entity_type="document", entity_id=doc.id,
           payload={"cusip": doc.cusip, "asset_class": asset_class, "doc_kind": doc_kind, "source": doc.source,
                    "observations": len(parsed.rows) if parsed else None,
                    "filename": filename, "sha256": doc.sha256, "pages": doc.page_count})
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
    plugin = get_plugin(doc.asset_class)
    if doc.doc_kind in getattr(plugin, "data_document_kinds", ()):
        raise ValueError(f"document {doc.id} is a {doc.doc_kind} data file; it is parsed on upload, not extracted")
    ex = Extraction(document_id=doc.id, cusip=cusip, model_requested=model, created_by=user,
                    prompt_version=plugin.extraction.prompt_version, status="failed", asset_class=plugin.key)
    try:
        res = extract_terms_from_pages(pages, cusip, llm, plugin.extraction, model=model,
                                       max_tokens=settings.extraction_max_tokens,
                                       max_pages=settings.extraction_max_pages)
    except ExtractionLLMError as e:
        ex.error = str(e)
        session.add(ex)
        session.flush()
        record(session, actor=user, event_type="extraction.failed", entity_type="extraction", entity_id=ex.id,
               payload={"cusip": cusip, "document_id": doc.id, "model": model,
                        "prompt_version": ex.prompt_version, "error": ex.error})
        return ex
    ex.prompt_version = res.prompt_version
    ex.model_served = res.model
    ex.status = res.status
    ex.terms = res.raw_json
    ex.citation_checks = [c.as_dict() for c in res.checks]
    ex.interest_terms = plugin.terms_to_json(res.interest_terms) if res.interest_terms else None
    ex.problems = res.problems
    ex.page_selection = jsonable(res.selection)
    ex.llm_meta = jsonable(res.llm_meta)
    session.add(ex)
    session.flush()
    record(session, actor=user, event_type="extraction.completed", entity_type="extraction", entity_id=ex.id,
           payload={"cusip": cusip, "asset_class": plugin.key, "document_id": doc.id, "document_sha256": doc.sha256,
                    "model_requested": model, "model_served": ex.model_served,
                    "prompt_version": ex.prompt_version, "status": ex.status, "problems": ex.problems,
                    "pages_sent": res.selection.pages, "interest_terms": ex.interest_terms,
                    "citations": {c.field: {"page": c.page, "status": c.status} for c in res.checks},
                    "llm": ex.llm_meta})
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
