from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from termscheck.db.models import ScreenFlag, ScreenRun
from termscheck.services.screening import execute_screen_run
from termscheck.api.deps import current_user, get_session

router = APIRouter(prefix="/api", tags=["screens"])


class ScreenRunRequest(BaseModel):
    as_of: date
    holdings_batch_id: int
    secondary_batch_id: int | None = None
    history_batch_id: int | None = None
    config: dict | None = None


def run_json(r: ScreenRun, with_flags: bool = False) -> dict:
    out = {"id": r.id, "as_of": r.as_of.isoformat(), "holdings_batch_id": r.holdings_batch_id,
           "secondary_batch_id": r.secondary_batch_id, "history_batch_id": r.history_batch_id,
           "config": r.config, "started_by": r.started_by,
           "started_at": r.started_at.isoformat() if r.started_at else None,
           "finished_at": r.finished_at.isoformat() if r.finished_at else None,
           "flag_count": r.flag_count}
    if with_flags:
        out["flags"] = [flag_json(f) for f in r.flags]
    return out


def flag_json(f: ScreenFlag) -> dict:
    return {"id": f.id, "run_id": f.run_id, "cusip": f.cusip, "rule": f.rule, "severity": f.severity,
            "message": f.message, "inputs": f.inputs, "computed": f.computed}


@router.post("/screen-runs")
def create_run(req: ScreenRunRequest, user: str = Depends(current_user),
               session: Session = Depends(get_session)):
    try:
        run = execute_screen_run(session, as_of=req.as_of, holdings_batch_id=req.holdings_batch_id,
                                 secondary_batch_id=req.secondary_batch_id,
                                 history_batch_id=req.history_batch_id,
                                 config_overrides=req.config, user=user)
    except (ValueError, TypeError) as e:
        session.rollback()
        raise HTTPException(422, str(e))
    session.commit()
    return run_json(run, with_flags=True)


@router.get("/screen-runs")
def list_runs(session: Session = Depends(get_session)):
    return [run_json(r) for r in session.scalars(select(ScreenRun).order_by(ScreenRun.id.desc()))]


@router.get("/screen-runs/{run_id}")
def get_run(run_id: int, session: Session = Depends(get_session)):
    r = session.get(ScreenRun, run_id)
    if r is None:
        raise HTTPException(404, "screen run not found")
    return run_json(r, with_flags=True)
