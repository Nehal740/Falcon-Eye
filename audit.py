"""Audit logging. Never pass secrets (passwords, API keys) in ``details``."""

import json

from sqlalchemy.orm import Session

from models import AuditLog


def record(
    db: Session,
    action: str,
    *,
    workspace_id: int | None = None,
    actor_type: str = "system",
    actor_id: str | int | None = None,
    actor_label: str | None = None,
    target_type: str | None = None,
    target_id: str | int | None = None,
    details: dict | None = None,
    ip: str | None = None,
) -> AuditLog:
    """Add an audit row to the current transaction (the caller commits)."""
    entry = AuditLog(
        workspace_id=workspace_id,
        actor_type=actor_type,
        actor_id=str(actor_id) if actor_id is not None else None,
        actor_label=(actor_label or "")[:120] or None,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=json.dumps(details, default=str)[:4000] if details else None,
        ip_address=ip,
    )
    db.add(entry)
    return entry
