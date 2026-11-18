# API Reference

Interactive documentation (Swagger) is served by the backend at `/docs` when `ENABLE_API_DOCS=true`. Machine-readable schema: `/openapi.json`.

This table is generated from the code, so it matches what the server really offers. `GET /health` (and `GET /health/ready`, which also checks the database) are public.

## Who can call what
- **People** sign in with `POST /auth/login` and send `Authorization: Bearer <access_token>`.
- **AI agents** send their agent key the same way (`Authorization: Bearer fe_live_...`) or in an `X-Falcon-Key` header. Agent keys work **only** on `/v1/*`.
- Workspace roles, from least to most powerful: **viewer** (read-only), **member** (also decides approvals), **admin** (also manages agents, policies and people), **owner** (also changes roles). The "Needs" column shows the minimum role.
- Everything under `/workspaces/{workspace_id}/...` checks on the server that you belong to that workspace. If you do not, you get `404`, so other workspaces' ids are never revealed.

## Errors
Every error has the same shape and is written for people:
```json
{"error": {"code": "invalid_credentials", "message": "What happened", "hint": "What you can do about it",
           "fields": [{"field": "password", "message": "Use at least one letter and one number."}]},
 "detail": "What happened"}
```
`fields` appears only for validation errors (422). Stack traces are never returned; they go to the server log together with a short reference.

Common codes: `401 not_signed_in`, `401 invalid_agent_key`, `403 not_allowed`, `404 not_found`, `409 already_decided`, `409 request_id_reused`, `422 validation_error`, `429 rate_limited` (see the `Retry-After` header).

## Endpoints

### Agent API (called by your AI agents)

| Method | Path | What it does | Needs |
|---|---|---|---|
| `GET/POST` | `/v1/ping` | Test the connection from your agent | agent key |
| `POST` | `/v1/evaluate` | Ask the firewall whether an action is allowed | agent key |
| `GET` | `/v1/approvals/{approval_id}` | Check whether a human has decided yet | agent key |

### Authentication

| Method | Path | What it does | Needs |
|---|---|---|---|
| `POST` | `/auth/register` | Create an account and your first workspace | public |
| `POST` | `/auth/login` | Sign in | public |
| `POST` | `/auth/logout` | Sign out and invalidate this session | signed-in user |
| `POST` | `/auth/refresh` | Get a fresh access token while you are still signed in | signed-in user |
| `GET` | `/auth/me` | Who am I, and which workspaces can I use? | signed-in user |
| `POST` | `/auth/onboarding/complete` | Mark the first-time guide as finished | signed-in user |
| `POST` | `/auth/change-password` | Change your password | signed-in user |

### Workspaces and members

| Method | Path | What it does | Needs |
|---|---|---|---|
| `GET` | `/workspaces` | Workspaces I belong to | signed-in user |
| `POST` | `/workspaces` | Create another workspace | signed-in user |
| `GET` | `/workspaces/{workspace_id}` | Workspace details | viewer+ |
| `PATCH` | `/workspaces/{workspace_id}` | Rename the workspace or change its default | admin+ |
| `GET` | `/workspaces/{workspace_id}/members` | People in this workspace | viewer+ |
| `POST` | `/workspaces/{workspace_id}/members` | Add an existing Falcon Eye user to this workspace | admin+ |
| `PATCH` | `/workspaces/{workspace_id}/members/{user_id}` | Change someone's role | owner+ |
| `DELETE` | `/workspaces/{workspace_id}/members/{user_id}` | Remove someone | admin+ |
| `GET` | `/workspaces/{workspace_id}/audit-logs` | Who did what, and when | admin+ |
| `GET` | `/workspaces/{workspace_id}/assistant-config` | AI assistant settings | viewer+ |
| `PUT` | `/workspaces/{workspace_id}/assistant-config` | Change AI assistant settings | admin+ |

### Agents

| Method | Path | What it does | Needs |
|---|---|---|---|
| `GET` | `/workspaces/{workspace_id}/agents` | List agents | viewer+ |
| `POST` | `/workspaces/{workspace_id}/agents` | Register an agent and generate its key | admin+ |
| `GET` | `/workspaces/{workspace_id}/agents/{agent_id}` | Agent details | viewer+ |
| `POST` | `/workspaces/{workspace_id}/agents/{agent_id}/test-connection` | Has this agent contacted Falcon Eye recently? | viewer+ |
| `PATCH` | `/workspaces/{workspace_id}/agents/{agent_id}` | Edit an agent, or enable / disable it | admin+ |
| `POST` | `/workspaces/{workspace_id}/agents/{agent_id}/credentials/rotate` | Create a new key and revoke the old one | admin+ |
| `POST` | `/workspaces/{workspace_id}/agents/{agent_id}/credentials/revoke` | Revoke a compromised key (the agent can no longer connect) | admin+ |
| `POST` | `/workspaces/{workspace_id}/agents/{agent_id}/credentials/new` | Generate a key for an agent that has none | admin+ |
| `DELETE` | `/workspaces/{workspace_id}/agents/{agent_id}` | Delete an agent (its past events are kept) | admin+ |

