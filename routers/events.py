import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import approval_service
from database import get_db
from deps import WorkspaceContext, require_role
from errors import AppError
from models import ApprovalRequest, FirewallEvent, User, iso

router = APIRouter(prefix="/workspaces/{workspace_id}/events", tags=["Events"])


def _approval_map(db: Session, workspace_id: int, events: list[FirewallEvent]) -> dict:
    ids = [e.approval_id for e in events if e.approval_id]
    if not ids:
        return {}
    rows = (db.query(ApprovalRequest)
            .filter(ApprovalRequest.workspace_id == workspace_id,
                    ApprovalRequest.approval_id.in_(ids)).all())
    return {r.approval_id: r for r in rows}


def event_out(event: FirewallEvent, approvals: dict | None = None, detail: bool = False,
              deciders: dict | None = None) -> dict:
    approval = (approvals or {}).get(event.approval_id) if event.approval_id else None
    data = {
        "event_id": event.event_id,
        "agent_id": event.agent_id,
        "agent_name": event.agent_name or event.agent_id,
        "action": event.action,
        "resource": event.resource,
        "category": event.category,
        "decision": event.decision,
        "decision_reason": event.decision_reason,
        "policy_name": event.policy_name,
        "approval_id": event.approval_id,
        "approval_status": approval.status if approval else None,
        "created_at": iso(event.created_at),
    }
    if detail:
        try:
            metadata = json.loads(event.details) if event.details else None
        except ValueError:
            metadata = None
        decider = (deciders or {}).get(approval.decided_by) if approval and approval.decided_by else None
        data.update({
            "agent_reason": event.reason,
            "policy_id": event.policy_id,
            "request_id": event.request_id,
            "metadata": metadata,
            "source_ip": event.source_ip,
            "approval_decided_by": decider.full_name if decider else None,
            "approval_decided_at": iso(approval.decided_at) if approval else None,
        })
    return data


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("", summary="Search and filter firewall events")
def list_events(
    q: str | None = Query(None, max_length=100, description="Search text"),
    decision: str | None = Query(None, pattern="^(ALLOW|BLOCK|REQUIRE_APPROVAL)$"),
    agent_id: str | None = Query(None, max_length=64, description="An agent's public id"),
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    ctx: WorkspaceContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
):
    query = db.query(FirewallEvent).filter(FirewallEvent.workspace_id == ctx.workspace.id)
    if decision:
        query = query.filter(FirewallEvent.decision == decision)
    if agent_id:
        query = query.filter(FirewallEvent.agent_id == agent_id)
    if q and q.strip():
        like = f"%{_escape_like(q.strip().lower())}%"
        columns = (FirewallEvent.action, FirewallEvent.resource, FirewallEvent.agent_name,
                   FirewallEvent.agent_id, FirewallEvent.event_id, FirewallEvent.category)
        query = query.filter(or_(*[func.lower(c).like(like, escape="\\") for c in columns]))
    total = query.count()
    rows = (query.order_by(FirewallEvent.created_at.desc(), FirewallEvent.id.desc())
            .offset(offset).limit(limit).all())
    approvals = _approval_map(db, ctx.workspace.id, rows)
    return {"items": [event_out(e, approvals) for e in rows], "total": total,
            "limit": limit, "offset": offset}


@router.get("/{event_id}", summary="Full details of one event")
def get_event(event_id: str, ctx: WorkspaceContext = Depends(require_role("viewer")),
              db: Session = Depends(get_db)):
    event = (db.query(FirewallEvent)
             .filter(FirewallEvent.event_id == event_id,
                     FirewallEvent.workspace_id == ctx.workspace.id).first())
    if event is None:
        raise AppError(404, "event_not_found", "We could not find that event.")
    approval_service.expire_stale(db, ctx.workspace.id)
    approvals = _approval_map(db, ctx.workspace.id, [event])
    deciders = {}
    ids = {a.decided_by for a in approvals.values() if a.decided_by}
    if ids:
        deciders = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}
    return event_out(event, approvals, detail=True, deciders=deciders)
