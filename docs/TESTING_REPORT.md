# Testing Report

Written honestly: what was run, what was not.

## Run and passing (23 tests)
`python -m pytest` runs `tests/test_policy_engine.py` and `tests/test_helpers.py`: the policy engine (ALLOW / BLOCK / REQUIRE_APPROVAL, priority, strictest-wins, default deny, category-evasion defence, agent scoping), agent key creation and verification, the rate limiter, category inference and documentation retrieval.

Also run: Python syntax check of every backend file, a static type check of the backend (only "package not installed" findings in the build environment), and a syntax parse of every frontend file.

## Written but NOT run yet (2 test files)
`tests/test_api.py` (about 25 tests) and `tests/test_migration.py` need FastAPI and SQLAlchemy, which could not be installed where this was built, so they were skipped. They cover registration, login, lockout, sign-out and refresh, tenant isolation, agent keys (shown once, rotate, revoke, disable), the three decisions and default deny, duplicate `request_id` protection, approvals (decide once, role checks), policy CRUD, history and the tester, events filters, dashboard numbers, the assistant fallback, the audit log, and the upgrade of an old single-user database.

**Please run them first:**
```bash
pip install -r requirements-dev.txt
python -m pytest
```
Expect that a few may need small fixes, since they have never executed.

## Not tested at all
- The frontend in a browser (no `npm install` / build was possible): screens, flows and responsive layout.
- PostgreSQL, Docker builds and `docker compose up`.
- The live LLM assistant (needs your `LLM_API_KEY`).
- Real database upgrade on your own data (back up first).
- Security review or penetration test.
