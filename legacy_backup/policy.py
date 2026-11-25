
from typing import Literal

Decision = Literal["ALLOW", "BLOCK", "REQUIRE_APPROVAL"]

# Our demo AI agent
AGENT_ID = "demo-agent"

# Actions the AI agent is allowed to perform
ALLOW_ACTIONS = {
    "read_sample_document",
    "search_sample_records",
    "draft_email",
}

# Actions that are completely blocked
BLOCK_ACTIONS = {
    "delete_file",
    "access_financial_records",
}

# Actions that need human approval
APPROVAL_ACTIONS = {
    "send_external_email",
}

# Main firewall decision function
def evaluate_policy(agent_id: str, action: str) -> Decision:

    if agent_id != AGENT_ID:
        return "BLOCK"

    if action in BLOCK_ACTIONS:
        return "BLOCK"

    if action in APPROVAL_ACTIONS:
        return "REQUIRE_APPROVAL"

    if action in ALLOW_ACTIONS:
        return "ALLOW"

    # Block anything we don't recognize
    return "BLOCK"
