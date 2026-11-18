"""Falcon Eye configuration.

All settings come from environment variables (see .env.example). Nothing
sensitive is hard-coded. Import ``settings`` from this module everywhere.
"""

import logging
import os
import secrets

logger = logging.getLogger("falcon_eye")


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except (TypeError, ValueError):
        logger.warning("Setting %s is not a number; using %s.", name, default)
        return default


def _bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.environment = (_env("ENVIRONMENT", "development") or "development").lower()
        self.is_production = self.environment == "production"

        # Database
        self.database_url = _env("DATABASE_URL")

        # Authentication
        self.jwt_secret: str = _env("JWT_SECRET_KEY") or ""
        self.jwt_algorithm = "HS256"
        self.access_token_minutes = _int("ACCESS_TOKEN_MINUTES", 60)
        self.cookie_name = "fe_session"
        self.cookie_secure = _bool("COOKIE_SECURE", self.is_production)
        self.login_max_attempts = _int("LOGIN_MAX_ATTEMPTS", 5)
        self.login_lockout_minutes = _int("LOGIN_LOCKOUT_MINUTES", 15)

        # Network
        origins = _env("CORS_ORIGINS") or "http://localhost:5173,http://127.0.0.1:5173"
        self.cors_origins = [o.strip() for o in origins.split(",") if o.strip()]
        self.trust_proxy = _bool("TRUST_PROXY", False)
        self.enable_docs = _bool("ENABLE_API_DOCS", True)
        self.max_body_bytes = _int("MAX_BODY_BYTES", 1_000_000)

        # Firewall
        self.agent_rate_limit_per_minute = _int("AGENT_RATE_LIMIT_PER_MINUTE", 120)
        self.approval_ttl_hours = _int("APPROVAL_TTL_HOURS", 24)
        self.agent_connected_minutes = _int("AGENT_CONNECTED_MINUTES", 15)

        # AI support assistant (optional)
        self.llm_provider = (_env("LLM_PROVIDER", "anthropic") or "anthropic").lower()
        self.llm_api_key = _env("LLM_API_KEY")
        self.llm_model = _env("LLM_MODEL", "claude-sonnet-5-5")
        self.llm_base_url = _env("LLM_BASE_URL")
        self.docs_dir = _env("DOCS_DIR")

        self._resolve_secrets()

    def _resolve_secrets(self) -> None:
        if self.jwt_secret:
            return
        if self.is_production:
            raise RuntimeError(
                "JWT_SECRET_KEY is not set. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        # Development only: a random per-process secret. Everyone is signed
        # out whenever the server restarts, which is safe but inconvenient.
        self.jwt_secret = secrets.token_urlsafe(48)
        logger.warning(
            "JWT_SECRET_KEY is not set - using a temporary secret. "
            "You will be signed out whenever the server restarts."
        )

    def validate_for_production(self) -> list[str]:
        """Return a list of problems that must be fixed before going live."""
        problems = []
        if not self.is_production:
            return problems
        if len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET_KEY must be at least 32 characters.")
        if not self.database_url:
            problems.append("DATABASE_URL must be set.")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must not contain '*'.")
        if not self.cookie_secure:
            # Not fatal (the web app signs in with a bearer token), but it
            # should be fixed as soon as you serve Falcon Eye over HTTPS.
            logger.warning("COOKIE_SECURE is false. Set COOKIE_SECURE=true when serving over HTTPS.")
        return problems

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)


settings = Settings()
