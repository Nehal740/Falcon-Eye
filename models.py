"""Database models.

``User``, ``FirewallEvent`` and ``ApprovalRequest`` already existed in the
first version of the project. Their original columns are unchanged; new
columns are nullable or have defaults so existing rows keep working (see
``migrations.py``).
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import expression

from database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat them as UTC."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def iso(value: datetime | None) -> str | None:
    value = aware(value)
    return value.isoformat() if value else None


# --------------------------------------------------------------------------
# Users, workspaces, membership
# --------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    # Added in v2 (all defaulted so old rows stay valid)
    is_active = Column(Boolean, nullable=False, default=True,
                       server_default=expression.true())
    failed_login_count = Column(Integer, nullable=False, default=0,
                                server_default=text("0"))
    locked_until = Column(DateTime(timezone=True))
    last_login_at = Column(DateTime(timezone=True))
    token_valid_after = Column(DateTime(timezone=True))
    onboarding_completed = Column(Boolean, nullable=False, default=False,
                                  server_default=expression.false())
    email_verified_at = Column(DateTime(timezone=True))


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # What happens when no rule matches. Never ALLOW (secure default).
    default_decision = Column(String(20), nullable=False, default="BLOCK",
                              server_default="BLOCK")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id",
                                       name="uq_member_workspace_user"),)

    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False, default="member")  # owner/admin/member/viewer
    created_at = Column(DateTime(timezone=True), default=utcnow)


class EmailToken(Base):
    """One-time links sent by email (confirm address, reset password).

    Only a SHA-256 hash of the token is stored, so a database leak cannot be
    used to take over accounts. A token works once and expires."""
    __tablename__ = "email_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    purpose = Column(String(30), nullable=False)  # verify_email | reset_password
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow)


class RevokedToken(Base):
    """Login tokens that were signed out before they expired."""
    __tablename__ = "revoked_tokens"

    jti = Column(String(64), primary_key=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)


# --------------------------------------------------------------------------
# Agents and credentials
# --------------------------------------------------------------------------

class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_agent_workspace_name"),)

    id = Column(Integer, primary_key=True)
    public_id = Column(String(40), unique=True, nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    description = Column(String(300), default="")
    connection_type = Column(String(30), nullable=False, default="http_api")
    status = Column(String(20), nullable=False, default="active")  # active / disabled
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_seen_at = Column(DateTime(timezone=True))

    credentials = relationship("AgentCredential", back_populates="agent",
                               cascade="all, delete-orphan")


class AgentCredential(Base):
    __tablename__ = "agent_credentials"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    key_prefix = Column(String(32), unique=True, nullable=False, index=True)
    key_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    last_used_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))

    agent = relationship("Agent", back_populates="credentials")


# --------------------------------------------------------------------------
# Policies
# --------------------------------------------------------------------------

class Policy(Base):
    __tablename__ = "policies"

    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), index=True)  # NULL = all agents
    name = Column(String(100), nullable=False)
    description = Column(String(300), default="")
    enabled = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=100)  # 1 = checked first
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    rules = relationship("PolicyRule", back_populates="policy",
                         cascade="all, delete-orphan", order_by="PolicyRule.position")
    versions = relationship("PolicyVersion", back_populates="policy",
                            cascade="all, delete-orphan", order_by="PolicyVersion.version")


class PolicyRule(Base):
    __tablename__ = "policy_rules"

    id = Column(Integer, primary_key=True)
    policy_id = Column(Integer, ForeignKey("policies.id"), nullable=False, index=True)
    target_type = Column(String(20), nullable=False)  # category / action
    target_value = Column(String(100), nullable=False)
    resource_pattern = Column(String(200), nullable=False, default="*")
    effect = Column(String(20), nullable=False)  # ALLOW / BLOCK / REQUIRE_APPROVAL
    position = Column(Integer, nullable=False, default=0)

    policy = relationship("Policy", back_populates="rules")


class PolicyVersion(Base):
    """One row per change, so users can see who changed a policy and when."""
    __tablename__ = "policy_versions"

    id = Column(Integer, primary_key=True)
    policy_id = Column(Integer, ForeignKey("policies.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    change_type = Column(String(30), nullable=False)  # created / updated / enabled / disabled
    snapshot = Column(Text, nullable=False)  # JSON of the policy at that time
    changed_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=utcnow)

    policy = relationship("Policy", back_populates="versions")


# --------------------------------------------------------------------------
# Firewall events and approvals
# --------------------------------------------------------------------------

class FirewallEvent(Base):
    __tablename__ = "firewall_events"
    __table_args__ = (
        Index("ix_events_workspace_created", "workspace_id", "created_at"),
        Index("ix_events_agent_pk", "agent_pk"),
        Index("uq_events_agent_request", "agent_pk", "request_id", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, unique=True, index=True)
    agent_id = Column(String, nullable=False)  # the agent's public id (or legacy name)
    action = Column(String, nullable=False)
    resource = Column(String)
    decision = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    # Added in v2
    workspace_id = Column(Integer, ForeignKey("workspaces.id"))
    agent_pk = Column(Integer)  # numeric agent id; kept after the agent is deleted
    agent_name = Column(String(80))
    category = Column(String(40))
    reason = Column(String(500))  # the agent's stated reason
    decision_reason = Column(String(500))  # why the firewall decided this way
    policy_id = Column(Integer)
    policy_name = Column(String(100))
    request_id = Column(String(64))
    approval_id = Column(String(64))
    details = Column(Text)  # JSON metadata sent by the agent (max 4 KB)
    source_ip = Column(String(64))


class Verification(Base):
    """One output check made through /v1/verify. Stores signal NAMES and counts only,
    never the checked text itself (only its SHA-256 hash and length)."""
    __tablename__ = "verifications"
    __table_args__ = (Index("ix_verifications_workspace_created", "workspace_id", "created_at"),)

    id = Column(Integer, primary_key=True, index=True)
    verification_id = Column(String, unique=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    agent_pk = Column(Integer)
    agent_id = Column(String(64))
    agent_name = Column(String(80))
    kind = Column(String(20))
    status = Column(String(30))
    risk_level = Column(String(10), index=True)
    decision = Column(String(20))
    flagged = Column(Boolean, default=False)
    signal_codes = Column(Text)        # JSON list of signal names
    counts = Column(Text)              # JSON: claims checked / unsupported / contradicted
    text_sha256 = Column(String(64))
    text_length = Column(Integer)
    event_id = Column(String)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (Index("ix_approvals_workspace_status", "workspace_id", "status"),)

    id = Column(Integer, primary_key=True, index=True)
    approval_id = Column(String, unique=True, index=True)
    agent_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    resource = Column(String)
    reason = Column(String)
    status = Column(String, default="PENDING")  # PENDING/APPROVED/REJECTED/EXPIRED
    created_at = Column(DateTime(timezone=True), default=utcnow)
    # Added in v2
    workspace_id = Column(Integer, ForeignKey("workspaces.id"))
    agent_pk = Column(Integer)
    agent_name = Column(String(80))
    event_id = Column(String(64))
    category = Column(String(40))
    details = Column(Text)
    expires_at = Column(DateTime(timezone=True))
    decided_at = Column(DateTime(timezone=True))
    decided_by = Column(Integer, ForeignKey("users.id"))


class ApprovalDecision(Base):
    """The permanent record of who decided an approval. One per approval."""
    __tablename__ = "approval_decisions"

    id = Column(Integer, primary_key=True)
    approval_pk = Column(Integer, ForeignKey("approval_requests.id"),
                         nullable=False, unique=True)
    decided_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    decision = Column(String(20), nullable=False)  # APPROVED / REJECTED
    comment = Column(String(300))
    decided_at = Column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------
# Audit log and assistant configuration
# --------------------------------------------------------------------------

class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_workspace_created", "workspace_id", "created_at"),)

    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"))
    actor_type = Column(String(20), nullable=False)  # user / agent / system
    actor_id = Column(String(64))
    actor_label = Column(String(120))
    action = Column(String(60), nullable=False)
    target_type = Column(String(40))
    target_id = Column(String(64))
    details = Column(Text)
    ip_address = Column(String(64))
    created_at = Column(DateTime(timezone=True), default=utcnow)


class AssistantConfig(Base):
    __tablename__ = "assistant_config"

    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), unique=True, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    custom_instructions = Column(String(500), default="")
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    version = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    applied_at = Column(DateTime(timezone=True), default=utcnow)
