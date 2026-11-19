"""Email templates, message building and SMTP sending (no network, no database)."""

import smtplib

import pytest

import email_service
from config import settings


@pytest.fixture(autouse=True)
def smtp_settings(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "mailer")
    monkeypatch.setattr(settings, "smtp_password", "pw")
    monkeypatch.setattr(settings, "smtp_security", "starttls")
    monkeypatch.setattr(settings, "email_from", "Falcon Eye <no-reply@example.test>")
    monkeypatch.setattr(settings, "email_reply_to", None)
    monkeypatch.setattr(settings, "app_base_url", "https://falcon.example.test")
    monkeypatch.setattr(settings, "email_log_links", False)


class FakeSMTP:
    instances = []
    fail_login = False

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls = []
        self.sent = None
        FakeSMTP.instances.append(self)

    def ehlo(self): self.calls.append("ehlo")

    def starttls(self, context=None): self.calls.append("starttls")

    def login(self, user, password):
        if FakeSMTP.fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")
        self.calls.append(("login", user, password))

    def send_message(self, message): self.sent = message

    def quit(self): self.calls.append("quit")


@pytest.fixture()
def fake_smtp(monkeypatch):
    FakeSMTP.instances = []
    FakeSMTP.fail_login = False
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


# ---- templates

def test_links_keep_the_token_after_the_hash():
    assert email_service.reset_link("abc") == "https://falcon.example.test/#/reset-password?token=abc"
    assert email_service.verify_link("abc") == "https://falcon.example.test/#/verify-email?token=abc"


def test_welcome_email_contains_the_confirm_link_in_text_and_html():
    mail = email_service.welcome_and_verify("Alice Example", "TOKEN123")
    assert "Welcome to Falcon Eye" in mail.subject
    link = "https://falcon.example.test/#/verify-email?token=TOKEN123"
    assert link in mail.text and link in mail.html
    assert "Alice" in mail.text


def test_reset_email_mentions_expiry_and_link():
    mail = email_service.password_reset("Alice Example", "RESETTOK")
    assert "reset-password?token=RESETTOK" in mail.text
    assert f"{settings.reset_token_minutes} minutes" in mail.text


def test_user_supplied_name_is_escaped_in_html():
    mail = email_service.verify_again('<script>alert(1)</script> Bob', "T0K3N")
    assert "<script>" not in mail.html


def test_password_changed_notice_has_no_link_to_act_on_blindly():
    mail = email_service.password_changed("Alice Example")
    assert "token=" not in mail.text and "token=" not in mail.html


# ---- message building

def test_message_has_both_parts_and_expected_headers():
    message = email_service.build_message("alice@example.com",
                                          email_service.password_changed("Alice"))
    assert message["To"] == "alice@example.com"
    assert "no-reply@example.test" in message["From"]
    assert message.get_body(preferencelist=("plain",)) is not None
    assert message.get_body(preferencelist=("html",)) is not None


@pytest.mark.parametrize("bad", ["a@example.com\r\nBcc: evil@example.com", "no-at-sign", ""])
def test_bad_recipient_addresses_are_rejected(bad):
    with pytest.raises(ValueError):
        email_service.build_message(bad, email_service.password_changed("Alice"))


# ---- sending

def test_starttls_login_and_send(fake_smtp):
    ok = email_service.send_email("alice@example.com", email_service.password_changed("Alice"))
    assert ok is True
    server = fake_smtp.instances[0]
    assert (server.host, server.port) == ("smtp.example.test", 587)
    assert "starttls" in server.calls and ("login", "mailer", "pw") in server.calls
    assert server.sent["To"] == "alice@example.com" and "quit" in server.calls
    assert server.timeout == email_service.SMTP_TIMEOUT_SECONDS


def test_ssl_mode_does_not_use_starttls(fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_security", "ssl")
    assert email_service.send_email("alice@example.com", email_service.password_changed("A")) is True
    assert "starttls" not in fake_smtp.instances[0].calls


def test_login_is_skipped_when_no_smtp_user(fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", None)
    email_service.send_email("alice@example.com", email_service.password_changed("A"))
    assert not any(isinstance(c, tuple) and c[0] == "login" for c in fake_smtp.instances[0].calls)


def test_wrong_credentials_return_false_and_do_not_raise(fake_smtp, caplog):
    fake_smtp.fail_login = True
    assert email_service.send_email("alice@example.com", email_service.password_changed("A")) is False
    assert "pw" not in caplog.text.replace("rejected", "")  # the password is never logged


def test_network_failure_returns_false(monkeypatch):
    def boom(*a, **k):
        raise OSError("network down")
    monkeypatch.setattr(smtplib, "SMTP", boom)
    assert email_service.send_email("alice@example.com", email_service.password_changed("A")) is False


def test_nothing_is_sent_when_smtp_is_not_configured(fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", None)
    assert email_service.send_email("alice@example.com", email_service.password_changed("A")) is False
    assert fake_smtp.instances == []


def test_dev_log_mode_prints_the_message_but_does_not_send(fake_smtp, monkeypatch, caplog):
    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(settings, "email_log_links", True)
    with caplog.at_level("INFO", logger="falcon_eye"):
        email_service.send_email("alice@example.com", email_service.password_reset("Alice", "DEVTOKEN"))
    assert "DEVTOKEN" in caplog.text and fake_smtp.instances == []


def test_settings_flags(monkeypatch):
    assert settings.email_enabled is True
    monkeypatch.setattr(settings, "email_from", None)
    assert settings.email_enabled is False and settings.email_available is False
    monkeypatch.setattr(settings, "email_log_links", True)
    assert settings.email_available is True
