from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import assistant_service as svc
import retrieval
from config import settings
from database import get_db
from deps import WorkspaceContext, require_role
from errors import AppError
from models import Agent, AssistantConfig, FirewallEvent, Policy
from rate_limiter import limiter
from schemas import AssistantIn

router = APIRouter(prefix="/workspaces/{workspace_id}/assistant", tags=["AI assistant"])


def _workspace_summary(db: Session, ctx: WorkspaceContext) -> str:
    """Facts about *this* workspace only. Never includes keys or hashes."""
    wid = ctx.workspace.id
    agents = db.query(Agent).filter(Agent.workspace_id == wid).limit(20).all()
    policies = db.query(Policy).filter(Policy.workspace_id == wid).limit(20).all()
    lines = [f"Workspace: {ctx.workspace.name}",
             f"Default when no rule matches: {ctx.workspace.default_decision}",
             f"User's role: {ctx.role}"]
    lines.append("Agents: " + (", ".join(f"{a.name} ({a.status})" for a in agents) or "none yet"))
    lines.append("Policies: " + (", ".join(
        f"{p.name} ({'on' if p.enabled else 'off'}, priority {p.priority}, {len(p.rules)} rules)"
        for p in policies) or "none yet"))
    return "\n".join(lines)


def _event_records(db: Session, ctx: WorkspaceContext, message: str) -> list[str]:
    records = []
    for event_id in svc.find_event_ids(message):
        event = (db.query(FirewallEvent)
                 .filter(FirewallEvent.workspace_id == ctx.workspace.id,
                         FirewallEvent.event_id == event_id).first())
        if event:
            records.append(
                f"event {event.event_id}: agent={event.agent_name}; action={event.action}; "
                f"resource={(event.resource or '')[:120]}; decision={event.decision}; "
                f"why={event.decision_reason}; policy={event.policy_name or 'none'}; "
                f"agent_said={(event.reason or '')[:200]}")
    return records


@router.get("/status", summary="Is the live AI model connected?")
def status(ctx: WorkspaceContext = Depends(require_role("viewer")),
           db: Session = Depends(get_db)):
    config = db.query(AssistantConfig).filter(AssistantConfig.workspace_id == ctx.workspace.id).first()
    return {"enabled": config.enabled if config else True,
            "live_ai_configured": settings.llm_enabled}


@router.post("/chat", summary="Ask the support assistant")
def chat(body: AssistantIn, ctx: WorkspaceContext = Depends(require_role("viewer")),
         db: Session = Depends(get_db)):
    config = db.query(AssistantConfig).filter(AssistantConfig.workspace_id == ctx.workspace.id).first()
    if config is not None and not config.enabled:
        raise AppError(403, "assistant_disabled",
                       "The AI assistant is turned off for this workspace.",
                       "A workspace admin can turn it on under Settings.")

    allowed, retry = limiter.hit(f"assistant:{ctx.user.id}", 20, 60)
    if not allowed:
        raise AppError(429, "rate_limited", "You are asking questions very quickly.",
                       f"Wait {retry} seconds and try again.", headers={"Retry-After": str(retry)})

    results = retrieval.search(svc.knowledge(), body.message, k=3)
    excerpts = [chunk for _score, chunk in results]
    sources = [{"title": c.title, "source": c.source} for c in excerpts]

    notice = None
    mode = "ai"
    try:
        system = svc.build_system_prompt(
            excerpts, _workspace_summary(db, ctx), _event_records(db, ctx, body.message),
            (config.custom_instructions if config else "") or "")
        answer = svc.call_llm(system, [m.model_dump() for m in body.history], body.message)
    except svc.LLMUnavailable as exc:
        mode = "docs"
        answer = svc.docs_only_answer(results)
        notice = ("The live AI model is not connected, so this answer comes straight from "
                  "the Falcon Eye guides." if not settings.llm_enabled else
                  f"The AI model could not be reached ({exc}). Showing the Falcon Eye guides instead.")
    return {"answer": answer, "mode": mode, "live_ai": mode == "ai",
            "sources": sources, "notice": notice}
