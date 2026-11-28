# Known Limitations and Future Improvements

Read these before relying on Falcon Eye:

- **Not independently security tested.** It follows secure practices, but it has not had a penetration test or formal review.
- **Rate limiting is in memory.** Counters live in one backend process. Run a single worker (the Docker image does) or put a gateway or Redis in front. Account lockout is stored in the database and is shared.
- **Login token in browser storage.** The web app keeps its token in localStorage, which a malicious script could read if a cross-site-scripting flaw ever existed. Tokens expire after `ACCESS_TOKEN_MINUTES` (60 by default) and are renewed while you work. Sign out on shared computers.
- **No email.** There are no invitations or password reset emails: people can only be added if they already have an account.
- **No SSO or two-factor authentication.**
- **No workspace deletion.** You can rename a workspace; deleting one is not supported yet.
- **Falcon Eye does not execute actions.** Agents must ask first and obey the answer. An agent that never asks cannot be stopped by Falcon Eye alone.
- **Category inference is name-based.** Unusual action names become `other`; write rules with action name patterns for those.
- **The assistant needs an LLM key** for generated answers. Otherwise it shows documentation passages. Its answers can be wrong; check important settings yourself.
- **Automatic database upgrades.** They run when the backend starts and have only been tested with unit tests on SQLite-compatible SQL. Back up your database before upgrading a real installation. There is no built-in backup, high availability or data retention tooling.
- **Tests.** See the testing notes in the project README for what has and has not been run.

Ideas for later: Redis rate limiting, email invitations and password reset, two-factor authentication, notifications and webhooks, execution integrations, policy import and export, workspace deletion.

- **Email is optional and unconfirmed addresses can still sign in.** Without SMTP settings, password reset by email is unavailable (an administrator would have to reset the account in the database). See `docs/EMAIL.md`.


## Output verification

Verification is heuristic. It checks text against evidence the agent supplies; it cannot know facts itself, will miss novel injection wording, and can flag correct text. Settings are server-wide. See `docs/VERIFICATION.md`.
