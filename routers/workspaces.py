import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import audit
from database import get_db
from deps import WorkspaceContext, get_current_user, require_role
from errors import AppError
from models import (
    AssistantConfig, AuditLog, User, Workspace, WorkspaceMember, iso,
)
from schemas import (
    AssistantConfigIn, MemberIn, MemberUpdateIn, WorkspaceIn, WorkspaceUpdateIn,
)
from workspace_service import ROLE_HELP, ROLE_RANK, create_workspace, workspace_out

router = APIRouter(tags=["Workspaces"])


@router.get("/workspaces", summary="Workspaces I belong to")
def list_workspaces(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(Workspace, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .filter(WorkspaceMember.user_id == user.id).order_by(Workspace.id).all())
    return {"items": [workspace_out(w, r) for w, r in rows], "total": len(rows)}


@router.post("/workspaces", status_code=201, summary="Create another workspace")
def new_workspace(body: WorkspaceIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    count = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == user.id, WorkspaceMember.role == "owner").count()
    if count >= 10:
        raise AppError(400, "too_many_workspaces", "You already own 10 workspaces.",
                       "Remove one you no longer need, or ask support to raise the limit.")
    workspace = create_workspace(db, user, body.name)
    audit.record(db, "workspace.created", workspace_id=workspace.id, actor_type="user",
                 actor_id=user.id, actor_label=user.email, target_type="workspace",
                 target_id=workspace.id)
    db.commit()
    return workspace_out(workspace, "owner")


@router.get("/workspaces/{workspace_id}", summary="Workspace details")
def get_workspace(ctx: WorkspaceContext = Depends(require_role("viewer"))):
    return workspace_out(ctx.workspace, ctx.role)


@router.patch("/workspaces/{workspace_id}", summary="Rename the workspace or change its default")
def update_workspace(body: WorkspaceUpdateIn,
                     ctx: WorkspaceContext = Depends(require_role("admin")),
                     db: Session = Depends(get_db)):
    changes = {}
    if body.name is not None and body.name.strip() != ctx.workspace.name:
        changes["name"] = body.name.strip()
        ctx.workspace.name = body.name.strip()
    if body.default_decision is not None and body.default_decision != ctx.workspace.default_decision:
        changes["default_decision"] = body.default_decision
        ctx.workspace.default_decision = body.default_decision
    if changes:
        audit.record(db, "workspace.updated", workspace_id=ctx.workspace.id,
                     actor_type="user", actor_id=ctx.user.id, actor_label=ctx.user.email,
                     target_type="workspace", target_id=ctx.workspace.id, details=changes)
        db.commit()
    return workspace_out(ctx.workspace, ctx.role)


# ---------------------------------------------------------------- members

def _member_out(member: WorkspaceMember, user: User) -> dict:
    return {"user_id": user.id, "email": user.email, "full_name": user.full_name,
            "role": member.role, "joined_at": iso(member.created_at)}


@router.get("/workspaces/{workspace_id}/members", summary="People in this workspace")
def list_members(ctx: WorkspaceContext = Depends(require_role("viewer")),
                 db: Session = Depends(get_db)):
    rows = (db.query(WorkspaceMember, User)
            .join(User, User.id == WorkspaceMember.user_id)
            .filter(WorkspaceMember.workspace_id == ctx.workspace.id)
            .order_by(WorkspaceMember.id).all())
    return {"items": [_member_out(m, u) for m, u in rows], "total": len(rows),
            "roles": ROLE_HELP}


@router.post("/workspaces/{workspace_id}/members", status_code=201,
             summary="Add an existing Falcon Eye user to this workspace")
def add_member(body: MemberIn, ctx: WorkspaceContext = Depends(require_role("admin")),
               db: Session = Depends(get_db)):
    if body.role == "admin" and ctx.role != "owner":
        raise AppError(403, "not_allowed", "Only the workspace owner can add admins.",
                       "Add them as a member, then ask the owner to promote them.")
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not user.is_active:
        raise AppError(404, "user_not_found",
                       "There is no Falcon Eye account with that email address.",
                       "Ask them to create an account first, then add them here.")
    exists = db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == ctx.workspace.id,
        WorkspaceMember.user_id == user.id).first()
    if exists:
        raise AppError(409, "already_member", "That person is already in this workspace.")
    member = WorkspaceMember(workspace_id=ctx.workspace.id, user_id=user.id, role=body.role)
    db.add(member)
    audit.record(db, "member.added", workspace_id=ctx.workspace.id, actor_type="user",
                 actor_id=ctx.user.id, actor_label=ctx.user.email, target_type="user",
                 target_id=user.id, details={"role": body.role, "email": user.email})
    db.commit()
    db.refresh(member)
    return _member_out(member, user)


