"""Shared request dependencies: who is calling, and what may they touch?"""

from dataclasses import dataclass
from typing import NoReturn

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from agent_keys import parse_agent_key, verify_agent_key
import audit
from config import settings
from database import get_db
from errors import AppError
from models import (
    Agent, AgentCredential, RevokedToken, User, Workspace, WorkspaceMember,
    aware, utcnow,
)
from rate_limiter import limiter
from security import decode_access_token
from workspace_service import ROLE_RANK

user_bearer = HTTPBearer(auto_error=False, scheme_name="UserToken",
                         description="Login token from POST /auth/login")
agent_bearer = HTTPBearer(auto_error=False, scheme_name="AgentKey",
                          description="Agent key shown once when the agent is created")

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def client_ip(request: Request) -> str | None:
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


def _not_signed_in(message: str | None = None) -> AppError:
    return AppError(401, "not_signed_in",
                    message or "You are not signed in, or your session has expired.",
                    "Please sign in again.")


# --------------------------------------------------------------------------
# People (browser sessions and API users)
# --------------------------------------------------------------------------

def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(user_bearer),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials else None
    from_cookie = False
    if not token:
        token = request.cookies.get(settings.cookie_name)
        from_cookie = True
    if not token:
        raise _not_signed_in()

    # Browsers attach cookies automatically, so state-changing requests made
    # with a cookie must carry a header that other websites cannot add.
    if from_cookie and request.method not in SAFE_METHODS:
        if request.headers.get("x-requested-with") != "FalconEye":
            raise AppError(403, "csrf_check_failed",
                           "This request was blocked as a safety precaution.",
                           "Reload the page and try again.")

    claims = decode_access_token(token)
    if claims is None:
        raise _not_signed_in()

    if db.query(RevokedToken).filter(RevokedToken.jti == claims["jti"]).first():
        raise _not_signed_in("You have been signed out.")

    try:
        user_id = int(claims["sub"])
    except (TypeError, ValueError):
        raise _not_signed_in() from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _not_signed_in()

    valid_after = aware(user.token_valid_after)
    if valid_after and int(claims["iat"]) < int(valid_after.timestamp()):
        raise _not_signed_in("Your password was changed. Please sign in again.")

    request.state.token_claims = claims
    return user


@dataclass
class WorkspaceContext:
    workspace: Workspace
    membership: WorkspaceMember
    user: User

    @property
    def role(self) -> str:
        return self.membership.role


def require_role(min_role: str = "viewer"):
    """Dependency factory: the caller must belong to the workspace in the URL
    with at least ``min_role``. Non-members get a 404 so workspace ids cannot
    be probed."""

    def dependency(
        workspace_id: int,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> WorkspaceContext:
        membership = (db.query(WorkspaceMember)
                      .filter(WorkspaceMember.workspace_id == workspace_id,
                              WorkspaceMember.user_id == user.id).first())
        workspace = db.get(Workspace, workspace_id) if membership else None
        if membership is None or workspace is None:
            raise AppError(404, "workspace_not_found",
                           "We could not find that workspace.",
                           "Check that you are signed in to the right account.")
        if ROLE_RANK.get(membership.role, 0) < ROLE_RANK[min_role]:
            raise AppError(
                403, "not_allowed",
                "Your role in this workspace does not allow that.",
                f"Ask a workspace owner to give you the '{min_role}' role or higher.")
        return WorkspaceContext(workspace, membership, user)

    return dependency


# --------------------------------------------------------------------------
# AI agents (API keys)
# --------------------------------------------------------------------------

@dataclass
class AgentContext:
    agent: Agent
    credential: AgentCredential
    workspace: Workspace


def authenticate_agent(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(agent_bearer),
    db: Session = Depends(get_db),
) -> AgentContext:
    ip = client_ip(request)

    # Slow down anyone guessing keys.
    allowed, retry = limiter.hit(f"agent-auth-fail-check:{ip}", 600, 60)
    if not allowed:
        raise AppError(429, "rate_limited", "Too many requests from this address.",
                       f"Wait {retry} seconds and try again.",
                       headers={"Retry-After": str(retry)})

    raw = credentials.credentials if credentials else request.headers.get("x-falcon-key")
    prefix = parse_agent_key(raw)
    invalid = AppError(
        401, "invalid_agent_key",
        "This agent key is missing, invalid or has been revoked.",
        "Send the key as 'Authorization: Bearer <key>'. If it was lost or "
        "revoked, create a new one in Falcon Eye under Agents.")

    def fail(workspace_id: int | None = None, reason: str = "invalid_key") -> NoReturn:
        bad, retry_after = limiter.hit(f"agent-auth-fail:{ip}", 10, 60)
        audit.record(db, "agent.auth_failed", workspace_id=workspace_id,
                     actor_type="agent", actor_label=prefix or "unknown", ip=ip,
                     details={"reason": reason})
        db.commit()
        if not bad:
            raise AppError(429, "rate_limited",
                           "Too many failed attempts with an invalid agent key.",
                           f"Wait {retry_after} seconds and check the key.",
                           headers={"Retry-After": str(retry_after)})
        raise invalid

    if prefix is None or raw is None:
        fail(reason="malformed_key")

    credential = (db.query(AgentCredential)
                  .filter(AgentCredential.key_prefix == prefix).first())
    if credential is None:
        fail(reason="unknown_key")
    if not verify_agent_key(raw, credential.key_hash):
        agent = db.get(Agent, credential.agent_id)
        fail(agent.workspace_id if agent else None, "wrong_secret")
    agent = db.get(Agent, credential.agent_id)
    if credential.revoked_at is not None:
        fail(agent.workspace_id if agent else None, "revoked_key")
    if agent is None:
        fail(reason="agent_missing")

    workspace = db.get(Workspace, agent.workspace_id)
    now = utcnow()
    credential.last_used_at = now
    agent.last_seen_at = now
    return AgentContext(agent=agent, credential=credential, workspace=workspace)
