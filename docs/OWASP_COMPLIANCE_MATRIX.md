# Falcon Eye – OWASP alignment matrix

Falcon Eye is **aligned with** OWASP guidance. It is **not certified** and has not had an
independent penetration test. This page records what exists in the code, what is
checked by an automated test, and what is still missing.

Standards used: OWASP Top 10 (2021 edition), OWASP API Security Top 10 (2023), OWASP Top 10 for
LLM Applications (2025), OWASP ASVS 4.0.3 (reference only, no level claimed).
Check the OWASP site for newer editions before relying on these labels.

**Status key** – ✅ implemented and covered by an automated test · 🟡 implemented, not
covered by a test · ◑ partial · ❌ not implemented · ➖ not applicable.
Test file: `tests/test_security_owasp.py` (new) and `tests/test_api.py`.
*A "✅" means a test exists in the repository. Run `python -m pytest` yourself to see it pass.*

## OWASP Top 10 (web)

| # | Risk | What Falcon Eye does | Gap / note | Status |
|---|---|---|---|---|
| A01 | Broken access control | Every workspace route checks membership; non-members get 404; roles viewer < member < admin < owner enforced by `require_role`; agent keys and user tokens are separate | Role matrix is tested for main paths, not every endpoint | ✅ |
| A02 | Cryptographic failures | Argon2 password hashes; agent keys and email tokens stored as SHA-256 hashes; HTTPS via Caddy in production; HSTS | Database and backups are not encrypted at rest by Falcon Eye (host/disk job) | ◑ |
| A03 | Injection | SQLAlchemy ORM (parameterised); strict pydantic schemas; rule patterns limited to a safe character set | No raw SQL review tool beyond Bandit | ✅ |
| A04 | Insecure design | Default deny, strictest-rule-wins, compound-action guard, approval flow; firewall evaluated by 63 cases (`docs/EVALUATION.md`) | No formal threat model document yet | ◑ |
| A05 | Security misconfiguration | Production refuses weak/missing secrets, wildcard CORS, EMAIL_LOG_LINKS; API docs can be disabled; security headers on API, nginx and Caddy | `ENABLE_API_DOCS` defaults to true – set false in production | ◑ |
| A06 | Vulnerable components | `pip-audit`, `npm audit`, weekly CI run (`.github/workflows/security.yml`) | Python requirements use `>=` ranges, no lock file | ◑ |
| A07 | Auth failures | Lockout after repeated failures, login/forgot-password rate limits, generic errors, timing-equalised unknown-user check, JWT with expiry + revocation + sign-out-everywhere on reset | **No two-factor login for Falcon Eye accounts**; token kept in browser `localStorage` | ◑ |
| A08 | Integrity failures | Audit log of changes; CI runs tests before merge | Docker images and dependencies are not signed or pinned by hash | ◑ |
| A09 | Logging & monitoring | Every firewall decision + admin change is recorded; secrets never logged | No alerting on repeated failures; logs are not shipped anywhere | ◑ |
| A10 | SSRF | The only outbound request is to the AI provider URL set by the server administrator in `.env`; users cannot supply URLs | Not tested; do not let users configure `LLM_BASE_URL` in future | ✅ by design (no user-supplied URLs) |

## OWASP API Security Top 10

| # | Risk | What Falcon Eye does | Gap | Status |
|---|---|---|---|---|
| API1 | Object-level authorization | Every object lookup is filtered by workspace id | – | ✅ |
| API2 | Broken authentication | See A07; agent keys `fe_live_…` hashed, rotatable, revocable | – | ✅ |
| API3 | Property-level authorization | Explicit response builders; hashes never returned; extra input fields ignored | – | ✅ |
| API4 | Resource consumption | Body size limit, pagination caps, per-agent rate limit, login rate limit, assistant length limits | Limiter is in memory (one backend process only); chunked uploads rely on Caddy's 2 MB limit | ◑ |
| API5 | Function-level authorization | `require_role` on every mutating route | – | ✅ |
| API6 | Sensitive business flows | Password reset and email resend are rate-limited, anti-enumeration | – | 🟡 |
| API7 | SSRF | See A10 | – | ➖ |
| API8 | Misconfiguration | Strict CORS list, no wildcard in production, safe errors, security headers | – | ✅ |
| API9 | Inventory | OpenAPI generated at `/docs`; `docs/API.md` | Disable `/docs` in production | ◑ |
| API10 | Unsafe consumption of APIs | AI provider replies treated as untrusted text and rendered as plain text | – | 🟡 |

