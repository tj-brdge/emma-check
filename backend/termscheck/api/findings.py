from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from termscheck.db.models import Finding
from termscheck.services.findings import FindingError, create_finding
from termscheck.api.deps import current_user, get_session

router = APIRouter(prefix="/api", tags=["findings"])


def finding_json(f: Finding, detail: bool = False) -> dict:
    out = {"id": f.id, "cusip": f.cusip, "asset_class": f.asset_class, "description": f.description, "as_of": f.as_of.isoformat(),
           "screen_run_id": f.screen_run_id, "extraction_id": f.extraction_id,
           "income_impact_usd": f.income_impact_usd, "run_rate_gap_usd": f.run_rate_gap_usd,
           "headline": f.headline, "rules": f.rules, "status": f.status,
           "extraction_status": (f.narrative or {}).get("extraction_status"),
           "created_by": f.created_by, "created_at": f.created_at.isoformat() if f.created_at else None}
    if detail:
        out["narrative"] = f.narrative
        out["comparison"] = f.comparison
        out["positions"] = [{"holding_id": c.holding_id, "par": c.inputs.get("par"),
                             "unbooked_income_usd": c.outputs.get("unbooked_income_usd"),
                             "run_rate_gap_usd": c.outputs.get("run_rate_gap_usd"),
                             "unbooked_window_usd": c.outputs.get("unbooked_window_usd"),
                             "computation_id": c.id} for c in f.computations]
    return out


class FindingRequest(BaseModel):
    screen_run_id: int
    extraction_id: int


@router.post("/findings")
def post_finding(req: FindingRequest, user: str = Depends(current_user), session: Session = Depends(get_session)):
    try:
        f = create_finding(session, screen_run_id=req.screen_run_id, extraction_id=req.extraction_id, user=user)
    except FindingError as e:
        session.rollback()
        raise HTTPException(422, str(e))
    session.commit()
    return finding_json(f, detail=True)


@router.get("/findings")
def list_findings(status: str | None = None, session: Session = Depends(get_session)):
    q = select(Finding).order_by(func.abs(Finding.income_impact_usd).desc(),
                                 func.abs(Finding.run_rate_gap_usd).desc(), Finding.id)
    if status:
        q = q.where(Finding.status == status)
    return [finding_json(f) for f in session.scalars(q)]


@router.get("/findings/{finding_id}")
def get_finding(finding_id: int, session: Session = Depends(get_session)):
    f = session.get(Finding, finding_id)
    if f is None:
        raise HTTPException(404, "finding not found")
    return finding_json(f, detail=True)
