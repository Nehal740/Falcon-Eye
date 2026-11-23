"""Email flows through the real API: welcome + confirm, forgot/reset password.

Needs FastAPI and SQLAlchemy. Outgoing mail is captured, nothing is sent.
"""

import re
import time
from datetime import timedelta

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

import email_service  # noqa: E402
from config import settings  # noqa: E402


@pytest.fixture()
def outbox(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "email_from", "Falcon Eye <no-reply@example.test>")
    sent = []
    monkeypatch.setattr(email_service, "send_email", lambda to, rendered: sent.append((to, rendered)) or True)
    return sent


def token_from(rendered) -> str:
    return re.search(r"token=([A-Za-z0-9_-]+)", rendered.text).group(1)


NEW_PASSWORD = "Brand-new-pass-77"


def test_register_sends_a_welcome_email_with_a_working_confirm_link(client, outbox, make_user):
    alice = make_user()
    assert len(outbox) == 1
    to, mail = outbox[0]
    assert to == "alice@example.com" and "Welcome to Falcon Eye" in mail.subject
    assert alice.get("/auth/me").json()["user"]["email_verified"] is False

    token = token_from(mail)
    ok = client.post("/auth/verify-email", json={"token": token})
    assert ok.status_code == 200
    assert alice.get("/auth/me").json()["user"]["email_verified"] is True
    again = client.post("/auth/verify-email", json={"token": token})
    assert again.status_code == 400 and again.json()["error"]["code"] == "invalid_or_expired_token"


def test_register_still_works_when_email_is_not_configured(client, make_user):
    alice = make_user()  # no outbox fixture: SMTP is not configured
    assert alice.get("/auth/me").status_code == 200


def test_forgot_password_does_not_reveal_whether_an_account_exists(client, outbox, make_user):
    make_user()
    outbox.clear()
    known = client.post("/auth/forgot-password", json={"email": "alice@example.com"})
    unknown = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert [to for to, _ in outbox] == ["alice@example.com"]


def test_full_password_reset_flow(client, outbox, make_user):
    alice = make_user()
    outbox.clear()
    client.post("/auth/forgot-password", json={"email": "alice@example.com"})
    token = token_from(outbox[0][1])
    outbox.clear()
    time.sleep(1.1)  # session checks work in whole seconds (see docs/EMAIL.md)

    reset = client.post("/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
    assert reset.status_code == 200
    assert "password was changed" in outbox[0][1].subject.lower()  # security notice

    old = client.post("/auth/login", json={"email": "alice@example.com", "password": "Sup3rSecret!"})
    assert old.status_code == 401
    new = client.post("/auth/login", json={"email": "alice@example.com", "password": NEW_PASSWORD})
    assert new.status_code == 200
    # the session that existed before the reset no longer works
    assert alice.get("/auth/me").status_code == 401
    # the link works only once
    reused = client.post("/auth/reset-password", json={"token": token, "new_password": "Another-pass-88"})
    assert reused.status_code == 400
    # a successful reset also proves the inbox belongs to the user
    headers = {"Authorization": f"Bearer {new.json()['access_token']}"}
    assert client.get("/auth/me", headers=headers).json()["user"]["email_verified"] is True


def test_weak_new_password_is_rejected_and_the_link_stays_usable(client, outbox, make_user):
    make_user()
    outbox.clear()
    client.post("/auth/forgot-password", json={"email": "alice@example.com"})
    token = token_from(outbox[0][1])
    weak = client.post("/auth/reset-password", json={"token": token, "new_password": "short"})
    assert weak.status_code == 422
    ok = client.post("/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
    assert ok.status_code == 200


def test_unknown_and_expired_links_are_rejected(client, outbox, make_user):
    make_user()
    bad = client.post("/auth/reset-password", json={"token": "x" * 40, "new_password": NEW_PASSWORD})
    assert bad.status_code == 400

    outbox.clear()
    client.post("/auth/forgot-password", json={"email": "alice@example.com"})
    token = token_from(outbox[0][1])
    from database import SessionLocal
    from models import EmailToken, utcnow
    db = SessionLocal()
    try:
        db.query(EmailToken).update({EmailToken.expires_at: utcnow() - timedelta(minutes=1)})
        db.commit()
    finally:
        db.close()
    late = client.post("/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
    assert late.status_code == 400


def test_a_new_reset_request_cancels_the_older_link(client, outbox, make_user):
    make_user()
    outbox.clear()
    client.post("/auth/forgot-password", json={"email": "alice@example.com"})
    first = token_from(outbox[0][1])
    client.post("/auth/forgot-password", json={"email": "alice@example.com"})
    second = token_from(outbox[1][1])
    assert client.post("/auth/reset-password", json={"token": first, "new_password": NEW_PASSWORD}).status_code == 400
    assert client.post("/auth/reset-password", json={"token": second, "new_password": NEW_PASSWORD}).status_code == 200


def test_reset_clears_an_account_lockout(client, outbox, make_user):
    make_user()
    for _ in range(5):
        client.post("/auth/login", json={"email": "alice@example.com", "password": "wrong-password-1"})
    locked = client.post("/auth/login", json={"email": "alice@example.com", "password": "Sup3rSecret!"})
    assert locked.status_code == 429
    outbox.clear()
    client.post("/auth/forgot-password", json={"email": "alice@example.com"})
    client.post("/auth/reset-password", json={"token": token_from(outbox[0][1]), "new_password": NEW_PASSWORD})
    assert client.post("/auth/login", json={"email": "alice@example.com", "password": NEW_PASSWORD}).status_code == 200


def test_at_most_three_reset_emails_per_address_per_hour(client, outbox, make_user):
    make_user()
    outbox.clear()
    for _ in range(5):
        r = client.post("/auth/forgot-password", json={"email": "alice@example.com"})
        assert r.status_code == 200
    assert len(outbox) == 3


def test_forgot_password_says_so_when_email_is_not_configured(client, make_user):
    make_user()
    r = client.post("/auth/forgot-password", json={"email": "alice@example.com"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "email_not_configured"


def test_changing_the_password_sends_a_security_notice(client, outbox, make_user):
    alice = make_user()
    outbox.clear()
    r = alice.post("/auth/change-password", {"current_password": "Sup3rSecret!", "new_password": NEW_PASSWORD})
    assert r.status_code == 200
    assert [to for to, _ in outbox] == ["alice@example.com"]
    assert "changed" in outbox[0][1].subject.lower()


def test_resend_verification(client, outbox, make_user):
    alice = make_user()
    outbox.clear()
    r = alice.post("/auth/resend-verification")
    assert r.status_code == 200 and len(outbox) == 1
    assert client.post("/auth/verify-email", json={"token": token_from(outbox[0][1])}).status_code == 200
    outbox.clear()
    done = alice.post("/auth/resend-verification")
    assert done.json()["email_verified"] is True and outbox == []
