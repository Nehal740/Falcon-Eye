import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import audit
import policy as engine
from catalog import CATEGORIES, POLICY_TEMPLATES, get_template
from database import get_db
from deps import WorkspaceContext, get_current_user, require_role
from errors import AppError
from models import Agent, Policy, PolicyRule, PolicyVersion, User, iso
from schemas import PolicyIn, PolicyUpdateIn, RuleIn, SimulateIn, TemplateIn

router = APIRouter(tags=["Policies"])


# ---------------------------------------------------------------- helpers

def rule_out(rule: PolicyRule) -> dict:
    return {"id": rule.id, "target_type": rule.target_type, "target_value": rule.target_value,
            "resource_pattern": rule.resource_pattern, "effect": rule.effect}


def policy_out(policy: Policy, agent_names: dict[int, str] | None = None) -> dict:
    return {
        "id": policy.id, "name": policy.name, "description": policy.description or "",
        "version": max((v.version for v in policy.versions), default=1),
        "enabled": policy.enabled, "priority": policy.priority,
        "agent_id": policy.agent_id,
        "agent_name": (agent_names or {}).get(policy.agent_id) if policy.agent_id else None,
        "scope": "agent" if policy.agent_id else "workspace",
        "rules": [rule_out(r) for r in policy.rules],
        "created_at": iso(policy.created_at), "updated_at": iso(policy.updated_at),
    }


def load_policy_views(db: Session, workspace_id: int) -> list[engine.PolicyView]:
    """Plain-data copies of a workspace's policies for the engine."""
    policies = db.query(Policy).filter(Policy.workspace_id == workspace_id).all()
    return [
        engine.PolicyView(
            id=p.id, name=p.name, priority=p.priority, agent_pk=p.agent_id, enabled=p.enabled,
            rules=tuple(engine.RuleView(r.id, r.target_type, r.target_value,
                                        r.resource_pattern, r.effect) for r in p.rules))
        for p in policies
    ]


def _validate_rules(rules: list[RuleIn]) -> None:
    for rule in rules:
        try:
            rule.check()
        except ValueError as exc:
            raise AppError(422, "validation_error", str(exc),
                           "Pick a category from the list, or use an action name pattern.")


def _check_agent(db: Session, ctx: WorkspaceContext, agent_id: int | None) -> None:
    if agent_id is None:
        return
    if not db.query(Agent).filter(Agent.id == agent_id,
                                  Agent.workspace_id == ctx.workspace.id).first():
        raise AppError(404, "agent_not_found", "We could not find that agent in this workspace.")


def _snapshot(policy: Policy) -> str:
    return json.dumps(policy_out(policy), default=str)


def _add_version(db: Session, policy: Policy, change: str, user: User) -> None:
    last = max((v.version for v in policy.versions), default=0)
    db.add(PolicyVersion(policy_id=policy.id, version=last + 1, change_type=change,
                         snapshot=_snapshot(policy), changed_by=user.id))


def _set_rules(policy: Policy, rules: list[RuleIn]) -> None:
    policy.rules.clear()
    for position, rule in enumerate(rules):
        policy.rules.append(PolicyRule(
            target_type=rule.target_type,
            target_value=rule.target_value.lower() if rule.target_type == "category" else rule.target_value,
            resource_pattern=rule.resource_pattern, effect=rule.effect, position=position))


def _agent_names(db: Session, workspace_id: int) -> dict[int, str]:
    return {a.id: a.name for a in db.query(Agent).filter(Agent.workspace_id == workspace_id).all()}


def _get_policy(db: Session, ctx: WorkspaceContext, policy_id: int) -> Policy:
    policy = db.query(Policy).filter(Policy.id == policy_id,
                                     Policy.workspace_id == ctx.workspace.id).first()
    if policy is None:
        raise AppError(404, "policy_not_found", "We could not find that policy.",
                       "It may have been deleted.")
    return policy


def _actor(ctx: WorkspaceContext) -> dict:
    return {"workspace_id": ctx.workspace.id, "actor_type": "user",
            "actor_id": ctx.user.id, "actor_label": ctx.user.email}


