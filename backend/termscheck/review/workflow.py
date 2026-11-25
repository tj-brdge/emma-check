"""Review state machine. Pure: given the current status and an action, return the new status.

open --approve--> approved      open --reject--> rejected
approved/rejected --reopen--> open
annotate: any state, no status change. Approve/reject require a decided-from-open finding;
reject requires a comment (reviewers must say why a flag was dismissed).
"""
from __future__ import annotations

from enum import StrEnum


class Status(StrEnum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"


class Action(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    ANNOTATE = "annotate"
    REOPEN = "reopen"


class ReviewError(ValueError):
    pass


TRANSITIONS = {
    (Status.OPEN, Action.APPROVE): Status.APPROVED,
    (Status.OPEN, Action.REJECT): Status.REJECTED,
    (Status.APPROVED, Action.REOPEN): Status.OPEN,
    (Status.REJECTED, Action.REOPEN): Status.OPEN,
}


def apply(status: str, action: str, comment: str | None) -> Status:
    s, a = Status(status), Action(action)
    if a is Action.ANNOTATE:
        if not comment or not comment.strip():
            raise ReviewError("annotation requires a comment")
        return s
    if a is Action.REJECT and (not comment or not comment.strip()):
        raise ReviewError("rejecting a finding requires a comment")
    nxt = TRANSITIONS.get((s, a))
    if nxt is None:
        raise ReviewError(f"cannot {a.value} a finding that is {s.value}")
    return nxt


def replay(actions: list[tuple[str, str | None]]) -> Status:
    """Derive status from the full action history (used to verify the cached status)."""
    s = Status.OPEN
    for a, c in actions:
        s = apply(s, a, c)
    return s
