# Architecture

```
AI agents (your code) --/v1/* with an agent key--> FastAPI backend --> PostgreSQL / SQLite
Browser (React app)  --/api/* with a login token--> FastAPI backend
```

## Backend (`main.py` and the modules beside it)
- `main.py` creates the app, error handlers, CORS, security headers and body-size limit, and runs the database upgrade at start-up.
- `routers/` holds the endpoints: `auth`, `workspaces`, `agents`, `policies`, `firewall` (the agent API), `events`, `approvals`, `dashboard`, `assistant`.
- `policy.py` is the policy engine. It is pure Python with no web or database imports, so the most security-critical logic is small and unit-tested. `catalog.py` holds action types and policy templates.
- `deps.py` authenticates people (bearer token) and agents (key) and checks workspace membership and role on every request. `security.py` hashes passwords (Argon2) and signs tokens. `agent_keys.py` creates and verifies agent keys.
- `approval_service.py` enforces the approval rules. `audit.py` writes the audit log. `rate_limiter.py` limits requests. `assistant_service.py` and `retrieval.py` power the support assistant (documentation search plus an optional LLM called only from the backend).
- `models.py`, `database.py`, `migrations.py` define and upgrade the database.

## The firewall pipeline
1. The agent calls `POST /v1/evaluate` with its key.
2. Falcon Eye authenticates the key (hash comparison), rate-limits and validates the request.
3. A repeated `request_id` returns the earlier result (replay protection).
4. A disabled agent is blocked; otherwise the policy engine decides.
5. The event is stored (and an approval request when needed), and an audit entry is written, in one transaction.
6. The agent gets `ALLOW`, `BLOCK` or `REQUIRE_APPROVAL` with a plain-language reason and `executed: false`.

## Frontend (`frontend/`)
React + Vite. `src/api.js` talks to the backend and turns errors into friendly messages; `src/pages/` has one file per screen; `src/components/` holds shared pieces. The app uses only real API data.

## Tenant isolation
Every `/workspaces/{id}/...` route runs through `require_role`, which looks up the caller's membership server-side and returns 404 for workspaces they do not belong to. Records carry a `workspace_id`, and every query filters on it.
