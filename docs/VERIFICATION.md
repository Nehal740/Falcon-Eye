# Output verification (`POST /v1/verify`)

Falcon Eye already decides whether an agent may **act** (`/v1/evaluate`). Verification adds a
second, optional check on what the agent **says or is about to do**: prompt injection signals,
leaked secrets, dangerous tool arguments, claims that the supplied evidence does not support,
and reports that do not match what Falcon Eye recorded.

## What it can and cannot do

| It can | It cannot |
|---|---|
| Compare a statement with **evidence you send** (numbers, identifiers, negations) | Know facts about the world on its own |
| Spot contradictions inside one answer | Prove an answer is true (it only says "supported by your evidence" or not) |
| Check "I did X" against Falcon Eye's own event log | Stop a model from hallucinating, or fix the text |
| Spot injection phrases, secrets, `../`, `; rm`, SQL patterns | Catch every injection or every secret (patterns, not understanding) |
| Hold or block a consequential action | Judge opinions, creative writing or advice (these are not blocked) |

Heuristics produce **false positives and false negatives**. Risk levels come from written rules, not
a probability. Nothing here is "99% accurate"; do not present it that way.

## Request

```json
{
  "text": "The login lockout starts after 5 failed attempts.",
  "kind": "response",
  "evidence": [{"id": "kb1", "text": "Lockout starts after 5 failed attempts.", "source": "docs"}],
  "tool_call": {"action": "send_external_email", "resource": "a@example.org", "arguments": {"to": "a@example.org"}},
  "reported_actions": [{"action": "read_file", "resource": "a.txt"}],
  "known_endpoints": ["/v1/evaluate", "/v1/approvals/{approval_id}"],
  "consequential": false
}
```

Only `text` is required. `kind` is `response`, `tool_call` or `report`. Limits: text 20,000 characters,
20 evidence items of 5,000 characters, 20 reported actions, 4 KB of arguments.

## Risk rules (strongest first)

| Level | When | Decision |
|---|---|---|
| CRITICAL | A consequential output (tool call / report) with a contradicted claim, dangerous arguments, a secret in arguments, injection text next to a tool call, or a report of an action Falcon Eye blocked or never approved | **BLOCK** |
| HIGH | Contradicts the evidence or itself; strong injection signal; secret in text; report of an action Falcon Eye never saw; unknown endpoint | **REQUIRE_APPROVAL** if consequential or a secret; otherwise ALLOW with `flagged: true` |
| MEDIUM | Unsupported checkable claims; unverified links/CVEs/endpoints; weak injection signal; checkable claims but no evidence | ALLOW with `flagged: true` (strict mode + consequential: REQUIRE_APPROVAL) |
| LOW | Nothing found | ALLOW |

If you send a `tool_call`, Falcon Eye **first** applies your normal policy (so `/v1/verify` can replace
`/v1/evaluate` for that call). The final decision is the stricter of the two. Verification can never turn
a BLOCK or REQUIRE_APPROVAL into ALLOW. Held outputs appear in **Approvals** like any other request.

## Response (main fields)

`verification_status` (VERIFIED, PARTIALLY_VERIFIED, NOT_VERIFIED, CONTRADICTED, NO_CHECKABLE_CLAIMS),
`risk_level`, `decision`, `policy_decision`, `flagged`, `requires_human_approval`, `reasons`,
`supported_claims`, `unsupported_claims`, `contradicted_claims`, `evidence_used`, `signals`,
`approval_id`, `redacted_text` (only if a secret was found), `regeneration_hint`, `limitations`.

**Regeneration:** Falcon Eye does not talk to your model. When claims fail it returns a
`regeneration_hint`; your agent may ask its model to rewrite using only the evidence and call `/v1/verify`
again. Keep a retry limit (2 is sensible) in your agent.

## Privacy

The checked text is **not stored**. Falcon Eye keeps only its SHA-256 hash and length, signal names,
counts and the decision (`GET /workspaces/{id}/verifications`). Secrets are never copied into logs or
signal details.

## Python example

```python
import requests
r = requests.post("http://localhost:8080/api/v1/verify",
                  headers={"Authorization": f"Bearer {AGENT_KEY}"},
                  json={"text": answer, "evidence": evidence, "kind": "response"}).json()
if r["decision"] == "BLOCK":
    raise RuntimeError(r["reasons"])
if r["decision"] == "REQUIRE_APPROVAL":
    wait_for_human(r["approval_id"])          # poll GET /v1/approvals/{id}
elif r["flagged"]:
    answer += "\n\n(Some statements could not be verified.)"
```

## Settings

`VERIFY_ENABLED=true|false` (default true) and `VERIFY_SENSITIVITY=standard|strict` (default standard).
These are server-wide for now. Results appear on the dashboard in the **AI Security & Trust** panel (counts only, last 7 days). Per-workspace switches are future work.

## Where this sits in OWASP

LLM01 prompt injection (signals, not full protection), LLM02 sensitive information (secret patterns,
redaction), LLM05 improper output handling (argument checks), LLM06 excessive agency (held/blocked),
LLM09 misinformation (evidence comparison only, **not** hallucination elimination).
See `docs/OWASP_COMPLIANCE_MATRIX.md`.