# ---------------------------------------------------------------- catalogue

@router.get("/action-catalog", summary="Action categories and starter templates")
def action_catalog(_user: User = Depends(get_current_user)):
    return {
        "categories": CATEGORIES,
        "effects": [
            {"id": "ALLOW", "label": "Allow", "description": "The agent may go ahead."},
            {"id": "REQUIRE_APPROVAL", "label": "Ask a human",
             "description": "Pause until someone approves it."},
            {"id": "BLOCK", "label": "Block", "description": "The agent may not do this."},
        ],
        "templates": [{"id": t["id"], "name": t["name"], "description": t["description"],
                       "rule_count": len(t["rules"])} for t in POLICY_TEMPLATES],
    }


@router.get("/action-categories", summary="Action categories (for the policy builder)")
def action_categories(_user: User = Depends(get_current_user)):
    return {"items": [{**c, "key": c["id"]} for c in CATEGORIES]}


@router.get("/policy-templates", summary="Ready-made policy templates")
def policy_templates(_user: User = Depends(get_current_user)):
    return {"items": [{**t, "key": t["id"]} for t in POLICY_TEMPLATES]}


# ---------------------------------------------------------------- CRUD

@router.get("/workspaces/{workspace_id}/policies", summary="List policies")
def list_policies(ctx: WorkspaceContext = Depends(require_role("viewer")),
                  db: Session = Depends(get_db)):
    policies = (db.query(Policy).filter(Policy.workspace_id == ctx.workspace.id)
                .order_by(Policy.priority, Policy.id).all())
    names = _agent_names(db, ctx.workspace.id)
    return {"items": [policy_out(p, names) for p in policies], "total": len(policies),
            "default_decision": ctx.workspace.default_decision}


@router.post("/workspaces/{workspace_id}/policies", status_code=201, summary="Create a policy")
def create_policy(body: PolicyIn, ctx: WorkspaceContext = Depends(require_role("admin")),
                  db: Session = Depends(get_db)):
    _validate_rules(body.rules)
    _check_agent(db, ctx, body.agent_id)
    policy = Policy(workspace_id=ctx.workspace.id, agent_id=body.agent_id, name=body.name,
                    description=body.description, enabled=body.enabled,
                    priority=body.priority, created_by=ctx.user.id)
    db.add(policy)
    db.flush()
    _set_rules(policy, body.rules)
    db.flush()
    _add_version(db, policy, "created", ctx.user)
    audit.record(db, "policy.created", target_type="policy", target_id=policy.id,
                 details={"name": policy.name, "rules": len(body.rules)}, **_actor(ctx))
    db.commit()
    db.refresh(policy)
    return policy_out(policy, _agent_names(db, ctx.workspace.id))


@router.post("/workspaces/{workspace_id}/policies/from-template", status_code=201,
             summary="Create a policy from a ready-made template")
def policy_from_template(body: TemplateIn, ctx: WorkspaceContext = Depends(require_role("admin")),
                         db: Session = Depends(get_db)):
    template = get_template(body.template_id)
    if template is None:
        raise AppError(404, "template_not_found", "That template does not exist.")
    _check_agent(db, ctx, body.agent_id)
    policy = Policy(workspace_id=ctx.workspace.id, agent_id=body.agent_id, name=template["name"],
                    description=template["description"], enabled=True,
                    priority=template["priority"], created_by=ctx.user.id)
    db.add(policy)
    db.flush()
    _set_rules(policy, [RuleIn(**r) for r in template["rules"]])
    db.flush()
    _add_version(db, policy, "created", ctx.user)
    audit.record(db, "policy.created", target_type="policy", target_id=policy.id,
                 details={"name": policy.name, "template": template["id"]}, **_actor(ctx))
    db.commit()
    db.refresh(policy)
    return policy_out(policy, _agent_names(db, ctx.workspace.id))


