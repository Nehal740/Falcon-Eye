"""Sending email (SMTP) and the Falcon Eye email templates.

Emails are sent in the background after the web response, so a slow mail
server never makes sign-up or sign-in slow, and a mail failure never breaks
them. Nothing secret is written to the log: only the kind of failure.
"""

import html
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr
from typing import NamedTuple

from config import settings

logger = logging.getLogger("falcon_eye")

SMTP_TIMEOUT_SECONDS = 15


class Rendered(NamedTuple):
    subject: str
    text: str
    html: str


# --------------------------------------------------------------------------
# Links (the token sits after '#', so it is never sent to a server or logged)
# --------------------------------------------------------------------------

def verify_link(token: str) -> str:
    return f"{settings.app_base_url}/#/verify-email?token={token}"


def reset_link(token: str) -> str:
    return f"{settings.app_base_url}/#/reset-password?token={token}"


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------

def _e(value: str) -> str:
    return html.escape(value or "", quote=True)


def _layout(heading: str, paragraphs: list[str], button: tuple[str, str] | None,
            footer: str) -> str:
    logo = f"{settings.app_base_url}/falcon-eye-icon.png"
    body = "".join(f'<p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:#2b3a55">{p}</p>'
                   for p in paragraphs)
    cta = ""
    if button:
        label, url = button
        cta = (f'<p style="margin:22px 0"><a href="{_e(url)}" style="background:#347cf5;color:#ffffff;'
               f'text-decoration:none;font-weight:700;font-size:15px;padding:12px 22px;'
               f'border-radius:8px;display:inline-block">{_e(label)}</a></p>'
               f'<p style="margin:0 0 14px;font-size:12px;line-height:1.5;color:#6b7891">'
               f'If the button does not work, copy this address into your browser:<br>'
               f'<span style="word-break:break-all">{_e(url)}</span></p>')
    return (
        '<!doctype html><html><body style="margin:0;padding:0;background:#f3f6fb;'
        'font-family:Arial,Helvetica,sans-serif">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:28px 12px">'
        '<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;'
        'background:#ffffff;border-radius:12px;overflow:hidden">'
        '<tr><td style="background:#0a1226;padding:18px 26px">'
        f'<img src="{_e(logo)}" width="36" height="36" alt="" style="vertical-align:middle;border-radius:8px">'
        '<span style="color:#ffffff;font-size:18px;font-weight:700;vertical-align:middle;margin-left:10px">Falcon Eye</span>'
        '</td></tr><tr><td style="padding:28px 26px 10px">'
        f'<h1 style="margin:0 0 16px;font-size:21px;color:#0a1226">{_e(heading)}</h1>{body}{cta}'
        '</td></tr><tr><td style="padding:14px 26px 24px;border-top:1px solid #e6ebf3;'
        f'font-size:12px;line-height:1.5;color:#6b7891">{footer}'
        '<br>Falcon Eye &middot; AI Agent Firewall &middot; Powerful security. Simple experience.</td></tr>'
        '</table></td></tr></table></body></html>'
    )


def welcome_and_verify(name: str, token: str) -> Rendered:
    url = verify_link(token)
    first = (name or "there").split()[0]
    hours = settings.verify_token_hours
    text = (f"Hello {first},\n\nWelcome to Falcon Eye. Your account has been created.\n\n"
            f"Please confirm your email address:\n{url}\n\n"
            f"This link works for {hours} hours. You can already sign in and set up your workspace.\n\n"
            "If you did not create this account, you can ignore this email.\n\n"
            "Falcon Eye - AI Agent Firewall")
    page = _layout(
        f"Welcome to Falcon Eye, {first}",
        ["Your account has been created and your private workspace is ready.",
         "Please confirm your email address so we can reach you if something needs your attention, "
         "and so you can reset your password later.",
         f"The link works for {hours} hours."],
        ("Confirm my email", url),
        "If you did not create this account, you can ignore this email.")
    return Rendered("Welcome to Falcon Eye - please confirm your email", text, page)


def verify_again(name: str, token: str) -> Rendered:
    url = verify_link(token)
    first = (name or "there").split()[0]
    text = (f"Hello {first},\n\nConfirm your email address for Falcon Eye:\n{url}\n\n"
            f"This link works for {settings.verify_token_hours} hours.\n\n"
            "If you did not ask for this, you can ignore this email.\n\nFalcon Eye - AI Agent Firewall")
    page = _layout("Confirm your email address",
                   [f"Hello {_e(first)}, use the button below to confirm your email address."],
                   ("Confirm my email", url), "If you did not ask for this, you can ignore this email.")
    return Rendered("Confirm your Falcon Eye email address", text, page)


