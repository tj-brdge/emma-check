from __future__ import annotations

from dataclasses import asdict, fields
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record
from ..db.models import Holding, PriceHistory, ScreenFlag, ScreenRun, UploadBatch, VendorTerms
from ..screens import Position, PricePoint, ScreenConfig, ScreenInput, SecurityRecord, run_screens

_SEC_FIELDS = [f.name for f in fields(SecurityRecord)]


def to_record(v: VendorTerms) -> SecurityRecord:
    return SecurityRecord(**{k: getattr(v, k) for k in _SEC_FIELDS})


def _batch(session: Session, batch_id: int, kind: str) -> UploadBatch:
    b = session.get(UploadBatch, batch_id)
    if b is None or b.kind != kind:
        raise ValueError(f"batch {batch_id} is not a {kind} batch")
    return b


def load_screen_input(session: Session, as_of: date, holdings_batch_id: int,
                      secondary_batch_id: int | None = None,
                      history_batch_id: int | None = None) -> ScreenInput:
    _batch(session, holdings_batch_id, "holdings")
    positions = [Position(h.portfolio, h.cusip, h.par, h.acquisition_date) for h in
                 session.scalars(select(Holding).where(Holding.batch_id == holdings_batch_id))]
    primary = {v.cusip: to_record(v) for v in
               session.scalars(select(VendorTerms).where(VendorTerms.batch_id == holdings_batch_id))}
    secondary: dict[str, SecurityRecord] = {}
    if secondary_batch_id is not None:
        _batch(session, secondary_batch_id, "vendor_secondary")
        secondary = {v.cusip: to_record(v) for v in
                     session.scalars(select(VendorTerms).where(VendorTerms.batch_id == secondary_batch_id))}
    history: dict[str, list[PricePoint]] = {}
    if history_batch_id is not None:
        _batch(session, history_batch_id, "price_history")
        for p in session.scalars(select(PriceHistory).where(PriceHistory.batch_id == history_batch_id)):
            history.setdefault(p.cusip, []).append(PricePoint(p.cusip, p.price_date, p.price, p.convention))
    return ScreenInput(as_of, positions, primary, secondary, history)


def execute_screen_run(session: Session, *, as_of: date, holdings_batch_id: int, user: str,
                       secondary_batch_id: int | None = None, history_batch_id: int | None = None,
                       config_overrides: dict | None = None) -> ScreenRun:
    config = ScreenConfig(**(config_overrides or {}))
    data = load_screen_input(session, as_of, holdings_batch_id, secondary_batch_id, history_batch_id)
    started = datetime.now(timezone.utc)
    result = run_screens(data, config)
    run = ScreenRun(as_of=as_of, holdings_batch_id=holdings_batch_id,
                    secondary_batch_id=secondary_batch_id, history_batch_id=history_batch_id,
                    config=config.as_dict(), started_by=user, started_at=started,
                    finished_at=datetime.now(timezone.utc), flag_count=len(result.flags))
    session.add(run)
    session.flush()
    for f in result.flags:
        session.add(ScreenFlag(run_id=run.id, cusip=f.cusip, rule=f.rule, severity=f.severity,
                               message=f.message, inputs=_jsonable(f.inputs),
                               computed=_jsonable(f.computed)))
    session.flush()
    by_rule: dict[str, int] = {}
    for f in result.flags:
        by_rule[f.rule] = by_rule.get(f.rule, 0) + 1
    record(session, actor=user, event_type="screen_run.completed", entity_type="screen_run", entity_id=run.id,
           payload={"as_of": as_of, "holdings_batch_id": holdings_batch_id,
                    "secondary_batch_id": secondary_batch_id, "history_batch_id": history_batch_id,
                    "config": run.config, "holdings": len(data.positions), "flag_count": len(result.flags),
                    "flags_by_rule": by_rule, "flagged_cusips": len(result.flagged_cusips()),
                    "flags": [{"cusip": f.cusip, "rule": f.rule, "severity": f.severity} for f in result.flags]})
    return run


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (date, datetime)):
        return x.isoformat()
    if isinstance(x, float) and (x != x or x in (float("inf"), float("-inf"))):
        return None
    if hasattr(x, "__dataclass_fields__"):
        return _jsonable(asdict(x))
    return x
