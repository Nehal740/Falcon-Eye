# AI Agent Integration Guide

**Falcon Eye decides, your agent executes.** Before your agent does something sensitive, it asks Falcon Eye. Falcon Eye replies ALLOW, BLOCK or REQUIRE_APPROVAL. Falcon Eye never performs the action; the response always has `"executed": false`.

## 1. Get an API key
In the dashboard open **Agents → Add agent**, name it, and copy the key (starts with `fe_live_`). It is shown **only once**. Store it in an environment variable, never in source code:
```
export FALCON_EYE_KEY="fe_live_..."
export FALCON_EYE_URL="http://127.0.0.1:8000"
```
If the key leaks, use **Revoke** or **Rotate key** on the agent.

## 2. Test the connection
```bash
curl -H "Authorization: Bearer $FALCON_EYE_KEY" $FALCON_EYE_URL/v1/ping
```
Expected: `{"status":"connected","agent":"<name>","agent_id":"agt_...","workspace":"<name>","agent_enabled":true}`. The dashboard then shows the agent as **Connected** (press **Test connection** on the agent). On Windows PowerShell, use `curl.exe` instead of `curl`.

## 3. Ask for a decision
```bash
curl -X POST $FALCON_EYE_URL/v1/evaluate \
  -H "Authorization: Bearer $FALCON_EYE_KEY" -H "Content-Type: application/json" \
  -d '{"action":"send_external_email","resource":"ceo@example.com","reason":"Weekly report","request_id":"job-123-step-4"}'
```
Response:
```json
{"event_id":"evt_...","decision":"REQUIRE_APPROVAL","message":"A human must approve this action first.",
 "reason":"Policy 'Recommended starter policy' has a rule for category 'external_email' that says require approval.",
 "category":"external_email","policy":{"id":1,"name":"Recommended starter policy"},
 "approval_id":"apr_...","duplicate":false,"executed":false}
```
Fields you send: `action` (required), `resource`, `reason`, `category`, `metadata` (a JSON object, 4 KB at most) and `request_id`.

## 4. Handle each decision
- **ALLOW** – go ahead and perform the action.
- **BLOCK** – do not perform it. Tell the user it is not permitted.
- **REQUIRE_APPROVAL** – wait. Poll `GET /v1/approvals/{approval_id}` until `status` is `APPROVED` (then perform the action) or `REJECTED` / `EXPIRED` (do not).

```bash
curl -H "Authorization: Bearer $FALCON_EYE_KEY" $FALCON_EYE_URL/v1/approvals/APPROVAL_ID
```

## 5. Duplicate protection with request_id
Send a unique `request_id` per logical step. If your agent retries after a network error with the same `request_id`, Falcon Eye returns the original decision with `"duplicate": true` and does not create a second event or approval.

## Python example
```python
import os, time, uuid, httpx

BASE = os.environ["FALCON_EYE_URL"]
HEADERS = {"Authorization": f"Bearer {os.environ['FALCON_EYE_KEY']}"}

def ask(action, resource="", reason=""):
    r = httpx.post(f"{BASE}/v1/evaluate", headers=HEADERS, timeout=10,
                   json={"action": action, "resource": resource, "reason": reason,
                         "request_id": str(uuid.uuid4())})
    r.raise_for_status()
    d = r.json()
    if d["decision"] == "ALLOW":
        return True
    if d["decision"] == "BLOCK":
        return False
    for _ in range(120):                      # wait up to ~10 minutes
        time.sleep(5)
        s = httpx.get(f"{BASE}/v1/approvals/{d['approval_id']}", headers=HEADERS).json()
        if s["status"] != "PENDING":
            return s["status"] == "APPROVED"
    return False                              # still pending: do not act

if ask("send_external_email", "ceo@example.com", "Weekly report"):
    print("send the email here")
```

## Node.js example (Node 18+)
```js
const BASE = process.env.FALCON_EYE_URL;
const headers = { Authorization: `Bearer ${process.env.FALCON_EYE_KEY}`, "Content-Type": "application/json" };

async function ask(action, resource = "", reason = "") {
  const res = await fetch(`${BASE}/v1/evaluate`, {
    method: "POST", headers,
    body: JSON.stringify({ action, resource, reason, request_id: crypto.randomUUID() }),
  });
  if (!res.ok) throw new Error((await res.json()).error?.message ?? res.statusText);
  const d = await res.json();
  if (d.decision === "ALLOW") return true;
  if (d.decision === "BLOCK") return false;
  for (let i = 0; i < 120; i++) {
    await new Promise(r => setTimeout(r, 5000));
    const s = await (await fetch(`${BASE}/v1/approvals/${d.approval_id}`, { headers })).json();
    if (s.status !== "PENDING") return s.status === "APPROVED";
  }
  return false;
}
```

## Errors your agent may see
- `401 agent_key_invalid` – wrong, revoked or rotated key.
- `403 agent_disabled` – the agent is turned off in the dashboard.
- `422 validation_error` – a field is missing or too long (`fields` tells which).
- `429 rate_limited` – slow down; honor the `Retry-After` header.
