"""The Falcon Eye policy engine.

This module is deliberately free of database and web-framework imports: it
receives plain data and returns a verdict. That keeps the most security-
critical logic small, deterministic and easy to test.

How a decision is made
----------------------
1. Only *enabled* policies that apply to the agent are considered. A policy
   applies when it is workspace-wide (``agent_pk is None``) or assigned to
   this specific agent.
2. Every rule is checked against the request. A rule matches when:
   * its target matches - a *category* rule compares with the category the
     agent declared AND the category Falcon Eye inferred from the action
     name; an *action* rule uses a case-insensitive wildcard pattern
     (``*`` and ``?``) on the action name; and
   * its resource pattern matches the requested resource (default ``*``).
3. Among all matching rules, the policy with the lowest priority number wins
   (1 = checked first). If several matching rules share that priority, the
   strictest effect wins: BLOCK > REQUIRE_APPROVAL > ALLOW.
4. If nothing matches, the workspace default applies (BLOCK or
   REQUIRE_APPROVAL - never ALLOW). Unknown actions are never allowed.

The engine decides; it never performs the action itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Iterable, Literal

from catalog import infer_category, normalize_category

Decision = Literal["ALLOW", "BLOCK", "REQUIRE_APPROVAL"]

DECISIONS = ("ALLOW", "REQUIRE_APPROVAL", "BLOCK")
SAFE_DEFAULTS = ("BLOCK", "REQUIRE_APPROVAL")
_STRICTNESS = {"ALLOW": 0, "REQUIRE_APPROVAL": 1, "BLOCK": 2}


@dataclass(frozen=True)
class RuleView:
    id: int | None
    target_type: str  # "category" or "action"
    target_value: str
    resource_pattern: str
    effect: str


@dataclass(frozen=True)
class PolicyView:
    id: int | None
    name: str
    priority: int
    agent_pk: int | None  # None = applies to every agent in the workspace
    enabled: bool
    rules: tuple[RuleView, ...]


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    message: str  # short, plain-language sentence for the agent and the UI
    reason: str  # why this decision was made
    category: str
    policy_id: int | None = None
    policy_name: str | None = None
    rule_id: int | None = None
    used_default: bool = False


_MESSAGES = {
    "ALLOW": "Allowed by your security policy.",
    "BLOCK": "Blocked by your security policy.",
    "REQUIRE_APPROVAL": "A human must approve this action first.",
}


def _glob(pattern: str, value: str) -> bool:
    return fnmatchcase(value.lower(), pattern.strip().lower())


def rule_matches(rule: RuleView, action: str, resource: str,
                 inferred: str, declared: str | None) -> bool:
    if rule.target_type == "category":
        wanted = rule.target_value.strip().lower()
        target_ok = wanted == inferred or (declared is not None and wanted == declared)
    else:
        target_ok = _glob(rule.target_value, action)
    if not target_ok:
        return False
    return _glob(rule.resource_pattern or "*", resource or "")


def applicable_policies(policies: Iterable[PolicyView], agent_pk: int | None):
    for policy in policies:
        if not policy.enabled:
            continue
        if policy.agent_pk is None or policy.agent_pk == agent_pk:
            yield policy


def evaluate(
    action: str,
    resource: str,
    policies: Iterable[PolicyView],
    agent_pk: int | None = None,
    declared_category: str | None = None,
    default_decision: str = "BLOCK",
) -> Verdict:
    """Evaluate one requested action and return a Verdict."""
    if default_decision not in SAFE_DEFAULTS:
        default_decision = "BLOCK"  # never fail open

    action = (action or "").strip()
    resource = (resource or "").strip()
    inferred = infer_category(action)
    declared = normalize_category(declared_category)
    category = inferred if inferred != "other" or declared is None else declared

    best = None  # (sort_key, policy, rule)
    for policy in applicable_policies(policies, agent_pk):
        for rule in policy.rules:
            if rule.effect not in _STRICTNESS:
                continue  # ignore corrupt rules rather than guess
            if rule_matches(rule, action, resource, inferred, declared):
                key = (policy.priority, -_STRICTNESS[rule.effect],
                       policy.id if policy.id is not None else 0,
                       rule.id if rule.id is not None else 0)
                if best is None or key < best[0]:
                    best = (key, policy, rule)

    if best is None:
        decision = default_decision
        return Verdict(
            decision=decision,  # type: ignore[arg-type]
            message=_MESSAGES[decision],
            reason="No policy rule matched this action, so the workspace "
                   "default was applied. Unknown actions are never allowed.",
            category=category,
            used_default=True,
        )

    _, policy, rule = best
    target = (f"category '{rule.target_value}'" if rule.target_type == "category"
              else f"action pattern '{rule.target_value}'")
    scope = "" if (rule.resource_pattern or "*") == "*" else f" on resources like '{rule.resource_pattern}'"
    return Verdict(
        decision=rule.effect,  # type: ignore[arg-type]
        message=_MESSAGES[rule.effect],
        reason=f"Policy '{policy.name}' has a rule for {target}{scope} "
               f"that says {rule.effect.replace('_', ' ').lower()}.",
        category=category,
        policy_id=policy.id,
        policy_name=policy.name,
        rule_id=rule.id,
    )
