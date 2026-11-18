"""Passwords and login tokens."""

import secrets
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from config import settings

# Argon2 by default. Existing hashes created by the first version still verify.
_password_hash = PasswordHash.recommended()
_dummy_hash: str | None = None


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _password_hash.verify(password, hashed)
    except Exception:
        return False


def burn_password_check(password: str) -> None:
    """Spend the same time as a real check, so response time does not reveal
    whether an email address has an account."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = _password_hash.hash(secrets.token_urlsafe(12))
    verify_password(password, _dummy_hash)


def create_access_token(user_id: int) -> tuple[str, str, datetime]:
    """Return ``(token, jti, expires_at)``."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.access_token_minutes)
    jti = secrets.token_hex(16)
    token = jwt.encode(
        {"sub": str(user_id), "jti": jti, "iat": int(now.timestamp()), "exp": expires},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, jti, expires


def decode_access_token(token: str) -> dict | None:
    """Return the token's claims, or None if it is invalid or expired."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],  # never trust the token's own header
            options={"require": ["exp", "sub", "jti", "iat"]},
        )
    except jwt.PyJWTError:
        return None
    return claims
