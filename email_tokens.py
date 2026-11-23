"""One-time email links: create, check and use them.

Only the SHA-256 hash of a token is stored. A token can be used once and
expires. Asking for a new token cancels the older unused ones of that kind.
"""

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from models import EmailToken, User, aware, utcnow

VERIFY_EMAIL = "verify_email"
RESET_PASSWORD = "reset_password"


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue(db: Session, user: User, purpose: str, ttl: timedelta) -> str:
    """Create a token for the user and return the raw value (shown only in the email)."""
    now = utcnow()
    db.query(EmailToken).filter(
        EmailToken.user_id == user.id, EmailToken.purpose == purpose,
        EmailToken.used_at.is_(None)).update({EmailToken.used_at: now}, synchronize_session=False)
    raw = secrets.token_urlsafe(32)
    db.add(EmailToken(user_id=user.id, purpose=purpose, token_hash=hash_token(raw),
                      expires_at=now + ttl))
    return raw


def consume(db: Session, raw: str, purpose: str) -> User | None:
    """Use a token. Returns its user, or None if unknown, used, expired or the wrong kind."""
    if not raw or len(raw) > 200:
        return None
    row = db.query(EmailToken).filter(
        EmailToken.token_hash == hash_token(raw), EmailToken.purpose == purpose).first()
    if row is None or row.used_at is not None:
        return None
    now = utcnow()
    expires = aware(row.expires_at)
    if expires is None or expires <= now:
        return None
    # Compare-and-set so two simultaneous requests cannot both use the same token.
    claimed = db.query(EmailToken).filter(
        EmailToken.id == row.id, EmailToken.used_at.is_(None)).update(
        {EmailToken.used_at: now}, synchronize_session=False)
    if claimed != 1:
        return None
    user = db.get(User, row.user_id)
    return user if user is not None and user.is_active else None


def purge_old(db: Session) -> None:
    """Delete tokens that expired more than a week ago."""
    db.query(EmailToken).filter(
        EmailToken.expires_at < utcnow() - timedelta(days=7)).delete(synchronize_session=False)
