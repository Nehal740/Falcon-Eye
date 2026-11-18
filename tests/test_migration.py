"""The upgrade from the original single-user database must keep every record."""

import pytest

pytest.importorskip("sqlalchemy")

LEGACY_SCHEMA = [
    """CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR NOT NULL, hashed_password VARCHAR NOT NULL,
       full_name VARCHAR NOT NULL, created_at TIMESTAMP)""",
    """CREATE TABLE firewall_events (id INTEGER PRIMARY KEY, event_id VARCHAR, agent_id VARCHAR NOT NULL,
       action VARCHAR NOT NULL, resource VARCHAR, decision VARCHAR NOT NULL, created_at TIMESTAMP)""",
    """CREATE TABLE approval_requests (id INTEGER PRIMARY KEY, approval_id VARCHAR, agent_id VARCHAR NOT NULL,
       action VARCHAR NOT NULL, resource VARCHAR, reason VARCHAR, status VARCHAR, created_at TIMESTAMP)""",
]


def test_legacy_database_is_upgraded_without_losing_data():
    from sqlalchemy import text

    from database import Base, engine
    from migrations import init_db

    Base.metadata.drop_all(bind=engine)
    with engine.begin() as conn:
        for statement in LEGACY_SCHEMA:
            conn.execute(text(statement))
        conn.execute(text("INSERT INTO users (id, email, hashed_password, full_name) "
                          "VALUES (1, 'old@example.com', 'hash', 'Old User')"))
        conn.execute(text("INSERT INTO firewall_events (event_id, agent_id, action, resource, decision) "
                          "VALUES ('e1', 'demo-agent', 'delete_file', 'x', 'BLOCK')"))
        conn.execute(text("INSERT INTO approval_requests (approval_id, agent_id, action, resource, reason, status) "
                          "VALUES ('a1', 'demo-agent', 'send_external_email', 'y', 'r', 'PENDING')"))

    init_db()
    init_db()  # running twice must be safe

    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM users")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM workspaces")).scalar() == 1
        row = conn.execute(text("SELECT workspace_id, agent_name FROM firewall_events")).one()
        assert row[0] is not None and row[1] == "demo-agent"
        row = conn.execute(text("SELECT workspace_id, agent_name, status FROM approval_requests")).one()
        assert row[0] is not None and row[1] == "demo-agent" and row[2] == "PENDING"
        assert conn.execute(text("SELECT COUNT(*) FROM schema_migrations")).scalar() >= 2
        owner = conn.execute(text("SELECT role FROM workspace_members")).scalar()
        assert owner == "owner"
