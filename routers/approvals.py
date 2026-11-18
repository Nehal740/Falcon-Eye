from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

import approval_service
from database import get_db
from deps import WorkspaceContext, client_ip, require_role
from models import ApprovalDecision, ApprovalRequest, User
from schemas import DecisionIn

router = APIRouter(prefix="/workspaces/{workspace_id}/approvals", tags=["Approvals"])


@router.get("", summary="Approval requests (pending by default)")
def list_approvals(
    status: str = Query("PENDING", pattern="^(PENDING|APPROVED|REJECTED|EXPIRED|ALL)$"),
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    ctx: WorkspaceContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
):
    approval_service.expire_stale(db, ctx.workspace.id)
    query = db.query(ApprovalRequest).filter(ApprovalRequest.workspace_id == ctx.workspace.id)
    if status != "ALL":
        query = query.filter(ApprovalRequest.status == status)
    total = query.count()
    rows = (query.order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc())
            .offset(offset).limit(limit).all())

    decisions = {}
    if rows:
        found = (db.query(ApprovalDecision)
                 .filter(ApprovalDecision.approval_pk.in_([r.id for r in rows])).all())
        decisions = {d.approval_pk: d for d in found}
    deciders = {}
    ids = {r.decided_by for r in rows if r.decided_by}
    if ids:
        deciders = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}

    items = []
    for row in rows:
        decision = decisions.get(row.id)
        items.append(approval_service.approval_out(
            row, deciders.get(row.decided_by), decision.comment if decision else None))
    pending = (db.query(ApprovalRequest)
               .filter(ApprovalRequest.workspace_id == ctx.workspace.id,
                       ApprovalRequest.status == "PENDING").count())
    return {"items": items, "total": total, "pending_count": pending,
            "can_decide": ctx.role in ("member", "admin", "owner")}


@router.post("/{approval_id}/decision", summary="Approve or reject a request")
def decide(approval_id: str, body: DecisionIn, request: Request,
           ctx: WorkspaceContext = Depends(require_role("member")),
           db: Session = Depends(get_db)):
    approval = approval_service.decide(
        db, workspace_id=ctx.workspace.id, approval_id=approval_id,
        decision=body.decision, comment=body.comment, user=ctx.user, ip=client_ip(request))
    verb = "approved" if body.decision == "APPROVED" else "rejected"
    return {
        "message": f"Request {verb}. Falcon Eye recorded your decision; the agent "
                   f"will see it the next time it checks.",
        "approval": approval_service.approval_out(approval, ctx.user, body.comment.strip() or None),
    }
