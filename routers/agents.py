from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

import audit
from agent_keys import generate_agent_key
from config import settings
from database import get_db
from deps import WorkspaceContext, require_role
from errors import AppError
from models import (
    Agent, AgentCredential, ApprovalRequest, FirewallEvent, Policy, aware, iso, utcnow,
)
from schemas import AgentIn, AgentUpdateIn

router = APIRouter(prefix="/workspaces/{workspace_id}/agents", tags=["Agents"])


def connection_status(agent: Agent, active_key: AgentCredential | None) -> str:
    """no_key / waiting / connected / inactive / disabled - in plain terms."""
    if agent.status == "disabled":
        return "disabled"
    if active_key is None:
        return "no_key"
    seen = aware(agent.last_seen_at)
    if seen is None:
        return "waiting"
    window = timedelta(minutes=settings.agent_connected_minutes)
    return "connected" if utcnow() - seen <= window else "inactive"


def _active_key(agent: Agent) -> AgentCredential | None:
    active = [c for c in agent.credentials if c.revoked_at is None]
    return max(active, key=lambda c: c.id) if active else None


EMPTY_STATS = {"total": 0, "allowed": 0, "blocked": 0, "pending": 0}


def agent_out(agent: Agent, counts: dict | None = None, stats: dict | None = None) -> dict:
    key = _active_key(agent)
    data = {
        "id": agent.id,
        "agent_id": agent.public_id,
        "name": agent.name,
        "description": agent.description or "",
        "connection_type": agent.connection_type,
        "status": agent.status,
        "connection_status": connection_status(agent, key),
        "last_seen_at": iso(agent.last_seen_at),
        "created_at": iso(agent.created_at),
        "credential": ({"key_prefix": key.key_prefix, "created_at": iso(key.created_at),
                        "last_used_at": iso(key.last_used_at)} if key else None),
        "has_active_key": key is not None,
        "key_prefix": key.key_prefix if key else None,
        "stats": stats or dict(EMPTY_STATS),
    }
    if counts is not None:
        data["activity_24h"] = counts
    return data


def _counts_24h(db: Session, workspace_id: int) -> dict[int, dict]:
    since = utcnow() - timedelta(hours=24)
    rows = (db.query(FirewallEvent.agent_pk, FirewallEvent.decision, func.count())
            .filter(FirewallEvent.workspace_id == workspace_id,
                    FirewallEvent.created_at >= since,
                    FirewallEvent.agent_pk.isnot(None))
            .group_by(FirewallEvent.agent_pk, FirewallEvent.decision).all())
    result: dict[int, dict] = {}
    for pk, decision, count in rows:
        bucket = result.setdefault(pk, {"total": 0, "ALLOW": 0, "BLOCK": 0, "REQUIRE_APPROVAL": 0})
        bucket[decision] = bucket.get(decision, 0) + count
        bucket["total"] += count
    return result


def _stats_all_time(db: Session, workspace_id: int) -> dict[int, dict]:
    """All-time counts per agent: total, allowed, blocked and pending approvals."""
    result: dict[int, dict] = {}
    rows = (db.query(FirewallEvent.agent_pk, FirewallEvent.decision, func.count())
            .filter(FirewallEvent.workspace_id == workspace_id,
                    FirewallEvent.agent_pk.isnot(None))
            .group_by(FirewallEvent.agent_pk, FirewallEvent.decision).all())
    for pk, decision, count in rows:
        bucket = result.setdefault(pk, dict(EMPTY_STATS))
        bucket["total"] += count
        if decision == "ALLOW":
            bucket["allowed"] += count
        elif decision == "BLOCK":
            bucket["blocked"] += count
    pending = (db.query(ApprovalRequest.agent_pk, func.count())
               .filter(ApprovalRequest.workspace_id == workspace_id,
                       ApprovalRequest.status == "PENDING",
                       ApprovalRequest.agent_pk.isnot(None))
               .group_by(ApprovalRequest.agent_pk).all())
    for pk, count in pending:
        result.setdefault(pk, dict(EMPTY_STATS))["pending"] = count
    return result


def get_agent_or_404(db: Session, ctx: WorkspaceContext, agent_id: int) -> Agent:
    agent = db.query(Agent).filter(Agent.id == agent_id,
                                   Agent.workspace_id == ctx.workspace.id).first()
    if agent is None:
        raise AppError(404, "agent_not_found", "We could not find that agent.",
                       "It may have been deleted.")
    return agent


