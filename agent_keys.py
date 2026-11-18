"""Agent credential helpers (standard library only).

An agent key looks like ``fe_live_<12 hex chars>_<43 url-safe chars>``.

* The first part (``fe_live_<12 hex>``) is the *prefix*. It is stored in
  plain text so the key can be looked up and shown in the dashboard.
* The whole key is 256 bits of randomness. Only its SHA-256 hash is stored,
  so a database leak does not reveal usable keys.
* The full key is shown to the user exactly once, when it is created.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

KEY_PREFIX = "fe_live_"
_KEY_RE = re.compile(r"^fe_live_([0-9a-f]{12})_([A-Za-z0-9_\-]{43})$")


def generate_agent_key() -> tuple[str, str, str]:
    """Return ``(full_key, prefix, sha256_hash)``."""
    public = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    full_key = f"{KEY_PREFIX}{public}_{secret}"
    return full_key, f"{KEY_PREFIX}{public}", hash_key(full_key)


def hash_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode("utf-8")).hexdigest()


def parse_agent_key(raw: str | None) -> str | None:
    """Validate the shape of a key and return its prefix, or None."""
    if not raw:
        return None
    match = _KEY_RE.match(raw.strip())
    if not match:
        return None
    return f"{KEY_PREFIX}{match.group(1)}"


def verify_agent_key(raw: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_key(raw.strip()), stored_hash)


def mask_key(prefix: str) -> str:
    return f"{prefix}_{'•' * 12}"
