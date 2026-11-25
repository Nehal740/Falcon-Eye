from policy import evaluate_policy


def test_allowed_action():
    assert evaluate_policy(
        "demo-agent", "read_sample_document"
    ) == "ALLOW"


def test_blocked_action():
    assert evaluate_policy(
        "demo-agent", "delete_file"
    ) == "BLOCK"


def test_approval_required():
    assert evaluate_policy(
        "demo-agent", "send_external_email"
    ) == "REQUIRE_APPROVAL"


def test_unknown_action():
    assert evaluate_policy(
        "demo-agent", "transfer_money"
    ) == "BLOCK"


def test_unknown_agent():
    assert evaluate_policy(
        "unknown-agent", "read_sample_document"
    ) == "BLOCK"