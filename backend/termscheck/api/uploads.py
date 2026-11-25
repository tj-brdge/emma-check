from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from termscheck.db.models import UploadBatch
from termscheck.services.ingestion import KINDS, IngestError, ingest_file, record_rejection
from termscheck.api.deps import current_user, get_session, read_limited
from termscheck.settings import settings

router = APIRouter(prefix="/api", tags=["uploads"])


def batch_json(b: UploadBatch) -> dict:
    return {"id": b.id, "kind": b.kind, "vendor": b.vendor, "filename": b.filename,
            "sha256": b.sha256, "row_count": b.row_count, "uploaded_by": b.uploaded_by,
            "uploaded_at": b.uploaded_at.isoformat() if b.uploaded_at else None}


@router.post("/uploads/{kind}")
def upload(kind: str, file: UploadFile = File(...), vendor: str | None = Form(None),
           user: str = Depends(current_user), session: Session = Depends(get_session)):
    # sync def: FastAPI runs it in a worker thread, so parsing never blocks other requests
    if kind not in KINDS:
        raise HTTPException(404, f"unknown upload kind; expected one of {KINDS}")
    raw = read_limited(file, settings.max_data_bytes)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "file must be UTF-8 CSV")
    try:
        out = ingest_file(session, kind=kind, filename=file.filename or "upload.csv", text=text,
                          user=user, vendor=vendor)
    except IngestError as e:
        session.rollback()
        record_rejection(session, kind=kind, filename=file.filename or "upload.csv", user=user, result=e.result)
        session.commit()
        raise HTTPException(422, {"message": "file rejected; nothing was ingested",
                                  "errors": [vars(x) for x in e.result.errors[:500]],
                                  "error_count": len(e.result.errors)})
    session.commit()
    return {"batch": batch_json(out.batch), "records": len(out.result.records),
            "positions": len(out.result.positions), "prices": len(out.result.prices)}


@router.get("/batches")
def list_batches(session: Session = Depends(get_session)):
    return [batch_json(b) for b in session.scalars(select(UploadBatch).order_by(UploadBatch.id.desc()))]
