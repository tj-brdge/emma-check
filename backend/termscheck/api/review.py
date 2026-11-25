from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..review import ReviewError
from ..services.review import act, approved_csv, history
from .deps import current_user, get_session

router = APIRouter(prefix="/api", tags=["review"])


class ActionRequest(BaseModel):
    action: str
    comment: str | None = None


def action_json(a) -> dict:
    return {"id": a.id, "finding_id": a.finding_id, "action": a.action, "from_status": a.from_status,
            "to_status": a.to_status, "comment": a.comment, "actor": a.actor,
            "at": a.at.isoformat() if a.at else None}


@router.post("/findings/{finding_id}/actions")
def post_action(finding_id: int, req: ActionRequest, user: str = Depends(current_user),
                session: Session = Depends(get_session)):
    try:
        a = act(session, finding_id=finding_id, action=req.action, comment=req.comment, user=user)
    except LookupError as e:
        session.rollback()
        raise HTTPException(404, str(e))
    except (ReviewError, ValueError) as e:
        session.rollback()
        raise HTTPException(422, str(e))
    session.commit()
    return action_json(a)


@router.get("/findings/{finding_id}/actions")
def get_actions(finding_id: int, session: Session = Depends(get_session)):
    return [action_json(a) for a in history(session, finding_id)]


@router.get("/exports/approved.csv")
def export_approved(user: str = Depends(current_user), session: Session = Depends(get_session)):
    body = approved_csv(session)
    session.commit()
    return Response(body, media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="terms_check_approved.csv"'})
