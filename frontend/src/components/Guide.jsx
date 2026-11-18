import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Loader2, XCircle } from 'lucide-react';
import { api, friendly } from '../api';
import { CodeBlock, CopyButton, Field, Notice, fmtDate } from './ui';

export function defaultBaseUrl() {
  const { protocol, hostname, port, origin } = window.location;
  if (port === '5173' || port === '4173') return `${protocol}//${hostname}:8000`;
  return `${origin}/api`;
}

export function KeyReveal({ apiKey, confirmed, onConfirm }) {
  return (
    <div className="key-reveal">
      <Notice tone="warn" icon={AlertTriangle}>
        <b>Copy this key now.</b> It is shown only once and Falcon Eye cannot show it again. If you lose it, rotate the key to get a new one.
      </Notice>
      <div className="key-box">
        <code aria-label="Agent API key">{apiKey}</code>
        <CopyButton text={apiKey} label="Copy key" />
      </div>
      {onConfirm && (
        <label className="check-row">
          <input type="checkbox" checked={confirmed} onChange={(e) => onConfirm(e.target.checked)} />
          I have saved this key somewhere safe.
        </label>
      )}
    </div>
  );
}

export function IntegrationGuide({ apiKey }) {
  const [base, setBase] = useState(defaultBaseUrl);
  const key = apiKey || 'YOUR_AGENT_KEY';
  const root = base.replace(/\/+$/, '');
  const curl = `curl -X POST ${root}/v1/evaluate \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{"action": "send_external_email",
       "resource": "client@example.com",
       "reason": "Send the weekly report",
       "request_id": "weekly-report-001"}'`;
  const py = `import requests

BASE = "${root}"
KEY = "${key}"   # keep this in an environment variable, not in code

def ask_firewall(action, resource="", reason="", request_id=None):
    r = requests.post(
        f"{BASE}/v1/evaluate",
        headers={"Authorization": f"Bearer {KEY}"},
        json={"action": action, "resource": resource,
              "reason": reason, "request_id": request_id},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()

result = ask_firewall("send_external_email", "client@example.com", "Weekly report")
if result["decision"] == "ALLOW":
    pass  # your agent performs the action itself
elif result["decision"] == "REQUIRE_APPROVAL":
    print("Waiting for a human. Approval id:", result["approval_id"])
    # poll GET {BASE}/v1/approvals/<approval_id> until status is APPROVED or REJECTED
else:
    print("Blocked:", result["reason"])`;
  const ping = `curl ${root}/v1/ping -H "Authorization: Bearer ${key}"`;
  return (
    <div className="stack">
      <ol className="steps-list">
        <li>Keep the agent key in a secret store or environment variable.</li>
        <li>Before your agent does anything sensitive, send the action to Falcon Eye.</li>
        <li>Do what the answer says: <b>ALLOW</b> go ahead, <b>BLOCK</b> stop, <b>REQUIRE_APPROVAL</b> wait for a human decision.</li>
      </ol>
      <Field label="Falcon Eye server address" htmlFor="base-url" hint="Where your backend is reachable from the agent. The default works for local development.">
        <input id="base-url" value={base} onChange={(e) => setBase(e.target.value)} spellCheck={false} />
      </Field>
      <CodeBlock label="1 · Check the connection (curl)" code={ping} />
      <CodeBlock label="2 · Send an action (curl)" code={curl} />
      <CodeBlock label="3 · Or use Python" code={py} />
      <p className="soft-note">Falcon Eye only decides. Your agent still has to perform (or skip) the action itself.</p>
    </div>
  );
}

// Polls the real test-connection endpoint until the agent has called the API.
export function ConnectionTest({ wid, agentId, auto = true, onResult }) {
  const [state, setState] = useState({ status: 'idle', data: null, error: null });
  async function run() {
    setState((s) => ({ ...s, status: 'checking' }));
    try {
      const data = await api.post(`/workspaces/${wid}/agents/${agentId}/test-connection`);
      setState({ status: data.status, data, error: null });
      if (onResult) onResult(data);
    } catch (e) {
      setState({ status: 'error', data: null, error: e });
    }
  }
  useEffect(() => {
    if (!auto) return undefined;
    run();
    const t = setInterval(() => {
      if (!document.hidden && state.status !== 'connected') run();
    }, 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line
  }, [wid, agentId, auto, state.status === 'connected']);

  const { status, data, error } = state;
  return (
    <div className={`conn-test ${status}`}>
      <div className="conn-line">
        {status === 'connected' && <CheckCircle2 size={22} />}
        {status === 'failed' && <XCircle size={22} />}
        {(status === 'checking' || status === 'idle') && <Loader2 size={22} className="spin" />}
        {status === 'error' && <XCircle size={22} />}
        <div>
          <b>{status === 'connected' ? 'Connected' : status === 'failed' ? 'Not connected yet' : status === 'error' ? 'Could not run the test' : 'Checking…'}</b>
          {data && <p>{data.message}{data.last_seen_at ? ` Last seen ${fmtDate(data.last_seen_at)}.` : ''}</p>}
          {status === 'failed' && data && data.hint && <p>{data.hint}</p>}
          {status === 'error' && <p>{friendly(error).message} {friendly(error).hint}</p>}
        </div>
      </div>
      <button className="ghost-btn" onClick={run} disabled={status === 'checking'}>Test connection</button>
    </div>
  );
}
