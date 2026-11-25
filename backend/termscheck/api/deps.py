from __future__ import annotations

from fastapi import Header, HTTPException

from ..db.session import get_session  # noqa: F401  (re-export for routers)


def current_user(x_user: str | None = Header(default=None)) -> str:
    """Prototype identity: the UI sends the reviewer's name in X-User. No authentication."""
    if not x_user or not x_user.strip():
        raise HTTPException(status_code=401, detail="X-User header required")
    return x_user.strip()[:128]