def _new_credential(agent: Agent, db: Session) -> str:
    full_key, prefix, key_hash = generate_agent_key()
    db.add(AgentCredential(agent_id=agent.id, key_prefix=prefix, key_hash=key_hash))
    return full_key


@router.get("", summary="List agents")
def list_agents(ctx: WorkspaceContext = Depends(require_role("viewer")),
                db: Session = Depends(get_db)):
    agents = (db.query(Agent).filter(Agent.workspace_id == ctx.workspace.id)
              .order_by(Agent.created_at.desc()).all())
    counts = _counts_24h(db, ctx.workspace.id)
    stats = _stats_all_time(db, ctx.workspace.id)
    empty = {"total": 0, "ALLOW": 0, "BLOCK": 0, "REQUIRE_APPROVAL": 0}
    return {"items": [agent_out(a, counts.get(a.id, empty), stats.get(a.id)) for a in agents],
            "total": len(agents)}


@router.post("", status_code=201, summary="Register an agent and generate its key")
def create_agent(body: AgentIn, ctx: WorkspaceContext = Depends(require_role("admin")),
                 db: Session = Depends(get_db)):
    if db.query(Agent).filter(Agent.workspace_id == ctx.workspace.id,
                              func.lower(Agent.name) == body.name.lower()).first():
        raise AppError(409, "agent_name_taken", "You already have an agent with that name.",
                       "Choose a different name so you can tell them apart.")
    agent = Agent(public_id=f"agt_{uuid4().hex[:16]}", workspace_id=ctx.workspace.id,
                  name=body.name, description=body.description,
                  connection_type=body.connection_type, created_by=ctx.user.id)
    db.add(agent)
    db.flush()
    full_key = _new_credential(agent, db)
    audit.record(db, "agent.created", workspace_id=ctx.workspace.id, actor_type="user",
                 actor_id=ctx.user.id, actor_label=ctx.user.email, target_type="agent",
                 target_id=agent.public_id, details={"name": agent.name})
    db.commit()
    db.refresh(agent)
    return {
        "agent": agent_out(agent),
        "api_key": full_key,
        "notice": "Copy this key now. For your security it is shown only once.",
    }


@router.get("/{agent_id}", summary="Agent details")
def get_agent(agent_id: int, ctx: WorkspaceContext = Depends(require_role("viewer")),
              db: Session = Depends(get_db)):
    agent = get_agent_or_404(db, ctx, agent_id)
    counts = _counts_24h(db, ctx.workspace.id).get(
        agent.id, {"total": 0, "ALLOW": 0, "BLOCK": 0, "REQUIRE_APPROVAL": 0})
    return agent_out(agent, counts, _stats_all_time(db, ctx.workspace.id).get(agent.id))


_CONNECTION_TEXT = {
    "connected": ("Your agent contacted Falcon Eye recently.", None),
    "waiting": ("Falcon Eye has not heard from this agent yet.",
                "Run the 'Check the connection' command from the integration guide, "
                "using this agent's key, then test again."),
    "inactive": ("This agent connected before but has been quiet for a while.",
                 "Check that your agent is running and still uses its current key."),
    "no_key": ("This agent has no active key, so it cannot connect.",
               "Rotate the key to create a new one."),
    "disabled": ("This agent is turned off.", "Turn it on to let it connect."),
}


@router.post("/{agent_id}/test-connection",
             summary="Has this agent contacted Falcon Eye recently?")
def test_connection(agent_id: int, ctx: WorkspaceContext = Depends(require_role("viewer")),
                    db: Session = Depends(get_db)):
    agent = get_agent_or_404(db, ctx, agent_id)
    state = connection_status(agent, _active_key(agent))
    message, hint = _CONNECTION_TEXT[state]
    return {"status": "connected" if state == "connected" else "failed",
            "connection_status": state, "message": message, "hint": hint,
            "last_seen_at": iso(agent.last_seen_at)}


