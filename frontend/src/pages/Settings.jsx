import { useState } from 'react';
import { LogOut, Trash2, UserPlus } from 'lucide-react';
import { api, friendly, qs, setToken } from '../api';
import { useFetch } from '../hooks';
import { Confirm, ErrorBox, Field, InlineError, Loading, Notice, Pager, ReadOnlyNote, ROLE_LABEL, fmtDate, useToast } from '../components/ui';

function WorkspaceSection({ ctx }) {
  const { ws, canWrite, refreshMe } = ctx;
  const toast = useToast();
  const [name, setName] = useState(ws.name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  async function save(e) {
    e.preventDefault(); setBusy(true); setError(null);
    try { await api.patch(`/workspaces/${ws.id}`, { name: name.trim() }); toast('Workspace renamed.'); refreshMe(); }
    catch (err) { setError(err); } finally { setBusy(false); }
  }
  return (
    <section className="panel settings-sec">
      <div className="panel-head"><div><h2>Workspace</h2><p>Your role: <b>{ROLE_LABEL[ws.role] || ws.role}</b></p></div></div>
      <form className="stack" onSubmit={save}>
        <Field label="Workspace name" htmlFor="s-ws" error={error ? friendly(error).fields?.name : null}>
          <input id="s-ws" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} disabled={!canWrite} />
        </Field>
        {canWrite && <div className="btn-row"><button className="primary-btn" disabled={busy || name.trim().length < 2 || name.trim() === ws.name}>Save name</button></div>}
        <InlineError error={error} />
      </form>
    </section>
  );
}

function MembersSection({ ctx }) {
  const { ws, canWrite, me } = ctx;
  const toast = useToast();
  const { data, error, loading, reload } = useFetch(() => api.get(`/workspaces/${ws.id}/members`), [ws.id]);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('viewer');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [remove, setRemove] = useState(null);
  const items = (data && data.items) || [];

  async function add(e) {
    e.preventDefault(); setBusy(true); setErr(null);
    try { await api.post(`/workspaces/${ws.id}/members`, { email: email.trim(), role }); toast('Member added.'); setEmail(''); reload(); }
    catch (x) { setErr(x); } finally { setBusy(false); }
  }
  async function changeRole(m, r) {
    try { await api.patch(`/workspaces/${ws.id}/members/${m.user_id}`, { role: r }); toast('Role updated.'); reload(); }
    catch (x) { toast(friendly(x).message, 'error'); reload(); }
  }
  async function doRemove() {
    setBusy(true); setErr(null);
    try { await api.del(`/workspaces/${ws.id}/members/${remove.user_id}`); toast('Member removed.'); setRemove(null); reload(); }
    catch (x) { setErr(x); } finally { setBusy(false); }
  }
  return (
    <section className="panel settings-sec">
      <div className="panel-head"><div><h2>Members</h2><p>People who can use this workspace.</p></div></div>
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? <Loading /> : (
        <div className="table-scroll"><table>
          <thead><tr><th>NAME</th><th>EMAIL</th><th>ROLE</th><th>JOINED</th><th /></tr></thead>
          <tbody>{items.map((m) => (
            <tr key={m.user_id}>
              <td>{m.full_name}{me.id === m.user_id && <em className="off-tag">you</em>}</td>
              <td>{m.email}</td>
              <td>{m.role === 'owner' || ws.role !== 'owner'
                ? ROLE_LABEL[m.role] || m.role
                : <select aria-label={`Role of ${m.full_name}`} value={m.role} onChange={(e) => changeRole(m, e.target.value)}><option value="admin">Admin</option><option value="member">Member (can review approvals)</option><option value="viewer">Viewer (read-only)</option></select>}</td>
              <td className="muted-cell">{fmtDate(m.joined_at)}</td>
              <td className="row-actions">{canWrite && m.role !== 'owner' && <button className="icon-btn" aria-label={`Remove ${m.full_name}`} onClick={() => { setRemove(m); setErr(null); }}><Trash2 size={16} /></button>}</td>
            </tr>))}</tbody>
        </table></div>
      )}
      {canWrite ? (
        <form className="stack add-member" onSubmit={add}>
          <h3 className="mini-title"><UserPlus size={14} /> Add a member</h3>
          <div className="row-fields">
            <Field label="Their email" htmlFor="m-e" hint="They must already have a Falcon Eye account."><input id="m-e" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
            <Field label="Role" htmlFor="m-r"><select id="m-r" value={role} onChange={(e) => setRole(e.target.value)}><option value="viewer">Viewer (read-only)</option><option value="member">Member (can review approvals)</option>{ws.role === 'owner' && <option value="admin">Admin</option>}</select></Field>
            <button className="primary-btn" disabled={busy || !email.trim()}>Add</button>
          </div>
          <InlineError error={err && !remove ? err : null} />
        </form>
      ) : <ReadOnlyNote canWrite={false} />}
      {remove && <Confirm title="Remove this member?" danger confirmLabel="Remove" busy={busy} error={err} onConfirm={doRemove} onClose={() => setRemove(null)}>
        <p><b>{remove.full_name}</b> will lose access to this workspace right away.</p></Confirm>}
    </section>
  );
}

