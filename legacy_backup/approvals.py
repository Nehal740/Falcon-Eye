
from datetime import datetime, timezone
from uuid import uuid4

pending_approvals = []


def create_approval_request(agent_id, action, resource, reason):
    approval = {
        "approval_id": str(uuid4()),
        "agent_id": agent_id,
        "action": action,
        "resource": resource,
        "reason": reason,
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    pending_approvals.append(approval)

    return approval


def get_pending_approvals():
    return [
        approval for approval in pending_approvals
        if approval["status"] == "PENDING"
    ]


def get_all_approvals():
    return pending_approvals


def decide_approval(approval_id, decision):
    for approval in pending_approvals:
        if approval["approval_id"] == approval_id:

            if approval["status"] != "PENDING":
                return None

            approval["status"] = decision
            return approval

    return None