def password_reset(name: str, token: str) -> Rendered:
    url = reset_link(token)
    first = (name or "there").split()[0]
    minutes = settings.reset_token_minutes
    text = (f"Hello {first},\n\nWe received a request to reset your Falcon Eye password.\n\n"
            f"Choose a new password here:\n{url}\n\n"
            f"This link works once and expires in {minutes} minutes.\n\n"
            "If you did not ask for this, ignore this email: your password stays the same.\n\n"
            "Falcon Eye - AI Agent Firewall")
    page = _layout("Reset your password",
                   [f"Hello {_e(first)}, we received a request to reset your Falcon Eye password.",
                    f"The link works once and expires in {minutes} minutes."],
                   ("Choose a new password", url),
                   "If you did not ask for this, ignore this email: your password stays the same.")
    return Rendered("Reset your Falcon Eye password", text, page)


def password_changed(name: str) -> Rendered:
    first = (name or "there").split()[0]
    text = (f"Hello {first},\n\nThe password for your Falcon Eye account was just changed, "
            "and other devices were signed out.\n\n"
            "If this was you, no action is needed. If it was not, reset your password straight away "
            f"using 'Forgot password' on {settings.app_base_url} and contact your administrator.\n\n"
            "Falcon Eye - AI Agent Firewall")
    page = _layout("Your password was changed",
                   [f"Hello {_e(first)}, the password for your Falcon Eye account was just changed, "
                    "and other devices were signed out.",
                    "If this was you, no action is needed.",
                    "If it was not, reset your password straight away with <b>Forgot password</b> "
                    "on the sign-in page and contact your administrator."],
                   None, "You receive this security notice every time a password changes.")
    return Rendered("Your Falcon Eye password was changed", text, page)


# --------------------------------------------------------------------------
# Sending
# --------------------------------------------------------------------------

def _clean_address(value: str) -> str:
    """Return a bare address or raise. Newlines would allow header injection."""
    if not value or "\r" in value or "\n" in value:
        raise ValueError("invalid address")
    address = parseaddr(value)[1]
    if "@" not in address or " " in address:
        raise ValueError("invalid address")
    return address


def build_message(to: str, rendered: Rendered) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = rendered.subject
    from_name, from_address = parseaddr(settings.email_from or "")
    message["From"] = formataddr((from_name, _clean_address(from_address or settings.email_from or "")))
    message["To"] = _clean_address(to)
    if settings.email_reply_to:
        message["Reply-To"] = _clean_address(settings.email_reply_to)
    message["Date"] = formatdate(localtime=False)
    domain = from_address.split("@")[-1] if "@" in from_address else None
    message["Message-ID"] = make_msgid(domain=domain)
    message["Auto-Submitted"] = "auto-generated"
    message.set_content(rendered.text)
    message.add_alternative(rendered.html, subtype="html")
    return message


def send_email(to: str, rendered: Rendered) -> bool:
    """Send one email. Returns True if the mail server accepted it. Never raises."""
    if not settings.email_enabled:
        if settings.email_log_links:
            logger.info("EMAIL (development, not sent) to=%s subject=%s\n%s",
                        to, rendered.subject, rendered.text)
        else:
            logger.info("Email not sent because SMTP is not configured: %s", rendered.subject)
        return False
    try:
        message = build_message(to, rendered)
        host = settings.smtp_host or ""
        context = ssl.create_default_context()
        if settings.smtp_security == "ssl":
            server = smtplib.SMTP_SSL(host, settings.smtp_port,
                                      timeout=SMTP_TIMEOUT_SECONDS, context=context)
        else:
            server = smtplib.SMTP(host, settings.smtp_port,
                                  timeout=SMTP_TIMEOUT_SECONDS)
        try:
            server.ehlo()
            if settings.smtp_security == "starttls":
                server.starttls(context=context)
                server.ehlo()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password or "")
            server.send_message(message)
        finally:
            try:
                server.quit()
            except Exception:  # noqa: BLE001 - closing a broken connection
                pass
        return True
    except smtplib.SMTPAuthenticationError:
        logger.warning("Email not sent: the mail server rejected SMTP_USER/SMTP_PASSWORD.")
    except smtplib.SMTPResponseException as exc:
        logger.warning("Email not sent: mail server answered %s.", exc.smtp_code)
    except Exception as exc:  # noqa: BLE001 - network, TLS, bad address, ...
        logger.warning("Email not sent: %s.", type(exc).__name__)
    return False