function PasswordSection({ ctx }) {
  const toast = useToast();
  const [cur, setCur] = useState('');
  const [nw, setNw] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  async function save(e) {
    e.preventDefault(); setError(null);
    if (nw.length < 10) { setError({ message: 'The new password needs at least 10 characters.', hint: 'Try a short sentence.' }); return; }
    setBusy(true);
    try {
      const d = await api.post('/auth/change-password', { current_password: cur, new_password: nw });
      if (d && d.access_token) setToken(d.access_token);
      toast('Password changed. Other devices were signed out.'); setCur(''); setNw('');
    } catch (x) { setError(friendly(x)); } finally { setBusy(false); }
  }
  const f = error && error.fields;
  return (
    <section className="panel settings-sec">
      <div className="panel-head"><div><h2>Your account</h2><p>{ctx.me.full_name} · {ctx.me.email}</p></div></div>
      <form className="stack" onSubmit={save}>
        <div className="row-fields">
          <Field label="Current password" htmlFor="p-c" error={f && f.current_password}><input id="p-c" type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} required /></Field>
          <Field label="New password" htmlFor="p-n" hint="At least 10 characters." error={f && f.new_password}><input id="p-n" type="password" autoComplete="new-password" value={nw} onChange={(e) => setNw(e.target.value)} required /></Field>
          <button className="primary-btn" disabled={busy || !cur || !nw}>Change password</button>
        </div>
        {error && <div className="inline-error" role="alert"><b>{error.message}</b><span>{error.hint}</span></div>}
      </form>
      <div className="btn-row"><button className="ghost-btn" onClick={ctx.onLogout}><LogOut size={14} /> Sign out</button></div>
    </section>
  );
}

const LIMIT = 20;
function AuditSection({ ctx }) {
  const { ws } = ctx;
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useFetch(() => api.get(`/workspaces/${ws.id}/audit-logs${qs({ limit: LIMIT, offset })}`), [ws.id, offset]);
  const items = (data && data.items) || [];
  return (
    <section className="panel settings-sec">
      <div className="panel-head"><div><h2>Audit log</h2><p>Who changed what in this workspace. Secrets are never logged.</p></div></div>
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? <Loading /> : items.length === 0 ? <p className="muted-cell">Nothing recorded yet.</p> : (
        <div className="table-scroll"><table>
          <thead><tr><th>WHEN</th><th>WHO</th><th>WHAT</th><th>TARGET</th></tr></thead>
          <tbody>{items.map((a) => (
            <tr key={a.id}><td className="muted-cell">{fmtDate(a.created_at)}</td><td>{a.actor || 'System'}</td><td className="mono">{a.action}</td><td className="resource">{a.target_type ? `${a.target_type} ${a.target_id || ''}` : '—'}</td></tr>))}</tbody>
        </table></div>
      )}
      <Pager total={(data && data.total) || 0} offset={offset} limit={LIMIT} onChange={setOffset} />
    </section>
  );
}

function AiSection({ ctx }) {
  const { ws } = ctx;
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  async function run() {
    setBusy(true); setErr(null); setRes(null);
    try { setRes(await api.get(`/workspaces/${ws.id}/assistant/diagnose`)); }
    catch (x) { setErr(x); } finally { setBusy(false); }
  }
  return (
    <section className="panel settings-sec">
      <div className="panel-head"><div><h2>AI assistant</h2><p>Check that the live AI model is connected and answering.</p></div></div>
      <div className="stack">
        <div className="btn-row"><button className="primary-btn" onClick={run} disabled={busy}>{busy ? 'Testing…' : 'Test AI connection'}</button></div>
        <InlineError error={err} />
        {res && (
          <>
            <Notice tone={res.ok ? 'ok' : 'warn'}>
              <b>{res.ok ? 'Connected.' : 'Not working yet.'}</b> {res.next_step}
              {res.test && !res.test.ok && <div>Reason: {res.test.message}{res.test.detail ? ` — the provider says: “${res.test.detail}”` : ''}</div>}
              {res.test && res.test.ok && <div>Test answer: “{res.test.sample}”</div>}
            </Notice>
            <ul className="notes">
              <li>Provider: <span className="mono">{res.provider}</span> · Model in use: <span className="mono">{res.model}</span></li>
              {res.list_error && <li>Model list: could not load ({res.list_error})</li>}
              {res.models.length > 0 && <li>Models your key can use: <span className="mono">{res.models.join(', ')}</span></li>}
              {res.suggested_model && !res.ok && <li>Suggested setting: <span className="mono">LLM_MODEL={res.suggested_model}</span></li>}
            </ul>
            <small>Settings live in the server’s <span className="mono">.env</span> file (see docs/AI_ASSISTANT.md). The key is never shown here.</small>
          </>
        )}
      </div>
    </section>
  );
}

export default function Settings({ ctx }) {
  return (
    <div className="settings-grid">
      <WorkspaceSection ctx={ctx} />
      <MembersSection ctx={ctx} />
      <PasswordSection ctx={ctx} />
      {ctx.canWrite && <AiSection ctx={ctx} />}
      {ctx.canWrite && <AuditSection ctx={ctx} />}
      <section className="panel settings-sec">
        <div className="panel-head"><div><h2>Security notes</h2><p>How Falcon Eye protects your workspace</p></div></div>
        <ul className="notes">
          <li>Passwords are stored as one-way hashes. Sign-in attempts are rate-limited.</li>
          <li>Your session expires automatically and is renewed while you work. Signing out ends every session.</li>
          <li>Agent keys are shown once and stored only as hashes. Revoke a key at once if you think it leaked.</li>
          <li>Each workspace is isolated: members of other workspaces cannot see your data.</li>
          <li>Falcon Eye decides and records. It never performs an agent’s action itself.</li>
          <li>The session token is kept in this browser’s local storage. Sign out on shared computers.</li>
        </ul>
      </section>
    </div>
  );
}
