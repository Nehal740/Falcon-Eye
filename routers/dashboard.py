import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

import approval_service
from database import get_db
from deps import WorkspaceContext, require_role
from models import (
    Agent, ApprovalRequest, AuditLog, FirewallEvent, Policy, Verification, aware, iso, utcnow,
)
from routers.agents import agent_out
from routers.events import _approval_map, event_out

router = APIRouter(prefix="/workspaces/{workspace_id}/dashboard", tags=["Dashboard"])


@router.get("", summary="Everything the dashboard needs, from real data")
def dashboard(ctx: WorkspaceContext = Depends(require_role("viewer")),
              db: Session = Depends(get_db)):
    wid = ctx.workspace.id
    approval_service.expire_stale(db, wid)
    now = utcnow()

    # Agents
    agents = db.query(Agent).filter(Agent.workspace_id == wid).all()
    agent_cards = [agent_out(a) for a in agents]
    active_agents = sum(1 for a in agents if a.status == "active")
    connected_agents = sum(1 for c in agent_cards if c["connection_status"] == "connected")

    # Events by decision (all time and last 24h)
    totals = dict(db.query(FirewallEvent.decision, func.count())
                  .filter(FirewallEvent.workspace_id == wid)
                  .group_by(FirewallEvent.decision).all())
    since = now - timedelta(hours=24)
    last_day = dict(db.query(FirewallEvent.decision, func.count())
                    .filter(FirewallEvent.workspace_id == wid, FirewallEvent.created_at >= since)
                    .group_by(FirewallEvent.decision).all())

    # Approvals
    pending_rows = (db.query(ApprovalRequest)
                    .filter(ApprovalRequest.workspace_id == wid,
                            ApprovalRequest.status == "PENDING").all())
    pending = len(pending_rows)

    # Policies
    policies = db.query(Policy).filter(Policy.workspace_id == wid).all()
    enabled_policies = sum(1 for p in policies if p.enabled)
    rule_count = sum(len(p.rules) for p in policies if p.enabled)

    # Recent activity
    recent = (db.query(FirewallEvent).filter(FirewallEvent.workspace_id == wid)
              .order_by(FirewallEvent.created_at.desc(), FirewallEvent.id.desc()).limit(8).all())
    approvals = _approval_map(db, wid, recent)

    by_agent = {}
    rows = (db.query(FirewallEvent.agent_pk, func.count(), func.max(FirewallEvent.created_at))
            .filter(FirewallEvent.workspace_id == wid, FirewallEvent.agent_pk.isnot(None))
            .group_by(FirewallEvent.agent_pk).all())
    for pk, count, last in rows:
        by_agent[pk] = (count, last)
    agent_activity = []
    for agent, card in zip(agents, agent_cards):
        count, last = by_agent.get(agent.id, (0, None))
        agent_activity.append({
            "id": agent.id, "name": agent.name, "connection_status": card["connection_status"],
            "total_events": count, "last_event_at": iso(last),
            "last_seen_at": card["last_seen_at"]})
    agent_activity.sort(key=lambda a: a["total_events"], reverse=True)

    alerts = _alerts(db, ctx, now, agents, agent_cards, policies, enabled_policies,
                     pending_rows, last_day)

    # Extra views for the dashboard page: a 7-day chart, busiest agents,
    # how often each policy decided, and the newest approval requests.
    days = [(now - timedelta(days=i)).date() for i in range(6, -1, -1)]
    daily = {d.isoformat(): {"date": d.isoformat(), "allowed": 0, "blocked": 0,
                             "require_approval": 0} for d in days}
    week_start = datetime(days[0].year, days[0].month, days[0].day, tzinfo=timezone.utc)
    day_col = func.date(FirewallEvent.created_at)
    bucket_name = {"ALLOW": "allowed", "BLOCK": "blocked", "REQUIRE_APPROVAL": "require_approval"}
    for day, decision, count in (db.query(day_col, FirewallEvent.decision, func.count())
                                 .filter(FirewallEvent.workspace_id == wid,
                                         FirewallEvent.created_at >= week_start)
                                 .group_by(day_col, FirewallEvent.decision).all()):
        bucket = daily.get(str(day)[:10])
        if bucket is not None and decision in bucket_name:
            bucket[bucket_name[decision]] += count

    per_agent: dict[int, list[int]] = {}
    for pk, decision, count in (db.query(FirewallEvent.agent_pk, FirewallEvent.decision,
                                         func.count())
                                .filter(FirewallEvent.workspace_id == wid,
                                        FirewallEvent.agent_pk.isnot(None))
                                .group_by(FirewallEvent.agent_pk, FirewallEvent.decision).all()):
        entry = per_agent.setdefault(pk, [0, 0])
        entry[0] += count
        if decision == "BLOCK":
            entry[1] += count
    top_agents = sorted(
        ({"agent_id": a.public_id, "name": a.name, "events": per_agent[a.id][0],
          "blocked": per_agent[a.id][1]} for a in agents if a.id in per_agent),
        key=lambda item: item["events"], reverse=True)[:5]

    matches = dict(db.query(FirewallEvent.policy_id, func.count())
                   .filter(FirewallEvent.workspace_id == wid, FirewallEvent.policy_id.isnot(None))
                   .group_by(FirewallEvent.policy_id).all())
    policy_stats = sorted(
        ({"id": p.id, "name": p.name, "enabled": p.enabled, "matches": matches.get(p.id, 0)}
         for p in policies), key=lambda item: item["matches"], reverse=True)[:6]

    newest_pending = sorted(pending_rows, key=lambda r: aware(r.created_at) or now,
                            reverse=True)[:3]

    return {
        "workspace": {"id": wid, "name": ctx.workspace.name,
                      "default_decision": ctx.workspace.default_decision},
        "stats": {
            "agents_total": len(agents), "agents_active": active_agents,
            "agents_connected": connected_agents,
            "events_total": sum(totals.values()),
            "allowed": totals.get("ALLOW", 0), "blocked": totals.get("BLOCK", 0),
            "require_approval": totals.get("REQUIRE_APPROVAL", 0),
            "pending_approvals": pending,
            "events_24h": sum(last_day.values()),
            "allowed_24h": last_day.get("ALLOW", 0), "blocked_24h": last_day.get("BLOCK", 0),
            "approval_24h": last_day.get("REQUIRE_APPROVAL", 0),
        },
        "policies": {"total": len(policies), "enabled": enabled_policies,
                     "disabled": len(policies) - enabled_policies, "rules": rule_count},
        "totals": {
            "agents": len(agents), "active_agents": active_agents,
            "events": sum(totals.values()), "allowed": totals.get("ALLOW", 0),
            "blocked": totals.get("BLOCK", 0), "pending_approvals": pending,
            "policies": len(policies), "enabled_policies": enabled_policies,
        },
        "last_24h": {"events": sum(last_day.values()), "allowed": last_day.get("ALLOW", 0),
                     "blocked": last_day.get("BLOCK", 0)},
        "daily": [daily[d.isoformat()] for d in days],
        "top_agents": top_agents,
        "policy_stats": policy_stats,
        "pending_approvals": [approval_service.approval_out(r) for r in newest_pending],
        "recent_events": [event_out(e, approvals) for e in recent],
        "agent_activity": agent_activity[:6],
        "alerts": alerts,
        "trust": _trust_summary(db, wid, now),
        "generated_at": iso(now),
    }


