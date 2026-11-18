# Troubleshooting

## The dashboard says it can't reach the server
The backend is not running or not reachable. Start it with `python -m uvicorn main:app --reload` and open http://127.0.0.1:8000/health. In Docker: `docker compose logs backend`.

## The backend won't start: "JWT_SECRET_KEY is not set" or "Unsafe production configuration"
In production, set `JWT_SECRET_KEY` in `.env` (32+ characters): `python -c "import secrets;print(secrets.token_urlsafe(48))"`. Also set `DATABASE_URL` and a specific `CORS_ORIGINS` (not `*`). In development a missing secret only produces a warning and you are signed out on every restart.

## Port already in use
Run the backend on another port: `python -m uvicorn main:app --port 8001` and change the `target` in `frontend/vite.config.js`. Vite picks another port itself if 5173 is busy; add that origin to `CORS_ORIGINS` if you call the API directly.

## What do 401, 403 and 404 mean?
- **401** – you are not signed in, your session expired, or an agent key is wrong or revoked.
- **403** – you are signed in but your role does not allow that (viewers are read-only; only admins manage agents and policies).
- **404** – it does not exist, **or you are not a member of that workspace**.

## Agent key rejected (401 invalid_agent_key)
The key was mistyped, revoked, or replaced when you rotated it. Rotate the key under Agents and update your agent. A key can't be shown again after creation. Send it as `Authorization: Bearer fe_live_...`.

## Everything is blocked
That is the default when no rule matches. Add a policy (start from a template), make sure it is turned on and applies to the agent. Use the **Policy tester** to see which rule decided.

## Approval returns 409 already_decided
Someone already approved or rejected it, or it expired. Refresh the Approvals page.

## The assistant says "Documentation search only"
No `LLM_API_KEY` is configured. Set `LLM_PROVIDER`, `LLM_API_KEY` (and optionally `LLM_MODEL`) in `.env` and restart the backend.

## npm install fails: invalid package name
`frontend/package.json` must have the name `falcon-eye-ai-firewall-ui` (lowercase, no spaces), also in `package-lock.json`.

## CORS error in the browser console
Add your frontend origin to `CORS_ORIGINS` (comma separated) and restart the backend. The Vite proxy (`/api`) avoids CORS entirely in development.

## Locked account or 429 errors
After `LOGIN_MAX_ATTEMPTS` wrong passwords the account is locked for `LOGIN_LOCKOUT_MINUTES`. `429 rate_limited` means too many requests; wait for the `Retry-After` seconds.

## My old events from before the upgrade
They are kept. On first start the upgrade gives every existing user a workspace and hands the old events and approvals to the oldest account. Old agents like `demo-agent` show in the event log only; register them again under Agents to get a key.