## OWASP Top 10 for LLM Applications

Falcon Eye is a **gateway**: it judges an agent's proposed *action*. It does not see the model's
prompt or reply, so several LLM risks can only be handled where the agent itself runs.

| # | Risk | Falcon Eye's position | Status |
|---|---|---|---|
| LLM01 | Prompt injection | Cannot detect injected text in agents it does not see. It limits the damage: a hijacked agent still cannot do anything the policy blocks or holds for approval. The built-in support assistant treats stored records as untrusted data and has no tools. Optional `/v1/verify` adds pattern-based injection signals (not a classifier, will miss novel attacks). | ◑ |
| LLM02 | Sensitive information disclosure | Sensitive file/credential resource rules block secret paths; assistant never receives API keys; secrets are not logged. `/v1/verify` scans agent output and tool arguments for secret patterns and redacts them. | ◑ |
| LLM03 | Supply chain | `pip-audit` / `npm audit`; AI provider is chosen by the admin | ◑ |
| LLM04 | Data / model poisoning | Policy changes versioned and audited. No model training in Falcon Eye. | ◑ |
| LLM05 | Improper output handling | Assistant output rendered as text, never as HTML (no `dangerouslySetInnerHTML`). Agent action names are validated and compound actions need approval. | ✅ |
| LLM06 | Excessive agency | **Core purpose**: default deny, BLOCK / REQUIRE_APPROVAL, sensitive-resource rules, human approval. | ✅ |
| LLM07 | System prompt leakage | The assistant's prompt holds no secrets. Test asks it to reveal keys. | ✅ |
| LLM08 | Vector / embedding weaknesses | No vector database (`retrieval.py` is keyword search over the docs). | ➖ |
| LLM09 | Misinformation / hallucination | Partial. `/v1/verify` compares an agent's output with **evidence the agent supplies** and with Falcon Eye's own records, then flags, holds or blocks. It does not know facts by itself and does not eliminate hallucinations. See `docs/VERIFICATION.md`. | ◑ |
| LLM10 | Unbounded consumption | Agent rate limit, assistant answer-length limit, request caps | ◑ |

## ASVS (reference areas, no level claimed)

| Area | Position |
|---|---|
| V2 Authentication | Strong hashing, lockout, reset flow; **no MFA** |
| V3 Session | Expiring tokens, server-side revocation; token in `localStorage` (XSS would expose it) |
| V4 Access control | Workspace/role checks tested |
| V5 Validation | Schema validation, safe-character rules |
| V7 Errors & logging | Safe errors, audit log |
| V8 Data protection | Secrets hashed; no encryption at rest in-app |
| V13 API | Rate limits, size limits, versioned `/v1` |
| V14 Configuration | Production safety checks, dependency scans |

## Priority fixes still open

1. Turn off `/docs` in production (`ENABLE_API_DOCS=false`).
2. Add two-factor sign-in for Falcon Eye accounts.
3. Move token out of `localStorage` (HttpOnly cookie + CSRF protection) – larger change.
4. Pin Python dependencies with a lock file.
5. Alerting for repeated failed logins / blocked agents.
6. Verification: per-workspace settings, dashboard panel, agent SDK helper, optional semantic (model-based) checker.

## Scan results (local Docker copy)

| Date | Tool | Result |
|---|---|---|
| 2026-11-25 | pytest | 126 passed (21 security tests) |
| 2026-11-25 | pip-audit | No known vulnerabilities |
| 2026-11-25 | npm audit (production) | 0 vulnerabilities |
| 2026-11-25 | Bandit (medium+ severity) | No issues reported |
| 2026-11-25 | OWASP ZAP baseline (passive) | 0 failures, 64 passes; 2 accepted warnings below |

Accepted on purpose:
- **Cacheable content** on `/assets/*`: public, hashed build files meant to be cached (ignored in `.zap/rules.tsv`).
- **CSP `style-src 'unsafe-inline'`**: the React interface uses inline style attributes. Scripts are limited to `'self'`, so injected scripts are still blocked. Removing it means moving inline styles into CSS (future cleanup).

The ZAP baseline is a passive scan. It does not log in or attack the API, so it does not replace a manual penetration test.
