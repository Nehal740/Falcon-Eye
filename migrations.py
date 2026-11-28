"""Database setup and upgrades.

Run automatically at start-up (``init_db``). It never deletes data:

1. ``create_all`` creates any table that does not exist yet.
2. ``add_missing_columns`` adds new columns to tables created by an earlier
   version of Falcon Eye (``ALTER TABLE ... ADD COLUMN``). New columns are
   always nullable or have a default, so existing rows stay valid.
3. Numbered, one-time migrations create indexes and move data from the
   original single-user MVP into the new multi-user structure. Each one is
   recorded in ``schema_migrations`` and is safe to run twice.

Works on PostgreSQL and SQLite.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

import models  # noqa: F401  (registers all tables on Base.metadata)
from database import Base, SessionLocal, engine
from models import (
    ApprovalRequest, FirewallEvent, SchemaMigration, User, WorkspaceMember,
)
from workspace_service import create_workspace, personal_workspace_name

logger = logging.getLogger("falcon_eye")


# --------------------------------------------------------------------------
# Step 2: add columns that older databases are missing
# --------------------------------------------------------------------------

def _default_clause(column) -> str:
    default = column.server_default
    if default is None:
        return ""
    arg = default.arg
    if isinstance(arg, str):
        return " DEFAULT '" + arg.replace("'", "''") + "'"
    return " DEFAULT " + str(arg.compile(dialect=engine.dialect))


def add_missing_columns() -> list[str]:
    quote = engine.dialect.identifier_preparer.quote
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    added: list[str] = []

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            have = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in have:
                    continue
                ddl = (
                    f"ALTER TABLE {quote(table.name)} ADD COLUMN {quote(column.name)} "
                    f"{column.type.compile(dialect=engine.dialect)}"
                    f"{_default_clause(column)}"
                )
                if not column.nullable and column.server_default is not None:
                    ddl += " NOT NULL"
                for fk in column.foreign_keys:
                    ddl += f" REFERENCES {quote(fk.column.table.name)} ({quote(fk.column.name)})"
                conn.execute(text(ddl))
                added.append(f"{table.name}.{column.name}")
    if added:
        logger.info("Database upgrade: added columns %s", ", ".join(added))
    return added


# --------------------------------------------------------------------------
# Step 3: numbered migrations
# --------------------------------------------------------------------------

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_events_workspace_created ON firewall_events (workspace_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_events_agent_pk ON firewall_events (agent_pk)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_events_agent_request ON firewall_events (agent_pk, request_id)",
    "CREATE INDEX IF NOT EXISTS ix_approvals_workspace_status ON approval_requests (workspace_id, status)",
]


def _m1_indexes(db):
    for statement in _INDEXES:
        db.execute(text(statement))


def _m2_workspaces_and_legacy_data(db):
    """Give every existing user a workspace and adopt pre-workspace records."""
    users = db.query(User).order_by(User.id).all()
    first_workspace_id = None

    for user in users:
        membership = (db.query(WorkspaceMember)
                      .filter(WorkspaceMember.user_id == user.id)
                      .order_by(WorkspaceMember.id).first())
        if membership is None:
            workspace = create_workspace(db, user, personal_workspace_name(user.full_name))
            workspace_id = workspace.id
            logger.info("Created workspace for existing user %s", user.id)
        else:
            workspace_id = membership.workspace_id
        if first_workspace_id is None:
            first_workspace_id = workspace_id

    if first_workspace_id is None:
        return  # no users yet; nothing to adopt

    # Records from the original single-user MVP had no owner. Hand them to
    # the oldest account (the original developer) so no data is lost.
    db.query(FirewallEvent).filter(FirewallEvent.workspace_id.is_(None)).update(
        {FirewallEvent.workspace_id: first_workspace_id}, synchronize_session=False)
    db.query(ApprovalRequest).filter(ApprovalRequest.workspace_id.is_(None)).update(
        {ApprovalRequest.workspace_id: first_workspace_id}, synchronize_session=False)
    db.query(FirewallEvent).filter(FirewallEvent.agent_name.is_(None)).update(
        {FirewallEvent.agent_name: FirewallEvent.agent_id}, synchronize_session=False)
    db.query(ApprovalRequest).filter(ApprovalRequest.agent_name.is_(None)).update(
        {ApprovalRequest.agent_name: ApprovalRequest.agent_id}, synchronize_session=False)


MIGRATIONS = [
    (1, "indexes_on_legacy_tables", _m1_indexes),
    (2, "personal_workspaces_and_legacy_data", _m2_workspaces_and_legacy_data),
]


def run_migrations() -> list[int]:
    applied: list[int] = []
    db = SessionLocal()
    try:
        done = {row.version for row in db.query(SchemaMigration).all()}
        for version, name, function in MIGRATIONS:
            if version in done:
                continue
            try:
                function(db)
                db.add(SchemaMigration(version=version, name=name))
                db.commit()
                applied.append(version)
                logger.info("Applied database migration %s (%s)", version, name)
            except IntegrityError:
                db.rollback()  # another process applied it first
            except Exception:
                db.rollback()
                raise
    finally:
        db.close()
    return applied


def lock_down_supabase_api() -> bool:
    """On Supabase, tables in the public schema can be reached through Supabase's own REST API
    with the public 'anon' key unless row-level security is on. Falcon Eye talks to the database
    directly as the owner (which bypasses RLS), so we switch RLS on for every table and remove the
    API roles' access. Returns True if it ran. Safe to run repeatedly; does nothing elsewhere."""
    if engine.dialect.name != "postgresql":
        return False
    try:
        with engine.begin() as conn:
            has_roles = conn.execute(text("SELECT count(*) FROM pg_roles WHERE rolname IN ('anon','authenticated')")).scalar()
            if not has_roles:
                return False
            conn.execute(text("""
                DO $$
                DECLARE t record;
                BEGIN
                  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
                    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
                  END LOOP;
                  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
                    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon;
                  END IF;
                  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated;
                    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM authenticated;
                  END IF;
                END $$;
            """))
        logger.info("Supabase detected: row-level security enabled and public API access removed.")
        return True
    except Exception:  # noqa: BLE001 - never stop start-up because of this
        logger.exception("Could not lock down the Supabase public API. Run scripts/supabase_lockdown.sql by hand.")
        return False


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    add_missing_columns()
    run_migrations()
    lock_down_supabase_api()
