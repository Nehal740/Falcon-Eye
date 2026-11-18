"""Approval workflow rules.

The backend - not the browser - enforces who may decide and that each
request is decided exactly once.
"""

from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

import audit
from errors import AppError
from models import ApprovalDecision, ApprovalRequest, User, aware, iso, utcnow


def expire_stale(db: Session, workspace_id: int | None = None) -> int:
    """Mark pending requests whose time ran out as EXPIRED."""
    query = (update(ApprovalRequest)
             .where(ApprovalRequest.status == "PENDING",
                    ApprovalRequest.expires_at.isnot(None),
                    ApprovalRequest.expires_at < utcnow()))
    if workspace_id is not None:
        query = query.where(ApprovalRequest.workspace_id == workspace_id)
    result = db.execute(query.values(status="EXPIRED"))
    db.commit()
    return result.rowcount or 0


def expiry_time(hours: int):
    return utcnow() + timedelta(hours=hours)


def decide(db: Session, *, workspace_id: int, approval_id: str, decision: str,
           comment: str, user: User, ip: str | None = None) -> ApprovalRequest:
    expire_stale(db, workspace_id)

    approval = (db.query(ApprovalRequest)
                .filter(ApprovalRequest.approval_id == approval_id,
                        ApprovalRequest.workspace_id == workspace_id).first())
    if approval is None:
        raise AppError(404, "approval_not_found", "We could not find that approval request.",
                       "It may belong to a different workspace.")

    if approval.status != "PENDING":
        raise AppError(409, "already_decided", _already_text(db, approval),
                       "Refresh the page to see the latest status.")

    now = utcnow()
    # Compare-and-set: only the first decision can change a PENDING request,
    # even if two people click at the same moment.
    result = db.execute(
        update(ApprovalRequest)
        .where(ApprovalRequest.id == approval.id, ApprovalRequest.status == "PENDING")
        .values(status=decision, decided_at=now, decided_by=user.id))
    if (result.rowcount or 0) != 1:
        db.rollback()
        raise AppError(409, "already_decided",
                       "Someone else just decided this request.",
                       "Refresh the page to see the latest status.")

    db.add(ApprovalDecision(approval_pk=approval.id, decided_by=user.id, decision=decision,
                            comment=comment.strip() or None, decided_at=now))
    audit.record(db, f"approval.{decision.lower()}", workspace_id=workspace_id,
                 actor_type="user", actor_id=user.id, actor_label=user.email,
                 target_type="approval", target_id=approval.approval_id,
                 details={"action": approval.action, "resource": approval.resource,
                          "agent": approval.agent_name or approval.agent_id}, ip=ip)
    db.commit()
    db.refresh(approval)
    return approval


def _already_text(db: Session, approval: ApprovalRequest) -> str:
    if approval.status == "EXPIRED":
        return "This request expired before anyone decided it."
    who = db.get(User, approval.decided_by) if approval.decided_by else None
    name = who.full_name if who else "someone"
    return f"This request was already {approval.status.lower()} by {name}."


def _is_past(value) -> bool:
    value = aware(value)
    return value is not None and value < utcnow()


def approval_out(approval: ApprovalRequest, decider: User | None = None,
                 comment: str | None = None) -> dict:
    return {
        "approval_id": approval.approval_id,
        "agent_id": approval.agent_id,
        "agent_name": approval.agent_name or approval.agent_id,
        "action": approval.action,
        "resource": approval.resource,
        "reason": approval.reason,
        "category": approval.category,
        "status": approval.status,
        "event_id": approval.event_id,
        "created_at": iso(approval.created_at),
        "expires_at": iso(approval.expires_at),
        "decided_at": iso(approval.decided_at),
        "decided_by": decider.full_name if decider else None,
        "decision_comment": comment,
        "is_expired": approval.status == "PENDING" and _is_past(approval.expires_at),
    }
