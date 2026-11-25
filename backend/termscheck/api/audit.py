from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import verify_chain
from ..db.models import AuditEvent
from .deps import get_session

router = APIRouter(prefix="/api", tags=["audit"])


def event_json(e: AuditEvent) -> dict:
    return {"id": e.id, "ts": e.ts, "actor": e.actor, "event_type": e.event_type, "entity_type": e.entity_type,
            "entity_id": e.entity_id, "payload": e.payload, "prev_hash": e.prev_hash, "hash": e.hash}


@router.get("/audit")
def list_events(limit: int = Query(200, le=5000), event_type: str | None = None, entity_type: str | None = None,
                entity_id: str | None = None, actor: str | None = None, session: Session = Depends(get_session)):
    q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if event_type:
        q = q.where(AuditEvent.event_type == event_type)
    if entity_type:
        q = q.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditEvent.entity_id == entity_id)
    if actor:
        q = q.where(AuditEvent.actor == actor)
    return [event_json(e) for e in session.scalars(q)]


@router.get("/audit/verify")
def verify(session: Session = Depends(get_session)):
    c = verify_chain(session)
    return {"ok": c.ok, "checked": c.checked, "first_bad_id": c.first_bad_id, "reason": c.reason}
