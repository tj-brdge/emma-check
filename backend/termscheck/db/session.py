from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..settings import settings

_engine = None
_Session: sessionmaker | None = None


def configure(url: str | None = None) -> None:
    global _engine, _Session
    _engine = create_engine(url or settings.database_url, pool_pre_ping=True, future=True)
    _Session = sessionmaker(_engine, expire_on_commit=False)


def engine():
    if _engine is None:
        configure()
    return _engine


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, committed by the service layer."""
    if _Session is None:
        configure()
    with _Session() as s:  # type: ignore[misc]
        yield s


@contextmanager
def session_scope() -> Iterator[Session]:
    if _Session is None:
        configure()
    with _Session() as s:  # type: ignore[misc]
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