@router.patch("/{agent_id}", summary="Edit an agent, or enable / disable it")
def update_agent(agent_id: int, body: AgentUpdateIn,
                 ctx: WorkspaceContext = Depends(require_role("admin")),
                 db: Session = Depends(get_db)):
    agent = get_agent_or_404(db, ctx, agent_id)
    changes: dict = {}
    if body.name is not None and body.name.strip() != agent.name:
        clash = db.query(Agent).filter(
            Agent.workspace_id == ctx.workspace.id, Agent.id != agent.id,
            func.lower(Agent.name) == body.name.strip().lower()).first()
        if clash:
            raise AppError(409, "agent_name_taken", "You already have an agent with that name.")
        changes["name"] = agent.name = body.name.strip()
    if body.description is not None and body.description.strip() != (agent.description or ""):
        changes["description"] = agent.description = body.description.strip()
    if body.connection_type is not None and body.connection_type != agent.connection_type:
        changes["connection_type"] = agent.connection_type = body.connection_type
    action = "agent.updated"
    if body.status is not None and body.status != agent.status:
        changes["status"] = agent.status = body.status
        action = "agent.enabled" if body.status == "active" else "agent.disabled"
    if changes:
        audit.record(db, action, workspace_id=ctx.workspace.id, actor_type="user",
                     actor_id=ctx.user.id, actor_label=ctx.user.email,
                     target_type="agent", target_id=agent.public_id, details=changes)
        db.commit()
    return agent_out(agent)


@router.post("/{agent_id}/credentials/rotate",
             summary="Create a new key and revoke the old one")
def rotate_credentials(agent_id: int, ctx: WorkspaceContext = Depends(require_role("admin")),
                       db: Session = Depends(get_db)):
    agent = get_agent_or_404(db, ctx, agent_id)
    now = utcnow()
    for credential in agent.credentials:
        if credential.revoked_at is None:
            credential.revoked_at = now
    full_key = _new_credential(agent, db)
    agent.last_seen_at = None  # so the connection test starts fresh
    audit.record(db, "agent.credentials_rotated", workspace_id=ctx.workspace.id,
                 actor_type="user", actor_id=ctx.user.id, actor_label=ctx.user.email,
                 target_type="agent", target_id=agent.public_id)
    db.commit()
    db.refresh(agent)
    return {"agent": agent_out(agent), "api_key": full_key,
            "notice": "Copy this key now. The old key no longer works."}


@router.post("/{agent_id}/credentials/revoke",
             summary="Revoke a compromised key (the agent can no longer connect)")
def revoke_credentials(agent_id: int, ctx: WorkspaceContext = Depends(require_role("admin")),
                       db: Session = Depends(get_db)):
    agent = get_agent_or_404(db, ctx, agent_id)
    now = utcnow()
    revoked = 0
    for credential in agent.credentials:
        if credential.revoked_at is None:
            credential.revoked_at = now
            revoked += 1
    audit.record(db, "agent.credentials_revoked", workspace_id=ctx.workspace.id,
                 actor_type="user", actor_id=ctx.user.id, actor_label=ctx.user.email,
                 target_type="agent", target_id=agent.public_id, details={"revoked": revoked})
    db.commit()
    db.refresh(agent)
    return {"agent": agent_out(agent),
            "message": "The key was revoked. Generate a new one when you are ready."}


@router.post("/{agent_id}/credentials/new", status_code=201,
             summary="Generate a key for an agent that has none")
def new_credentials(agent_id: int, ctx: WorkspaceContext = Depends(require_role("admin")),
                    db: Session = Depends(get_db)):
    agent = get_agent_or_404(db, ctx, agent_id)
    if _active_key(agent) is not None:
        raise AppError(409, "key_exists", "This agent already has an active key.",
                       "Use 'Rotate key' to replace it.")
    full_key = _new_credential(agent, db)
    audit.record(db, "agent.credentials_created", workspace_id=ctx.workspace.id,
                 actor_type="user", actor_id=ctx.user.id, actor_label=ctx.user.email,
                 target_type="agent", target_id=agent.public_id)
    db.commit()
    db.refresh(agent)
    return {"agent": agent_out(agent), "api_key": full_key,
            "notice": "Copy this key now. For your security it is shown only once."}


@router.delete("/{agent_id}", summary="Delete an agent (its past events are kept)")
def delete_agent(agent_id: int, ctx: WorkspaceContext = Depends(require_role("admin")),
                 db: Session = Depends(get_db)):
    agent = get_agent_or_404(db, ctx, agent_id)
    # Policies assigned only to this agent go with it, so they can never
    # silently turn into workspace-wide policies.
    for policy in db.query(Policy).filter(Policy.agent_id == agent.id).all():
        db.delete(policy)
    name, public_id = agent.name, agent.public_id
    db.delete(agent)
    audit.record(db, "agent.deleted", workspace_id=ctx.workspace.id, actor_type="user",
                 actor_id=ctx.user.id, actor_label=ctx.user.email, target_type="agent",
                 target_id=public_id, details={"name": name})
    db.commit()
    return {"message": f"Agent '{name}' was deleted. Its past activity is still in your event log."}