def _trust_summary(db: Session, wid: int, now) -> dict:
    """Numbers for the 'AI Security & Trust' panel (last 7 days). Counts only, never text."""
    rows = (db.query(Verification).filter(Verification.workspace_id == wid,
                                          Verification.created_at >= now - timedelta(days=7))
            .order_by(Verification.created_at.desc(), Verification.id.desc()).limit(2000).all())
    by_risk = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    held = blocked = injections = secrets = unsupported = contradicted = 0
    for r in rows:
        by_risk[r.risk_level] = by_risk.get(r.risk_level, 0) + 1
        held += r.decision == "REQUIRE_APPROVAL"
        blocked += r.decision == "BLOCK"
        try:
            codes = json.loads(r.signal_codes or "[]")
            counts = json.loads(r.counts or "{}")
        except ValueError:
            codes, counts = [], {}
        injections += any("injection" in c for c in codes)
        secrets += any(c.startswith(("secret.", "argument_secret.")) for c in codes)
        unsupported += counts.get("unsupported", 0)
        contradicted += counts.get("contradicted", 0)
    recent = [{"verification_id": r.verification_id, "agent_name": r.agent_name, "kind": r.kind,
               "risk_level": r.risk_level, "decision": r.decision, "status": r.status,
               "signals": (json.loads(r.signal_codes or "[]") if r.signal_codes else [])[:4],
               "created_at": iso(r.created_at)}
              for r in rows if r.risk_level in ("MEDIUM", "HIGH", "CRITICAL")][:5]
    return {"days": 7, "total": len(rows), "by_risk": by_risk, "held_for_approval": held,
            "blocked": blocked, "injection_signals": injections, "secret_signals": secrets,
            "unsupported_claims": unsupported, "contradicted_claims": contradicted,
            "recent_flagged": recent}