@router.get("/workspaces/{workspace_id}/policies/{policy_id}", summary="Policy details")
def get_policy(policy_id: int, ctx: WorkspaceContext = Depends(require_role("viewer")),
               db: Session = Depends(get_db)):
    return policy_out(_get_policy(db, ctx, policy_id), _agent_names(db, ctx.workspace.id))


@router.patch("/workspaces/{workspace_id}/policies/{policy_id}",
              summary="Edit a policy, or switch it on / off")
def update_policy(policy_id: int, body: PolicyUpdateIn,
                  ctx: WorkspaceContext = Depends(require_role("admin")),
                  db: Session = Depends(get_db)):
    policy = _get_policy(db, ctx, policy_id)
    change = "updated"
    if body.rules is not None:
        _validate_rules(body.rules)
    if body.name is not None:
        policy.name = body.name.strip()
    if body.description is not None:
        policy.description = body.description.strip()
    if body.priority is not None:
        policy.priority = body.priority
    if body.assign_to_all_agents:
        policy.agent_id = None
    elif body.agent_id is not None:
        _check_agent(db, ctx, body.agent_id)
        policy.agent_id = body.agent_id
    if body.enabled is not None and body.enabled != policy.enabled:
        policy.enabled = body.enabled
        only_toggle = all(v is None for v in (body.name, body.description, body.priority,
                                              body.rules, body.agent_id)) and not body.assign_to_all_agents
        if only_toggle:
            change = "enabled" if policy.enabled else "disabled"
    if body.rules is not None:
        _set_rules(policy, body.rules)
    db.flush()
    _add_version(db, policy, change, ctx.user)
    audit.record(db, f"policy.{change}", target_type="policy", target_id=policy.id,
                 details={"name": policy.name}, **_actor(ctx))
    db.commit()
    db.refresh(policy)
    return policy_out(policy, _agent_names(db, ctx.workspace.id))


@router.delete("/workspaces/{workspace_id}/policies/{policy_id}", summary="Delete a policy")
def delete_policy(policy_id: int, ctx: WorkspaceContext = Depends(require_role("admin")),
                  db: Session = Depends(get_db)):
    policy = _get_policy(db, ctx, policy_id)
    name = policy.name
    db.delete(policy)
    audit.record(db, "policy.deleted", target_type="policy", target_id=policy_id,
                 details={"name": name}, **_actor(ctx))
    db.commit()
    return {"message": f"Policy '{name}' was deleted."}


@router.get("/workspaces/{workspace_id}/policies/{policy_id}/history",
            summary="Every change made to a policy")
def policy_history(policy_id: int, ctx: WorkspaceContext = Depends(require_role("viewer")),
                   db: Session = Depends(get_db)):
    policy = _get_policy(db, ctx, policy_id)
    users = {u.id: u for u in db.query(User).filter(
        User.id.in_([v.changed_by for v in policy.versions if v.changed_by])).all()}
    items = []
    for version in reversed(policy.versions):
        user = users.get(version.changed_by)
        try:
            snapshot = json.loads(version.snapshot)
        except ValueError:
            snapshot = None
        items.append({"version": version.version, "change_type": version.change_type,
                      "changed_by": user.full_name if user else "Unknown",
                      "created_at": iso(version.created_at), "snapshot": snapshot})
    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------- try it out

@router.post("/workspaces/{workspace_id}/policies/simulate",
             summary="Test what the firewall would decide (nothing is recorded)")
def simulate(body: SimulateIn, ctx: WorkspaceContext = Depends(require_role("viewer")),
             db: Session = Depends(get_db)):
    _check_agent(db, ctx, body.agent_id)
    verdict = engine.evaluate(
        action=body.action, resource=body.resource,
        policies=load_policy_views(db, ctx.workspace.id), agent_pk=body.agent_id,
        declared_category=body.category, default_decision=ctx.workspace.default_decision)
    return {"decision": verdict.decision, "message": verdict.message, "reason": verdict.reason,
            "category": verdict.category, "policy_id": verdict.policy_id,
            "policy_name": verdict.policy_name, "used_default": verdict.used_default,
            "recorded": False}
