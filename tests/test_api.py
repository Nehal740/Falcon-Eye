"""End-to-end API tests (need FastAPI and SQLAlchemy installed).

They use an in-memory SQLite database (see conftest.py) and never touch real data.
Run:  python -m pytest
"""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")


def evaluate(client, agent, action, resource="", **extra):
    return client.post("/v1/evaluate", headers=agent["headers"],
                       json={"action": action, "resource": resource, **extra})


# ----------------------------------------------------------- accounts

def test_register_login_me_logout(client, make_user):
    user = make_user()
    assert user.user["email"] == "alice@example.com"
    r = client.post("/auth/login", json={"email": "ALICE@example.com", "password": "Sup3rSecret!"})
    assert r.status_code == 200 and r.json()["access_token"]
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/auth/me", headers=headers).status_code == 200
    assert client.post("/auth/logout", headers=headers).status_code == 200
    again = client.get("/auth/me", headers=headers)
    assert again.status_code == 401 and again.json()["error"]["code"] == "not_signed_in"


def test_weak_password_and_duplicate_email_are_rejected(client, make_user):
    weak = client.post("/auth/register", json={"full_name": "Eve Ex", "email": "e@example.com",
                                               "password": "short"})
    assert weak.status_code == 422 and weak.json()["error"]["fields"]
    letters_only = client.post("/auth/register", json={"full_name": "Eve Ex", "email": "e@example.com",
                                                       "password": "onlyletterspassword"})
    assert letters_only.status_code == 422
    make_user()
    dup = client.post("/auth/register", json={"full_name": "Alice Two", "email": "alice@example.com",
                                              "password": "Sup3rSecret!"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "email_taken"


def test_wrong_password_is_generic_and_account_locks(client, make_user):
    make_user()
    for _ in range(5):
        r = client.post("/auth/login", json={"email": "alice@example.com", "password": "wrong-password1"})
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    locked = client.post("/auth/login", json={"email": "alice@example.com", "password": "Sup3rSecret!"})
    assert locked.status_code == 429 and locked.json()["error"]["code"] == "account_locked"
    unknown = client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever123"})
    assert unknown.status_code == 401 and unknown.json()["error"]["code"] == "invalid_credentials"


def test_refresh_and_change_password(client, make_user):
    alice = make_user()
    fresh = client.post("/auth/refresh", headers=alice.headers)
    assert fresh.status_code == 200
    new_headers = {"Authorization": f"Bearer {fresh.json()['access_token']}"}
    assert client.get("/auth/me", headers=new_headers).status_code == 200
    wrong = alice.post("/auth/change-password", {"current_password": "nope", "new_password": "An0therSecret!"})
    assert wrong.status_code == 400 and wrong.json()["error"]["code"] == "wrong_password"
    ok = alice.post("/auth/change-password", {"current_password": "Sup3rSecret!", "new_password": "An0therSecret!"})
    assert ok.status_code == 200
    assert client.post("/auth/login", json={"email": "alice@example.com",
                                            "password": "An0therSecret!"}).status_code == 200


def test_endpoints_require_sign_in(client):
    for path in ("/auth/me", "/workspaces"):
        r = client.get(path)
        assert r.status_code == 401 and r.json()["error"]["code"] == "not_signed_in"


# ----------------------------------------------------------- tenant isolation

def test_other_workspaces_are_invisible(alice, bob):
    for suffix in ("", "/agents", "/policies", "/events", "/approvals", "/dashboard", "/members"):
        r = bob.get(alice.ws(suffix))
        assert r.status_code == 404, (suffix, r.status_code)
    assert bob.post(alice.ws("/agents"), {"name": "Intruder bot"}).status_code == 404


def test_agent_of_one_workspace_cannot_use_another_workspaces_approval(client, alice, bob, agent):
    sent = evaluate(client, agent, "send_external_email", "x@example.com")
    approval_id = sent.json()["approval_id"]
    assert bob.post(bob.ws(f"/approvals/{approval_id}/decision"),
                    {"decision": "APPROVED"}).status_code == 404
    assert client.get(f"/v1/approvals/{approval_id}", headers=agent["headers"]).json()["status"] == "PENDING"


# ----------------------------------------------------------- agents and the firewall

def test_agent_key_is_shown_once_and_never_again(alice, agent):
    listing = alice.get(alice.ws("/agents")).json()["items"][0]
    assert "api_key" not in listing and agent["key"] not in str(listing)
    assert listing["has_active_key"] and listing["key_prefix"].startswith("fe_live_")
    assert agent["key"] not in str(alice.get(alice.ws(f"/agents/{agent['id']}")).json())


def test_connection_test_goes_from_waiting_to_connected(client, alice, agent):
    first = alice.post(alice.ws(f"/agents/{agent['id']}/test-connection")).json()
    assert first["status"] == "failed" and first["connection_status"] == "waiting"
    ping = client.get("/v1/ping", headers=agent["headers"])
    assert ping.status_code == 200 and ping.json()["status"] == "connected"
    second = alice.post(alice.ws(f"/agents/{agent['id']}/test-connection")).json()
    assert second["status"] == "connected"


def test_three_decisions_and_default_deny(client, agent):
    assert evaluate(client, agent, "read_sample_document", "doc1").json()["decision"] == "ALLOW"
    assert evaluate(client, agent, "delete_file", "doc1").json()["decision"] == "BLOCK"
    pending = evaluate(client, agent, "send_external_email", "bob@example.org", reason="report").json()
    assert pending["decision"] == "REQUIRE_APPROVAL" and pending["approval_id"]
    unknown = evaluate(client, agent, "transfer_money", "acct").json()
    assert unknown["decision"] == "BLOCK"
    for body in (pending, unknown):
        assert body["executed"] is False and body["reason"]


def test_bad_or_missing_agent_keys_are_refused(client, alice, agent):
    bad = {"Authorization": "Bearer fe_live_" + "a" * 12 + "_" + "b" * 43}
    for headers in (bad, {}, alice.headers):
        r = client.post("/v1/evaluate", headers=headers, json={"action": "read_file"})
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_agent_key"
    assert client.get("/workspaces", headers=agent["headers"]).status_code == 401


def test_duplicate_request_id_is_safe(client, alice, agent):
    first = evaluate(client, agent, "send_external_email", "a@example.org", request_id="job-1").json()
    again = evaluate(client, agent, "send_external_email", "a@example.org", request_id="job-1").json()
    assert again["duplicate"] is True and again["event_id"] == first["event_id"]
    assert again["approval_id"] == first["approval_id"]
    clash = evaluate(client, agent, "delete_file", "x", request_id="job-1")
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "request_id_reused"
    events = alice.get(alice.ws("/events")).json()
    assert events["total"] == 1


def test_disabled_agent_is_blocked_and_revoked_key_stops_working(client, alice, agent):
    assert alice.patch(alice.ws(f"/agents/{agent['id']}"), {"status": "disabled"}).status_code == 200
    blocked = evaluate(client, agent, "read_sample_document").json()
    assert blocked["decision"] == "BLOCK" and "switched off" in blocked["reason"]
    alice.patch(alice.ws(f"/agents/{agent['id']}"), {"status": "active"})
    assert evaluate(client, agent, "read_sample_document").json()["decision"] == "ALLOW"
    assert alice.post(alice.ws(f"/agents/{agent['id']}/credentials/revoke")).status_code == 200
    assert evaluate(client, agent, "read_sample_document").status_code == 401


def test_rotating_a_key_invalidates_the_old_one(client, alice, agent):
    rotated = alice.post(alice.ws(f"/agents/{agent['id']}/credentials/rotate")).json()
    assert rotated["api_key"] != agent["key"]
    assert evaluate(client, agent, "read_sample_document").status_code == 401
    new = {"headers": {"Authorization": f"Bearer {rotated['api_key']}"}}
    assert evaluate(client, new, "read_sample_document").json()["decision"] == "ALLOW"


def test_validation_errors_are_friendly(client, agent):
    r = client.post("/v1/evaluate", headers=agent["headers"], json={"action": "bad action!"})
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "validation_error" and body["hint"] and "Traceback" not in str(body)


# ----------------------------------------------------------- approvals

def test_approval_is_decided_once_and_visible_to_the_agent(client, alice, agent):
    sent = evaluate(client, agent, "send_external_email", "c@example.org").json()
    approval_id = sent["approval_id"]
    pending = alice.get(alice.ws("/approvals")).json()
    assert pending["total"] == 1 and pending["items"][0]["approval_id"] == approval_id
    ok = alice.post(alice.ws(f"/approvals/{approval_id}/decision"),
                    {"decision": "APPROVED", "comment": "looks fine"})
    assert ok.status_code == 200 and ok.json()["approval"]["status"] == "APPROVED"
    second = alice.post(alice.ws(f"/approvals/{approval_id}/decision"), {"decision": "REJECTED"})
    assert second.status_code == 409 and second.json()["error"]["code"] == "already_decided"
    status = client.get(f"/v1/approvals/{approval_id}", headers=agent["headers"]).json()
    assert status["status"] == "APPROVED" and status["executed"] is False
    history = alice.get(alice.ws("/approvals?status=ALL")).json()["items"][0]
    assert history["decided_by"] == "Alice Example" and history["decision_comment"] == "looks fine"


def test_viewers_cannot_decide_but_members_can(client, make_user, alice, bob, agent):
    assert alice.post(alice.ws("/members"), {"email": "bob@example.com", "role": "viewer"}).status_code == 201
    approval_id = evaluate(client, agent, "send_external_email", "d@example.org").json()["approval_id"]
    denied = bob.post(alice.ws(f"/approvals/{approval_id}/decision"), {"decision": "APPROVED"})
    assert denied.status_code == 403
    assert bob.get(alice.ws("/dashboard")).status_code == 200  # read access works
    assert bob.post(alice.ws("/agents"), {"name": "Viewer bot"}).status_code == 403
    assert alice.patch(alice.ws("/members/%d" % bob.user["id"]), {"role": "member"}).status_code == 200
    assert bob.post(alice.ws(f"/approvals/{approval_id}/decision"),
                    {"decision": "REJECTED"}).status_code == 200


# ----------------------------------------------------------- policies

def test_policy_crud_history_and_simulation(client, alice, agent):
    body = {"name": "Allow reports", "priority": 5, "rules": [
        {"target_type": "action", "target_value": "export_report", "resource_pattern": "*", "effect": "ALLOW"}]}
    created = alice.post(alice.ws("/policies"), body)
    assert created.status_code == 201
    policy = created.json()
    assert policy["version"] == 1 and policy["scope"] == "workspace"

    sim = alice.post(alice.ws("/policies/simulate"), {"action": "export_report", "agent_id": agent["id"]}).json()
    assert sim["decision"] == "ALLOW" and sim["policy_name"] == "Allow reports" and sim["recorded"] is False
    assert alice.get(alice.ws("/events")).json()["total"] == 0  # simulation records nothing

    assert alice.patch(alice.ws(f"/policies/{policy['id']}"), {"enabled": False}).status_code == 200
    sim = alice.post(alice.ws("/policies/simulate"), {"action": "export_report", "agent_id": agent["id"]}).json()
    assert sim["decision"] == "REQUIRE_APPROVAL"  # falls back to the starter policy (data_export)

    history = alice.get(alice.ws(f"/policies/{policy['id']}/history")).json()["items"]
    assert [h["change_type"] for h in history] == ["disabled", "created"]
    assert alice.delete(alice.ws(f"/policies/{policy['id']}")).status_code == 200


def test_policy_rules_are_validated(alice):
    bad = {"name": "Bad", "rules": [{"target_type": "category", "target_value": "nonsense",
                                     "resource_pattern": "*", "effect": "ALLOW"}]}
    assert alice.post(alice.ws("/policies"), bad).status_code == 422
    worse = {"name": "Bad", "rules": [{"target_type": "action", "target_value": "a; DROP TABLE users",
                                       "resource_pattern": "*", "effect": "ALLOW"}]}
    assert alice.post(alice.ws("/policies"), worse).status_code == 422


def test_catalog_endpoints_for_the_policy_builder(alice):
    cats = alice.get("/action-categories").json()["items"]
    assert any(c["key"] == "external_email" for c in cats)
    templates = alice.get("/policy-templates").json()["items"]
    assert templates and all(t["key"] and t["rules"] for t in templates)


# ----------------------------------------------------------- monitoring

def test_events_filters_and_dashboard_use_real_numbers(client, alice, agent):
    evaluate(client, agent, "read_sample_document", "a")
    evaluate(client, agent, "delete_file", "b")
    evaluate(client, agent, "send_external_email", "c@example.org")
    events = alice.get(alice.ws("/events")).json()
    assert events["total"] == 3
    only_blocked = alice.get(alice.ws("/events?decision=BLOCK")).json()
    assert only_blocked["total"] == 1 and only_blocked["items"][0]["action"] == "delete_file"
    assert alice.get(alice.ws("/events?q=email")).json()["total"] == 1
    assert alice.get(alice.ws(f"/events?agent_id={agent['public_id']}")).json()["total"] == 3
    one = alice.get(alice.ws(f"/events/{events['items'][0]['event_id']}")).json()
    assert "decision_reason" in one

    dash = alice.get(alice.ws("/dashboard")).json()
    assert dash["totals"]["events"] == 3 and dash["totals"]["allowed"] == 1
    assert dash["totals"]["blocked"] == 1 and dash["totals"]["pending_approvals"] == 1
    assert len(dash["daily"]) == 7 and dash["recent_events"] and dash["pending_approvals"]
    assert dash["top_agents"][0]["events"] == 3
    agent_row = alice.get(alice.ws("/agents")).json()["items"][0]
    assert agent_row["stats"]["total"] == 3 and agent_row["stats"]["pending"] == 1


def test_assistant_falls_back_to_documentation_without_an_ai_key(alice):
    status = alice.get(alice.ws("/assistant/status")).json()
    assert status["live_ai_configured"] is False
    answer = alice.post(alice.ws("/assistant/chat"), {"message": "How do I connect my first agent?"})
    assert answer.status_code == 200
    body = answer.json()
    assert body["mode"] == "docs" and body["answer"] and body["notice"]


def test_audit_log_records_changes_without_secrets(client, alice, agent):
    log = alice.get(alice.ws("/audit-logs")).json()
    actions = {item["action"] for item in log["items"]}
    assert "agent.created" in actions or any(a.startswith("agent.") for a in actions)
    assert agent["key"] not in str(log)


def test_health_endpoints(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/health/ready").json()["database"] == "ok"
