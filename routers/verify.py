"""Output verification: agents ask Falcon Eye to check text or a tool call before using it.

The check can only make the outcome STRICTER than the policy engine's decision.
It never grants permission and never overrides a BLOCK.
"""

import json
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.orm import Session

import approval_notify
import approval_service
import audit
import policy as engine
import verification
from catalog import infer_category
from config import settings
from database import get_db
from deps import AgentContext, WorkspaceContext, authenticate_agent, client_ip, require_role
from errors import AppError
from models import ApprovalRequest, FirewallEvent, Verification, iso, utcnow
from rate_limiter import limiter
from routers.policies import load_policy_views
from schemas import VerifyIn

router = APIRouter(tags=["Output verification"])

_STRICT = {"ALLOW": 0, "REQUIRE_APPROVAL": 1, "BLOCK": 2}


def _known_actions(db: Session, agent_pk: int) -> list[dict]:
    since = utcnow() - timedelta(hours=24)
    events = (db.query(FirewallEvent)
              .filter(FirewallEvent.agent_pk == agent_pk, FirewallEvent.created_at >= since)
              .order_by(FirewallEvent.id.desc()).limit(300).all())
    approval_ids = [e.approval_id for e in events if e.approval_id]
    status = {}
    if approval_ids:
        status = {a.approval_id: a.status for a in
                  db.query(ApprovalRequest).filter(ApprovalRequest.approval_id.in_(approval_ids)).all()}
    return [{"action": e.action, "resource": e.resource, "decision": e.decision,
             "approval_status": status.get(e.approval_id)} for e in events]


@router.post("/v1/verify", tags=["Agent API (for your AI agents)"],
             summary="Check an output or tool call before you use it")