def _alerts(db, ctx, now, agents, cards, policies, enabled_policies, pending_rows, last_day):
    wid = ctx.workspace.id
    alerts = []

    if not agents:
        alerts.append({"id": "no_agents", "severity": "info", "page": "Agents",
                       "title": "Connect your first AI agent",
                       "message": "Add an agent to start monitoring what it does."})
    if enabled_policies == 0:
        alerts.append({"id": "no_policies", "severity": "warning", "page": "Policies",
                       "title": "No active policies",
                       "message": "Every action is currently handled by your workspace default "
                                  f"({ctx.workspace.default_decision.replace('_', ' ').lower()}). "
                                  "Add a policy so agents can do their approved work."})

    blocked_hour = (db.query(func.count(FirewallEvent.id))
                    .filter(FirewallEvent.workspace_id == wid, FirewallEvent.decision == "BLOCK",
                            FirewallEvent.created_at >= now - timedelta(hours=1)).scalar() or 0)
    if blocked_hour >= 5:
        alerts.append({"id": "blocked_spike", "severity": "warning", "page": "Events",
                       "title": f"{blocked_hour} blocked actions in the last hour",
                       "message": "An agent may be misbehaving or a policy may be too strict."})

    old = [p for p in pending_rows
           if aware(p.created_at) and now - aware(p.created_at) > timedelta(hours=1)]
    if old:
        alerts.append({"id": "stale_approvals", "severity": "info", "page": "Approvals",
                       "title": f"{len(old)} approval request(s) waiting over an hour",
                       "message": "Agents are paused until someone decides."})

    failed = (db.query(func.count(AuditLog.id))
              .filter(AuditLog.workspace_id == wid, AuditLog.action == "agent.auth_failed",
                      AuditLog.created_at >= now - timedelta(hours=24)).scalar() or 0)
    if failed:
        alerts.append({"id": "bad_keys", "severity": "warning", "page": "Settings",
                       "title": f"{failed} rejected agent key attempt(s) in 24 hours",
                       "message": "Someone used a wrong or revoked key. If a key leaked, "
                                  "rotate it under Agents."})

    critical = (db.query(func.count(Verification.id))
                .filter(Verification.workspace_id == wid, Verification.risk_level == "CRITICAL",
                        Verification.created_at >= now - timedelta(hours=24)).scalar() or 0)
    if critical:
        alerts.append({"id": "critical_verifications", "severity": "warning", "page": "Overview",
                       "title": f"{critical} critical output check(s) in the last 24 hours",
                       "message": "Agent output or tool calls looked dangerous and were blocked. "
                                  "See the AI Security & Trust panel."})

    for agent, card in zip(agents, cards):
        if card["connection_status"] == "no_key":
            alerts.append({"id": f"nokey_{agent.id}", "severity": "info", "page": "Agents",
                           "title": f"'{agent.name}' has no active key",
                           "message": "Generate a new key so it can connect."})

    disabled_hits = (db.query(func.count(FirewallEvent.id))
                     .filter(FirewallEvent.workspace_id == wid,
                             FirewallEvent.decision_reason.like("This agent is switched off%"),
                             FirewallEvent.created_at >= now - timedelta(hours=24)).scalar() or 0)
    if disabled_hits:
        alerts.append({"id": "disabled_active", "severity": "warning", "page": "Agents",
                       "title": f"A disabled agent tried to act {disabled_hits} time(s)",
                       "message": "Its actions were blocked. Revoke its key if you did not expect this."})
    return alerts
