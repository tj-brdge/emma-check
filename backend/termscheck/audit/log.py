"""Immutable, hash-chained audit log.

Each event stores sha256(prev_hash || canonical_json(event)). Events are serialised with a
transaction-scoped advisory lock so the chain is linear. The database rejects UPDATE, DELETE
and TRUNCATE on audit_event (and on other write-once tables) via triggers - see migration 0004.
verify_chain() recomputes every hash; any edit, deletion or reordering breaks it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..db.models import AuditEvent
from ..services.serialize import jsonable

GENESIS = "0" * 64
_LOCK_KEY = 7_340_001  # arbitrary constant for pg_advisory_xact_lock


def canonical(ts: str, actor: str, event_type: str, entity_type: str, entity_id: str, payload: Any) -> str:
    return json.dumps({"ts": ts, "actor": actor, "event_type": event_type, "entity_type": entity_type,
                       "entity_id": entity_id, "payload": payload}, sort_keys=True, separators=(",", ":"))


def chain_hash(prev: str, body: str) -> str:
    return hashlib.sha256((prev + body).encode()).hexdigest()


def record(session: Session, *, actor: str, event_type: str, entity_type: str, entity_id: Any,
           payload: dict[str, Any] | None = None) -> AuditEvent:
    session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
    prev = session.scalars(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1)).first() or GENESIS
    ts = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    body_payload = jsonable(payload or {})
    eid = str(entity_id)
    h = chain_hash(prev, canonical(ts, actor, event_type, entity_type, eid, body_payload))
    ev = AuditEvent(ts=ts, actor=actor, event_type=event_type, entity_type=entity_type, entity_id=eid,
                    payload=body_payload, prev_hash=prev, hash=h)
    session.add(ev)
    session.flush()
    return ev


@dataclass
class ChainCheck:
    ok: bool
    checked: int
    first_bad_id: int | None
    reason: str | None


def verify_chain(session: Session) -> ChainCheck:
    prev = GENESIS
    n = 0
    for ev in session.scalars(select(AuditEvent).order_by(AuditEvent.id)).yield_per(1000):
        n += 1
        if ev.prev_hash != prev:
            return ChainCheck(False, n, ev.id, "prev_hash does not link to the preceding event")
        expect = chain_hash(prev, canonical(ev.ts, ev.actor, ev.event_type, ev.entity_type, ev.entity_id, ev.payload))
        if expect != ev.hash:
            return ChainCheck(False, n, ev.id, "event content does not match its hash")
        prev = ev.hash
    return ChainCheck(True, n, None, None)