def verify_output(body: VerifyIn, request: Request, background: BackgroundTasks,
                  ctx: AgentContext = Depends(authenticate_agent),
                  db: Session = Depends(get_db)):
    if not settings.verify_enabled:
        raise AppError(503, "verification_disabled", "Output verification is switched off.",
                       "An administrator can enable it with VERIFY_ENABLED=true.")
    agent, workspace = ctx.agent, ctx.workspace
    ip = client_ip(request)
    allowed, retry = limiter.hit(f"agent:{agent.id}", settings.agent_rate_limit_per_minute, 60)
    if not allowed:
        raise AppError(429, "rate_limited", "This agent is sending requests too quickly.",
                       f"Wait {retry} seconds, then try again.", headers={"Retry-After": str(retry)})

    tool = body.tool_call
    result = verification.verify(
        body.text, evidence=[e.model_dump() for e in body.evidence], kind=body.kind,
        tool_call=tool.model_dump() if tool else None,
        reported_actions=[r.model_dump() for r in body.reported_actions],
        known_actions=_known_actions(db, agent.id) if body.reported_actions else None,
        known_endpoints=body.known_endpoints, consequential=body.consequential,
        sensitivity=settings.verify_sensitivity)

    # 1) Mandatory policy first. The verifier may only tighten it.
    policy = None
    if agent.status != "active":
        decision, category = "BLOCK", infer_category(tool.action if tool else "verify")
        policy_reason = "This agent is switched off in Falcon Eye."
    elif tool:
        verdict = engine.evaluate(
            action=tool.action, resource=tool.resource, policies=load_policy_views(db, workspace.id),
            agent_pk=agent.id, declared_category=None, default_decision=workspace.default_decision)
        decision, category, policy_reason = verdict.decision, verdict.category, verdict.reason
        if verdict.policy_id:
            policy = {"id": verdict.policy_id, "name": verdict.policy_name}
    else:
        decision, category, policy_reason = "ALLOW", "verification", None
    policy_decision = decision
    if _STRICT[result["decision"]] > _STRICT[decision]:
        decision = result["decision"]
    result["policy_decision"] = policy_decision
    result["decision"] = decision
    result["requires_human_approval"] = decision == "REQUIRE_APPROVAL"
    if policy_decision != "ALLOW" and policy_reason:
        result["reasons"] = [f"Policy: {policy_reason}"] + result["reasons"]

    # 2) Record it. Only names and counts are stored, never the text.
    codes = sorted({s["code"] for s in result["signals"]})
    counts = {"claims_checked": result["checked"]["claims_checked"],
              "unsupported": len(result["unsupported_claims"]),
              "contradicted": len(result["contradicted_claims"])}
    vid = f"ver_{uuid4().hex}"
    event_id = approval_id = None
    if tool or decision != "ALLOW":
        event_id = f"evt_{uuid4().hex}"
        approval_id = f"apr_{uuid4().hex}" if decision == "REQUIRE_APPROVAL" else None
        action_name = tool.action if tool else f"verify:{body.kind}"
        resource = tool.resource if tool else ""
        why = "; ".join(result["reasons"])[:480]
        db.add(FirewallEvent(
            event_id=event_id, workspace_id=workspace.id, agent_id=agent.public_id,
            agent_pk=agent.id, agent_name=agent.name, action=action_name, resource=resource,
            category=category, decision=decision, reason="Output verification",
            decision_reason=f"Verification {result['risk_level']}: {why}"[:500],
            policy_id=policy["id"] if policy else None, policy_name=policy["name"] if policy else None,
            approval_id=approval_id, details=json.dumps({"verification_id": vid, "signals": codes}),
            source_ip=ip))
        if approval_id:
            db.add(ApprovalRequest(
                approval_id=approval_id, workspace_id=workspace.id, agent_id=agent.public_id,
                agent_pk=agent.id, agent_name=agent.name, action=action_name, resource=resource,
                reason=f"Held by output verification ({result['risk_level']}): {why}"[:500],
                category=category, event_id=event_id, status="PENDING",
                details=json.dumps({"verification_id": vid}),
                expires_at=approval_service.expiry_time(settings.approval_ttl_hours)))
    db.add(Verification(
        verification_id=vid, workspace_id=workspace.id, agent_pk=agent.id, agent_id=agent.public_id,
        agent_name=agent.name, kind=body.kind, status=result["verification_status"],
        risk_level=result["risk_level"], decision=decision, flagged=bool(result["flagged"] or decision != "ALLOW"),
        signal_codes=json.dumps(codes), counts=json.dumps(counts),
        text_sha256=verification.text_hash(body.text), text_length=len(body.text), event_id=event_id))
    audit.record(db, f"verification.{result['risk_level'].lower()}", workspace_id=workspace.id,
                 actor_type="agent", actor_id=agent.public_id, actor_label=agent.name,
                 target_type="verification", target_id=vid, ip=ip,
                 details={"decision": decision, "risk": result["risk_level"], "signals": codes[:15]})
    db.commit()
    if approval_id:
        approval_notify.notify_approvers(
            db, background, workspace, agent_name=agent.name,
            action=tool.action if tool else f"verify:{body.kind}",
            resource=tool.resource if tool else "",
            reason=f"Held by output verification ({result['risk_level']})")

    result.update({
        "verification_id": vid, "event_id": event_id, "approval_id": approval_id,
        "approval_status_url": f"/v1/approvals/{approval_id}" if approval_id else None,
        "policy": policy, "executed": False, "text_stored": False,
        "note": "Falcon Eye checks and decides. It does not run the action or rewrite your output.",
    })
    return result


@router.get("/workspaces/{workspace_id}/verifications", tags=["Output verification"],
            summary="Recent output verifications (names and counts only, never the text)")
def list_verifications(
    risk: str | None = Query(None, pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$"),
    agent_id: str | None = Query(None, max_length=64),
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    ctx: WorkspaceContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
):
    query = db.query(Verification).filter(Verification.workspace_id == ctx.workspace.id)
    if risk:
        query = query.filter(Verification.risk_level == risk)
    if agent_id:
        query = query.filter(Verification.agent_id == agent_id)
    total = query.count()
    rows = (query.order_by(Verification.created_at.desc(), Verification.id.desc())
            .offset(offset).limit(limit).all())

    def load(value):
        try:
            return json.loads(value) if value else None
        except ValueError:
            return None

    items = [{"verification_id": r.verification_id, "agent_id": r.agent_id, "agent_name": r.agent_name,
              "kind": r.kind, "status": r.status, "risk_level": r.risk_level, "decision": r.decision,
              "flagged": bool(r.flagged), "signals": load(r.signal_codes) or [],
              "counts": load(r.counts) or {}, "event_id": r.event_id,
              "created_at": iso(r.created_at)} for r in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}
