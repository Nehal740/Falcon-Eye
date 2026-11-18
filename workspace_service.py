"""Shared helpers for creating workspaces and checking roles."""

from sqlalchemy.orm import Session

from models import AssistantConfig, User, Workspace, WorkspaceMember

ROLE_RANK = {"viewer": 1, "member": 2, "admin": 3, "owner": 4}
ASSIGNABLE_ROLES = ("admin", "member", "viewer")

ROLE_HELP = {
    "owner": "Full control, including members and settings.",
    "admin": "Manage agents, policies and members; decide approvals.",
    "member": "View everything and decide approvals.",
    "viewer": "View-only access.",
}


def create_workspace(db: Session, owner: User, name: str) -> Workspace:
    """Create a workspace with the owner as its first member. Does not commit."""
    workspace = Workspace(name=name.strip(), owner_id=owner.id, default_decision="BLOCK")
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=owner.id, role="owner"))
    db.add(AssistantConfig(workspace_id=workspace.id, enabled=True))
    db.flush()
    return workspace


def personal_workspace_name(full_name: str) -> str:
    first = (full_name or "My").strip().split(" ")[0] or "My"
    return f"{first}'s workspace"[:100]


def workspace_out(workspace: Workspace, role: str | None = None) -> dict:
    data = {
        "id": workspace.id,
        "name": workspace.name,
        "default_decision": workspace.default_decision,
    }
    if role:
        data["role"] = role
    return data