def _get_member(db: Session, ctx: WorkspaceContext, user_id: int) -> tuple[WorkspaceMember, User]:
    row = (db.query(WorkspaceMember, User)
           .join(User, User.id == WorkspaceMember.user_id)
           .filter(WorkspaceMember.workspace_id == ctx.workspace.id,
                   WorkspaceMember.user_id == user_id).first())
    if row is None:
        raise AppError(404, "member_not_found", "That person is not in this workspace.")
    return row


@router.patch("/workspaces/{workspace_id}/members/{user_id}", summary="Change someone's role")
def update_member(user_id: int, body: MemberUpdateIn,
                  ctx: WorkspaceContext = Depends(require_role("owner")),
                  db: Session = Depends(get_db)):
    member, user = _get_member(db, ctx, user_id)
    if member.role == "owner":
        raise AppError(400, "owner_locked", "The owner's role cannot be changed.")
    old = member.role
    member.role = body.role
    audit.record(db, "member.role_changed", workspace_id=ctx.workspace.id, actor_type="user",
                 actor_id=ctx.user.id, actor_label=ctx.user.email, target_type="user",
                 target_id=user.id, details={"from": old, "to": body.role})
    db.commit()
    return _member_out(member, user)


@router.delete("/workspaces/{workspace_id}/members/{user_id}", summary="Remove someone")
def remove_member(user_id: int, ctx: WorkspaceContext = Depends(require_role("admin")),
                  db: Session = Depends(get_db)):
    member, user = _get_member(db, ctx, user_id)
    if member.role == "owner":
        raise AppError(400, "owner_locked", "The workspace owner cannot be removed.")
    if ROLE_RANK[member.role] >= ROLE_RANK[ctx.role] and ctx.role != "owner":
        raise AppError(403, "not_allowed", "You cannot remove someone with the same or a higher role.")
    db.delete(member)
    audit.record(db, "member.removed", workspace_id=ctx.workspace.id, actor_type="user",
                 actor_id=ctx.user.id, actor_label=ctx.user.email, target_type="user",
                 target_id=user.id, details={"email": user.email})
    db.commit()
    return {"message": f"{user.full_name} was removed from the workspace."}


# ---------------------------------------------------------------- audit log

@router.get("/workspaces/{workspace_id}/audit-logs", summary="Who did what, and when")
def audit_logs(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
               ctx: WorkspaceContext = Depends(require_role("admin")),
               db: Session = Depends(get_db)):
    query = db.query(AuditLog).filter(AuditLog.workspace_id == ctx.workspace.id)
    total = query.count()
    rows = query.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()
    items = []
    for row in rows:
        try:
            details = json.loads(row.details) if row.details else None
        except ValueError:
            details = None
        items.append({
            "id": row.id, "action": row.action, "actor_type": row.actor_type,
            "actor": row.actor_label or row.actor_id, "target_type": row.target_type,
            "target_id": row.target_id, "details": details, "ip_address": row.ip_address,
            "created_at": iso(row.created_at),
        })
    return {"items": items, "total": total}


# ---------------------------------------------------------------- assistant settings

def _config(db: Session, workspace_id: int) -> AssistantConfig:
    config = db.query(AssistantConfig).filter(AssistantConfig.workspace_id == workspace_id).first()
    if config is None:
        config = AssistantConfig(workspace_id=workspace_id, enabled=True)
        db.add(config)
        db.flush()
    return config


@router.get("/workspaces/{workspace_id}/assistant-config", summary="AI assistant settings")
def get_assistant_config(ctx: WorkspaceContext = Depends(require_role("viewer")),
                         db: Session = Depends(get_db)):
    from config import settings
    config = _config(db, ctx.workspace.id)
    db.commit()
    return {"enabled": config.enabled, "custom_instructions": config.custom_instructions or "",
            "live_ai_configured": settings.llm_enabled}


@router.put("/workspaces/{workspace_id}/assistant-config", summary="Change AI assistant settings")
def put_assistant_config(body: AssistantConfigIn,
                         ctx: WorkspaceContext = Depends(require_role("admin")),
                         db: Session = Depends(get_db)):
    from config import settings
    config = _config(db, ctx.workspace.id)
    config.enabled = body.enabled
    config.custom_instructions = body.custom_instructions.strip()
    audit.record(db, "assistant.configured", workspace_id=ctx.workspace.id, actor_type="user",
                 actor_id=ctx.user.id, actor_label=ctx.user.email,
                 details={"enabled": body.enabled}, ip=None)
    db.commit()
    return {"enabled": config.enabled, "custom_instructions": config.custom_instructions or "",
            "live_ai_configured": settings.llm_enabled}
