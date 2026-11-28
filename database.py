import logging

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from config import settings

logger = logging.getLogger("falcon_eye")

DATABASE_URL = settings.database_url

if not DATABASE_URL:
    if settings.is_production:
        raise RuntimeError("DATABASE_URL is not configured.")
    DATABASE_URL = "sqlite:///./falcon_eye.db"
    logger.warning(
        "DATABASE_URL is not set - using a local SQLite file (falcon_eye.db). "
        "Set DATABASE_URL to use PostgreSQL."
    )

_is_sqlite = DATABASE_URL.startswith("sqlite")
_engine_args: dict = {"pool_pre_ping": True}

if _is_sqlite:
    _engine_args["connect_args"] = {"check_same_thread": False}
    if ":memory:" in DATABASE_URL or DATABASE_URL in ("sqlite://", "sqlite:///"):
        # A single shared connection so every session sees the same in-memory DB.
        _engine_args["poolclass"] = StaticPool

if not _is_sqlite and "supabase" in DATABASE_URL:
    # Supabase requires encrypted connections; its shared pooler also dislikes prepared statements.
    _engine_args["connect_args"] = {"sslmode": "require", "prepare_threshold": None}

engine = create_engine(DATABASE_URL, **_engine_args)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
