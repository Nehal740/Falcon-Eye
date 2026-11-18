# Database and Migrations

Falcon Eye uses SQLAlchemy and works with PostgreSQL (recommended) and SQLite (development and tests).

## Tables
`users`, `workspaces`, `workspace_members` (role per person per workspace), `agents`, `agent_credentials` (only a hash of each key is stored), `policies`, `policy_rules`, `policy_versions` (history), `firewall_events`, `approval_requests`, `approval_decisions`, `audit_logs`, `assistant_config`, `revoked_tokens` (signed-out sessions) and `schema_migrations` (which upgrades have run).

Foreign keys link everything to its workspace; queries always filter by workspace, which is what keeps tenants apart. A unique index on `(agent, request_id)` makes duplicate requests safe. Approval decisions use a compare-and-set update, so a request can only be decided once even if two people click at the same moment. All timestamps are stored in UTC.

## How upgrades work
When the backend starts (`init_db` in `migrations.py`) it:
1. creates tables that do not exist yet,
2. adds missing columns to older tables (`ALTER TABLE ... ADD COLUMN`, always nullable or with a default),
3. runs numbered one-time migrations recorded in `schema_migrations`: indexes, then a personal workspace for every existing user, and the hand-over of pre-workspace events and approvals to the oldest account.

Nothing is deleted. The steps are safe to run twice. **Back up your database before upgrading a real installation** (for PostgreSQL: `pg_dump`).

## Adding your own migration
Append `(number, "name", function)` to `MIGRATIONS` in `migrations.py`. The function receives a session and must not commit; the runner records and commits it.
