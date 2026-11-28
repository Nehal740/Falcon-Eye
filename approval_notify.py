"""Email people who can review approvals when an agent is waiting.

* Only active members with the member, admin or owner role, who have not
  turned the emails off, are told.
* At most one email per person per workspace every 15 minutes, so a busy
  agent cannot flood anyone's inbox. (The counter lives in memory.)
* Sent in the background after the response; a mail failure changes nothing.
"""

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

import email_service
from config import settings
from models import User, Workspace, WorkspaceMember
from rate_limiter import limiter

REVIEW_ROLES = ("member", "admin", "owner")
QUIET_SECONDS = 15 * 60


def notify_approvers(db: Session, background: BackgroundTasks, workspace: Workspace, *,
                     agent_name: str, action: str, resource: str | None,
                     reason: str | None) -> int:
    """Queue the emails. Returns how many were queued."""
    if not settings.email_available:
        return 0
    people = (db.query(User)
              .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
              .filter(WorkspaceMember.workspace_id == workspace.id,
                      WorkspaceMember.role.in_(REVIEW_ROLES),
                      User.is_active.is_(True), User.notify_approvals.is_(True)).all())
    queued = 0
    for person in people:
        allowed, _retry = limiter.hit(f"approval-mail:{workspace.id}:{person.id}", 1, QUIET_SECONDS)
        if not allowed:
            continue
        mail = email_service.approval_waiting(person.full_name, workspace.name, agent_name,
                                              action, resource or "", reason or "")
        background.add_task(email_service.send_email, person.email, mail)
        queued += 1
    return queued