### Policies

| Method | Path | What it does | Needs |
|---|---|---|---|
| `GET` | `/action-catalog` | Action categories and starter templates | signed-in user |
| `GET` | `/action-categories` | Action categories (for the policy builder) | signed-in user |
| `GET` | `/policy-templates` | Ready-made policy templates | signed-in user |
| `GET` | `/workspaces/{workspace_id}/policies` | List policies | viewer+ |
| `POST` | `/workspaces/{workspace_id}/policies` | Create a policy | admin+ |
| `POST` | `/workspaces/{workspace_id}/policies/from-template` | Create a policy from a ready-made template | admin+ |
| `GET` | `/workspaces/{workspace_id}/policies/{policy_id}` | Policy details | viewer+ |
| `PATCH` | `/workspaces/{workspace_id}/policies/{policy_id}` | Edit a policy, or switch it on / off | admin+ |
| `DELETE` | `/workspaces/{workspace_id}/policies/{policy_id}` | Delete a policy | admin+ |
| `GET` | `/workspaces/{workspace_id}/policies/{policy_id}/history` | Every change made to a policy | viewer+ |
| `POST` | `/workspaces/{workspace_id}/policies/simulate` | Test what the firewall would decide (nothing is recorded) | viewer+ |

### Events

| Method | Path | What it does | Needs |
|---|---|---|---|
| `GET` | `/workspaces/{workspace_id}/events` | Search and filter firewall events | viewer+ |
| `GET` | `/workspaces/{workspace_id}/events/{event_id}` | Full details of one event | viewer+ |

### Approvals

| Method | Path | What it does | Needs |
|---|---|---|---|
| `GET` | `/workspaces/{workspace_id}/approvals` | Approval requests (pending by default) | viewer+ |
| `POST` | `/workspaces/{workspace_id}/approvals/{approval_id}/decision` | Approve or reject a request | member+ |

### Dashboard

| Method | Path | What it does | Needs |
|---|---|---|---|
| `GET` | `/workspaces/{workspace_id}/dashboard` | Everything the dashboard needs, from real data | viewer+ |

### AI assistant

| Method | Path | What it does | Needs |
|---|---|---|---|
| `GET` | `/workspaces/{workspace_id}/assistant/status` | Is the live AI model connected? | viewer+ |
| `POST` | `/workspaces/{workspace_id}/assistant/chat` | Ask the support assistant | viewer+ |

### Service

| Method | Path | What it does | Needs |
|---|---|---|---|
| `GET` | `/health` | Is the API running? | public |
| `GET` | `/health/ready` | Is the API ready (database reachable)? | public |

## The agent request in detail
`POST /v1/evaluate` with JSON:

| Field | Required | Notes |
|---|---|---|
| `action` | yes | What the agent wants to do, e.g. `send_external_email`. Letters, numbers and `_ . : / -` only. |
| `resource` | no | What it wants to do it to (an address, a file path...). |
| `reason` | no | Why the agent wants to do it. Shown to the person approving. |
| `category` | no | One of the categories in the policy guide. Falcon Eye also infers one from the action name and uses the stricter reading, so a wrong category cannot hide a dangerous action. |
| `request_id` | no | A unique id you choose per request (1-64 characters). Sending the same id again returns the first answer with `"duplicate": true` instead of creating a second event or approval. Reusing it for a different action returns `409 request_id_reused`. |
| `metadata` | no | Extra details (an object, 4 KB at most). Do not put secrets here. |

Response:
```json
{"event_id": "evt_...", "decision": "REQUIRE_APPROVAL", "message": "A human must approve this action first.",
 "reason": "Policy 'Recommended starter policy' has a rule for category 'external_email' that says require approval.",
 "category": "external_email", "policy": {"id": 1, "name": "Recommended starter policy"},
 "approval_id": "apr_...", "approval_status_url": "/v1/approvals/apr_...", "duplicate": false, "executed": false}
```
`executed` is always `false`: Falcon Eye makes a decision and records it. Your agent performs (or skips) the action itself.

When `decision` is `REQUIRE_APPROVAL`, poll `GET /v1/approvals/{approval_id}` until `status` is `APPROVED`, `REJECTED` or `EXPIRED`.
