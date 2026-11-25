# Environment Configuration

Falcon Eye reads settings from environment variables. For local use copy `.env.example` to `.env`. When you run the backend directly (`python -m uvicorn main:app`) it reads the `.env` file in the project folder; with Docker Compose the `.env` file is passed in automatically. Real environment variables always win over `.env`; the automated tests ignore `.env` on purpose. **Never commit `.env`.**

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` or `production`. Production refuses to start with a weak secret, no database URL, or `*` in CORS. |
| `DATABASE_URL` | local SQLite file (development only) | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pass@host:5432/falconeye`. Required in production. |
| `JWT_SECRET_KEY` | random per start (development only) | Signs login tokens. Required in production, 32+ characters. |
| `ACCESS_TOKEN_MINUTES` | `60` | Login token lifetime. |
| `COOKIE_SECURE` | `true` in production | Mark the session cookie HTTPS-only. Set `true` once you serve over HTTPS. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Browser origins allowed to call the API. |
| `TRUST_PROXY` | `false` | Trust `X-Forwarded-For` from a reverse proxy so rate limits use the real client address. Only enable it behind a proxy you control. |
| `ENABLE_API_DOCS` | `true` | Serve Swagger at `/docs`. |
| `MAX_BODY_BYTES` | `1000000` | Largest request body accepted. |
| `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES` | `5`, `15` | Brute-force protection. |
| `AGENT_RATE_LIMIT_PER_MINUTE` | `120` | Requests per minute per agent. |
| `APPROVAL_TTL_HOURS` | `24` | When pending approvals expire. |
| `AGENT_CONNECTED_MINUTES` | `15` | An agent counts as "Connected" if seen within this time. |
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `openai` (also OpenAI-compatible servers). |
| `LLM_API_KEY` | none | Enables generated assistant answers. Without it the assistant shows documentation passages. Kept on the server only. |
| `LLM_MAX_TOKENS` | `1500` | Room for each answer. Some models use part of it for "thinking", so keep it generous. |
| `LLM_MODEL`, `LLM_BASE_URL` | `claude-sonnet-5-5`, provider default | Model name and optional custom endpoint. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SECURITY` | none, `587`, none, none, `starttls` | Mail server for welcome emails, email confirmation and password reset. `SMTP_SECURITY` is `starttls` (port 587), `ssl` (port 465) or `none`. Without `SMTP_HOST` no email is sent. See `docs/EMAIL.md`. |
| `EMAIL_FROM`, `EMAIL_REPLY_TO` | none | Sender shown to people, e.g. `Falcon Eye <no-reply@yourdomain.com>`. `EMAIL_FROM` is required to send. |
| `APP_BASE_URL` | first `CORS_ORIGINS` entry | Public web address used for links inside emails. Docker sets it automatically; set `https://your-domain` on a server. |
| `RESET_TOKEN_MINUTES`, `VERIFY_TOKEN_HOURS` | `60`, `48` | How long reset and confirmation links work. |
| `EMAIL_LOG_LINKS` | `false` | Development only: write emails (with their links) to the server log instead of sending. Refused in production. |
| `DOCS_DIR` | `docs/` next to the backend | Folder of Markdown files the assistant searches. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `falconeye`, none, `falconeye` | Used only by `docker-compose.yml`. |

Generate a secret: `python -c "import secrets;print(secrets.token_urlsafe(48))"`.


## Output verification

| Variable | Default | Meaning |
|---|---|---|
| `VERIFY_ENABLED` | `true` | Turns `/v1/verify` on or off |
| `VERIFY_SENSITIVITY` | `standard` | `strict` also holds medium-risk consequential outputs for approval |
