"""The agent-facing API: this is where AI agents ask permission."""

import json
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import approval_service
import audit
import policy as engine
from catalog import infer_category, normalize_category
from config import settings
from database import get_db
from deps import AgentContext, authenticate_agent, client_ip
from errors import AppError
from models import ApprovalRequest, FirewallEvent, iso
from rate_limiter import limiter
from routers.policies import load_policy_views
from schemas import ActionIn

router = APIRouter(prefix="/v1", tags=["Agent API (for your AI agents)"])


def _response(event: FirewallEvent, approval_id: str | None, duplicate: bool = False) -> dict:
    return {
        "event_id": event.event_id,
        "decision": event.decision,
        "message": {
            "ALLOW": "Allowed by your security policy.",
            "BLOCK": "Blocked by your security policy.",
            "REQUIRE_APPROVAL": "A human must approve this action first.",
        }.get(event.decision, ""),
        "reason": event.decision_reason,
        "category": event.category,
        "policy": ({"id": event.policy_id, "name": event.policy_name}
                   if event.policy_id else None),
        "approval_id": approval_id,
        "approval_status_url": f"/v1/approvals/{approval_id}" if approval_id else None,
        "duplicate": duplicate,
        # Falcon Eye only decides. It does not perform the action itself.
        "executed": False,
        "note": "This is a firewall decision. Falcon Eye does not carry out the action.",
    }


@router.api_route("/ping", methods=["GET", "POST"],
                  summary="Test the connection from your agent")
def ping(request: Request, ctx: AgentContext = Depends(authenticate_agent),
         db: Session = Depends(get_db)):
    audit.record(db, "agent.ping", workspace_id=ctx.workspace.id, actor_type="agent",
                 actor_id=ctx.agent.public_id, actor_label=ctx.agent.name,
                 ip=client_ip(request))
    db.commit()
    return {"status": "connected", "agent": ctx.agent.name, "agent_id": ctx.agent.public_id,
            "workspace": ctx.workspace.name,
            "agent_enabled": ctx.agent.status == "active"}


@router.post("/evaluate", summary="Ask the firewall whether an action is allowed")
def evaluate(body: ActionIn, request: Request,
             ctx: AgentContext = Depends(authenticate_agent),
             db: Session = Depends(get_db)):
    agent, workspace = ctx.agent, ctx.workspace
    ip = client_ip(request)

    allowed, retry = limiter.hit(f"agent:{agent.id}", settings.agent_rate_limit_per_minute, 60)
    if not allowed:
        raise AppError(429, "rate_limited", "This agent is sending requests too quickly.",
                       f"Wait {retry} seconds, then try again.",
                       headers={"Retry-After": str(retry)})

    # Duplicate / replay protection
    if body.request_id:
        prior = _find_prior(db, agent.id, body.request_id)
        if prior is not None:
            db.commit()  # keeps "last seen" up to date
            return _replay(prior, body)

    if agent.status != "active":
        verdict = engine.Verdict(
            decision="BLOCK", message="Blocked: this agent is disabled.",
            reason="This agent is switched off in Falcon Eye, so every action is blocked.",
            category=normalize_category(body.category) or infer_category(body.action))
    else:
        verdict = engine.evaluate(
            action=body.action, resource=body.resource,
            policies=load_policy_views(db, workspace.id), agent_pk=agent.id,
            declared_category=body.category, default_decision=workspace.default_decision)

    event_id = f"evt_{uuid4().hex}"
    approval_id = f"apr_{uuid4().hex}" if verdict.decision == "REQUIRE_APPROVAL" else None
    details = json.dumps(body.metadata, default=str) if body.metadata else None

    event = FirewallEvent(
        event_id=event_id, workspace_id=workspace.id, agent_id=agent.public_id,
        agent_pk=agent.id, agent_name=agent.name, action=body.action,
        resource=body.resource, category=verdict.category, decision=verdict.decision,
        reason=body.reason or None, decision_reason=verdict.reason,
        policy_id=verdict.policy_id, policy_name=verdict.policy_name,
        request_id=body.request_id, approval_id=approval_id, details=details, source_ip=ip)
    db.add(event)
    if approval_id:
        db.add(ApprovalRequest(
            approval_id=approval_id, workspace_id=workspace.id, agent_id=agent.public_id,
            agent_pk=agent.id, agent_name=agent.name, action=body.action,
            resource=body.resource, reason=body.reason, category=verdict.category,
            event_id=event_id, status="PENDING", details=details,
            expires_at=approval_service.expiry_time(settings.approval_ttl_hours)))
    audit.record(db, f"firewall.{verdict.decision.lower()}", workspace_id=workspace.id,
                 actor_type="agent", actor_id=agent.public_id, actor_label=agent.name,
                 target_type="event", target_id=event_id, ip=ip,
                 details={"action": body.action, "resource": body.resource[:200]})
    try:
        db.commit()
    except IntegrityError:
        # Two identical requests raced; the other one won. Return its result.
        db.rollback()
        prior = _find_prior(db, agent.id, body.request_id) if body.request_id else None
        if prior is None:
            raise
        return _replay(prior, body)
    return _response(event, approval_id)


def _find_prior(db: Session, agent_pk: int, request_id: str) -> FirewallEvent | None:
    return (db.query(FirewallEvent)
            .filter(FirewallEvent.agent_pk == agent_pk,
                    FirewallEvent.request_id == request_id).first())


def _replay(prior: FirewallEvent, body: ActionIn) -> dict:
    if prior.action != body.action or (prior.resource or "") != body.resource:
        raise AppError(
            409, "request_id_reused",
            "That request_id was already used for a different action.",
            "Use a new, unique request_id for every new request.")
    return _response(prior, prior.approval_id, duplicate=True)


@router.get("/approvals/{approval_id}", summary="Check whether a human has decided yet")
def approval_status(approval_id: str, ctx: AgentContext = Depends(authenticate_agent),
                    db: Session = Depends(get_db)):
    approval_service.expire_stale(db, ctx.workspace.id)
    approval = (db.query(ApprovalRequest)
                .filter(ApprovalRequest.approval_id == approval_id,
                        ApprovalRequest.agent_pk == ctx.agent.id).first())
    db.commit()  # persists last_seen_at
    if approval is None:
        raise AppError(404, "approval_not_found",
                       "No approval request with that id exists for this agent.")
    return {
        "approval_id": approval.approval_id, "status": approval.status,
        "action": approval.action, "resource": approval.resource,
        "decided_at": iso(approval.decided_at), "expires_at": iso(approval.expires_at),
        "executed": False,
        "note": "APPROVED means a human said yes. Your agent is still responsible "
                "for performing the action.",
    }
