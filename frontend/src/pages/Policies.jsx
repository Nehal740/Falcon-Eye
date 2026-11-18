import { useState } from 'react';
import { FlaskConical, History, Pencil, Plus, SlidersHorizontal, Trash2, X } from 'lucide-react';
import { api, friendly } from '../api';
import { useFetch } from '../hooks';
import {
  Confirm, Dialog, Empty, ErrorBox, Field, InlineError, Loading, Notice, ReadOnlyNote, Status, fmtDate, useToast,
} from '../components/ui';
import { catLabel } from '../components/EventParts';

const EFFECTS = [['ALLOW', 'Allow'], ['REQUIRE_APPROVAL', 'Ask a human first'], ['BLOCK', 'Block']];
const blankRule = () => ({ effect: 'REQUIRE_APPROVAL', target_type: 'category', target_value: '', resource_pattern: '' });
const fromServerRule = (r) => ({ effect: r.effect, target_type: r.target_type, target_value: r.target_value, resource_pattern: r.resource_pattern === '*' ? '' : r.resource_pattern });

function describeRule(r, categories) {
  const value = r.target_value.trim();
  if (!value) return 'Choose an action type or type an action name.';
  const parts = [r.target_type === 'category' ? `the action type is “${catLabel(categories, value)}”` : `the action name matches “${value}”`];
  if (r.resource_pattern.trim()) parts.push(`the resource matches “${r.resource_pattern.trim()}”`);
  const verb = { ALLOW: 'ALLOW', BLOCK: 'BLOCK', REQUIRE_APPROVAL: 'ASK A HUMAN' }[r.effect];
  return `${verb} when ${parts.join(' and ')}.`;
}

/* ---------- Builder ---------- */
function PolicyBuilder({ ws, categories, agents, policy, onClose, onSaved }) {
  const toast = useToast();
  const editing = !!policy;
  const [form, setForm] = useState(() => policy ? {
    name: policy.name, description: policy.description || '', enabled: policy.enabled, priority: policy.priority,
    agent_id: policy.agent_id || '',
    rules: policy.rules.map(fromServerRule),
  } : { name: '', description: '', enabled: true, priority: 100, agent_id: '', rules: [blankRule()] });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const templates = useFetch(() => (editing ? Promise.resolve(null) : api.get('/policy-templates')), []);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const setRule = (i, patch) => setForm((f) => ({ ...f, rules: f.rules.map((r, j) => (j === i ? { ...r, ...patch } : r)) }));
  const rulesOk = form.rules.length > 0 && form.rules.every((r) => r.target_value.trim());

  function applyTemplate(t) {
    set({ name: form.name || t.name, description: form.description || t.description,
      rules: t.rules.map(fromServerRule) });
  }

  async function save() {
    setBusy(true); setError(null);
    const body = {
      name: form.name.trim(), description: form.description.trim(), enabled: form.enabled,
      priority: Number(form.priority) || 100, agent_id: form.agent_id ? Number(form.agent_id) : null,
      assign_to_all_agents: !form.agent_id,
      rules: form.rules.map((r) => ({ effect: r.effect, target_type: r.target_type, target_value: r.target_value.trim(), resource_pattern: r.resource_pattern.trim() || '*' })),
    };
    try {
      if (editing) await api.patch(`/workspaces/${ws.id}/policies/${policy.id}`, body);
      else await api.post(`/workspaces/${ws.id}/policies`, body);
      toast(editing ? 'Policy saved.' : 'Policy created.');
      onSaved();
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  const fields = error ? (friendly(error).fields || {}) : {};

  return (
    <Dialog title={editing ? 'Edit policy' : 'New policy'} subtitle="If rules disagree, the stricter one wins: Block beats Ask a human, which beats Allow." onClose={onClose} wide
      footer={<><button className="ghost-btn" onClick={onClose} disabled={busy}>Cancel</button>
        <button className="primary-btn big" disabled={busy || form.name.trim().length < 2 || !rulesOk} onClick={save}>{busy ? 'Saving…' : 'Save policy'}</button></>}>
      <div className="stack">
        {!editing && templates.data && templates.data.items.length > 0 && (
          <div>
            <h3 className="mini-title">Start from a template</h3>
            <div className="chips">{templates.data.items.map((t) => <button key={t.key} className="chip" title={t.description} onClick={() => applyTemplate(t)}>{t.name}</button>)}</div>
          </div>
        )}
        <Field label="Policy name" htmlFor="po-n" error={fields.name}><input id="po-n" value={form.name} maxLength={100} onChange={(e) => set({ name: e.target.value })} /></Field>
        <Field label="Description (optional)" htmlFor="po-d"><input id="po-d" value={form.description} maxLength={300} onChange={(e) => set({ description: e.target.value })} /></Field>
        <div className="row-fields">
          <Field label="Applies to" htmlFor="po-a" hint="One agent or all agents.">
            <select id="po-a" value={form.agent_id} onChange={(e) => set({ agent_id: e.target.value })}>
              <option value="">All agents in this workspace</option>
              {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </Field>
          <Field label="Priority (1 = checked first)" htmlFor="po-p" error={fields.priority}>
            <input id="po-p" type="number" min={1} max={1000} value={form.priority} onChange={(e) => set({ priority: e.target.value })} />
          </Field>
        </div>
        <label className="check-row"><input type="checkbox" checked={form.enabled} onChange={(e) => set({ enabled: e.target.checked })} /> Policy is turned on</label>

        <h3 className="mini-title">Rules</h3>
        <Notice>Anything that no rule matches is <b>blocked</b>. Use <span className="mono">*</span> to match anything, e.g. <span className="mono">delete_*</span> or <span className="mono">/finance/*</span>. Matching ignores upper/lower case.</Notice>
        {form.rules.map((r, i) => (
          <div className="rule-row" key={i}>
            <div className="rule-head">
              <b>Rule {i + 1}</b>
              <div className="rule-tools">
                <button className="icon-btn" onClick={() => set({ rules: form.rules.filter((_, j) => j !== i) })} disabled={form.rules.length === 1} aria-label="Remove rule"><X size={15} /></button>
              </div>
            </div>
            <div className="rule-grid">
              <Field label="Then" htmlFor={`r-e-${i}`}>
                <select id={`r-e-${i}`} value={r.effect} onChange={(e) => setRule(i, { effect: e.target.value })}>{EFFECTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
              </Field>
              <Field label="When the action" htmlFor={`r-t-${i}`}>
                <select id={`r-t-${i}`} value={r.target_type} onChange={(e) => setRule(i, { target_type: e.target.value, target_value: '' })}>
                  <option value="category">is of this type</option>
                  <option value="action">has a name matching</option>
                </select>
              </Field>
              {r.target_type === 'category' ? (
                <Field label="Action type" htmlFor={`r-c-${i}`}>
                  <select id={`r-c-${i}`} value={r.target_value} onChange={(e) => setRule(i, { target_value: e.target.value })}>
                    <option value="">Choose a type…</option>
                    {categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                  </select>
                </Field>
              ) : (
                <Field label="Action name" htmlFor={`r-a-${i}`}><input id={`r-a-${i}`} placeholder="e.g. delete_*" maxLength={100} value={r.target_value} onChange={(e) => setRule(i, { target_value: e.target.value })} /></Field>
              )}
              <Field label="and the resource matches (optional)" htmlFor={`r-r-${i}`}><input id={`r-r-${i}`} placeholder="e.g. /finance/*" maxLength={200} value={r.resource_pattern} onChange={(e) => setRule(i, { resource_pattern: e.target.value })} /></Field>
            </div>
            <p className="rule-sentence"><Status value={r.effect} /> {describeRule(r, categories)}</p>
          </div>
        ))}
        <button className="ghost-btn" onClick={() => set({ rules: [...form.rules, blankRule()] })}><Plus size={14} /> Add a rule</button>
        <InlineError error={error} />
      </div>
    </Dialog>
  );
}

/* ---------- History ---------- */
function HistoryDrawer({ ws, policy, onClose }) {
  const { data, error, loading } = useFetch(() => api.get(`/workspaces/${ws.id}/policies/${policy.id}/history`), [policy.id]);
  return (
    <Dialog side title="Policy history" subtitle={policy.name} onClose={onClose}>
      {loading && !data && <Loading />}
      <ErrorBox error={error} />
      {data && (data.items.length === 0 ? <Empty icon={History} title="No history" text="Changes to this policy will be listed here." /> : (
        <ol className="timeline">
          {data.items.map((h) => (
            <li key={h.version}>
              <b>Version {h.version} · {String(h.change_type).replaceAll('_', ' ')}</b>
              <span>{h.changed_by || 'Unknown'} · {fmtDate(h.created_at)}</span>
              <details><summary>See what it looked like</summary><pre className="json-box">{JSON.stringify(h.snapshot, null, 2)}</pre></details>
            </li>
          ))}
        </ol>
      ))}
    </Dialog>
  );
}

/* ---------- Tester ---------- */
function Tester({ ws, agents, categories }) {
  const [agent, setAgent] = useState('');
  const [action, setAction] = useState('send_external_email');
  const [resource, setResource] = useState('');
  const [res, setRes] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const chosen = agent || (agents[0] && String(agents[0].id)) || '';
  async function run() {
    setBusy(true); setError(null);
    try { setRes(await api.post(`/workspaces/${ws.id}/policies/simulate`, { agent_id: chosen ? Number(chosen) : null, action: action.trim(), resource: resource.trim() })); }
    catch (e) { setError(e); setRes(null); } finally { setBusy(false); }
  }
  return (
    <section className="panel">
      <div className="panel-head"><div><h2><FlaskConical size={16} /> Policy tester</h2><p>See what the firewall would decide. Nothing is recorded and nothing runs.</p></div></div>
      {agents.length === 0 ? <Notice>Add an agent first, then you can test it here.</Notice> : (
        <div className="stack">
          <div className="rule-grid">
            <Field label="Agent" htmlFor="t-a"><select id="t-a" value={chosen} onChange={(e) => setAgent(e.target.value)}>{agents.map((a) => <option key={a.id} value={String(a.id)}>{a.name}</option>)}</select></Field>
            <Field label="Action" htmlFor="t-n"><input id="t-n" value={action} onChange={(e) => setAction(e.target.value)} /></Field>
            <Field label="Resource (optional)" htmlFor="t-r"><input id="t-r" value={resource} onChange={(e) => setResource(e.target.value)} placeholder="e.g. client@example.com" /></Field>
            <div className="fld"><label>&nbsp;</label><button className="primary-btn" onClick={run} disabled={busy || !action.trim()}>Test</button></div>
          </div>
          <InlineError error={error} />
          {res && (
            <div className="sim-result">
              <Status value={res.decision} />
              <p>{res.reason}</p>
              <small>Action type: {catLabel(categories, res.category)} · Policy: {res.policy_name || 'none matched (workspace default applies)'}</small>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

/* ---------- Page ---------- */
export default function Policies({ ctx }) {
  const { ws, canWrite, categories } = ctx;
  const toast = useToast();
  const { data, error, loading, reload } = useFetch(() => api.get(`/workspaces/${ws.id}/policies`), [ws.id]);
  const agentsQ = useFetch(() => api.get(`/workspaces/${ws.id}/agents`), [ws.id]);
  const [builder, setBuilder] = useState(null); // {policy|null}
  const [history, setHistory] = useState(null);
  const [del, setDel] = useState(null);
  const [busy, setBusy] = useState(false);
  const [delErr, setDelErr] = useState(null);
  const items = (data && data.items) || [];
  const agents = (agentsQ.data && agentsQ.data.items) || [];

  async function toggle(p) {
    try { await api.patch(`/workspaces/${ws.id}/policies/${p.id}`, { enabled: !p.enabled }); toast(p.enabled ? 'Policy turned off.' : 'Policy turned on.'); reload(); }
    catch (e) { toast(friendly(e).message, 'error'); }
  }
  async function remove() {
    setBusy(true); setDelErr(null);
    try { await api.del(`/workspaces/${ws.id}/policies/${del.id}`); toast('Policy deleted.'); setDel(null); reload(); }
    catch (e) { setDelErr(e); } finally { setBusy(false); }
  }

  return (
    <>
      <section className="panel full-panel">
        <div className="panel-head">
          <div><h2>Security policies</h2><p>Your rules for what agents may do. Lower priority numbers are checked first.</p></div>
          {canWrite && <button className="primary-btn" onClick={() => setBuilder({ policy: null })}><Plus size={15} /> New policy</button>}
        </div>
        <ReadOnlyNote canWrite={canWrite} />
        <ErrorBox error={error} onRetry={reload} />
        {loading && !data ? <Loading /> : items.length === 0 ? (
          <Empty icon={SlidersHorizontal} title="No policies yet" text="Until you add a policy, Falcon Eye blocks every action. Start with a template to get going quickly.">
            {canWrite && <button className="primary-btn" onClick={() => setBuilder({ policy: null })}><Plus size={15} /> Create a policy</button>}
          </Empty>
        ) : (
          <div className="table-scroll">
            <table>
              <thead><tr><th>ON</th><th>POLICY</th><th>APPLIES TO</th><th>PRIORITY</th><th>RULES</th><th>UPDATED</th><th /></tr></thead>
              <tbody>
                {items.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <button role="switch" aria-checked={p.enabled} aria-label={`${p.name} is ${p.enabled ? 'on' : 'off'}`} className={`switch ${p.enabled ? 'on' : ''}`} disabled={!canWrite} onClick={() => toggle(p)}><i /></button>
                    </td>
                    <td><b>{p.name}</b><div className="muted-cell">{p.description}</div></td>
                    <td>{p.agent_id ? (p.agent_name || p.agent_id) : 'All agents'}</td>
                    <td>{p.priority}</td>
                    <td>{p.rules.length}</td>
                    <td className="muted-cell">v{p.version} · {fmtDate(p.updated_at)}</td>
                    <td className="row-actions">
                      <button className="icon-btn" title="History" aria-label={`History of ${p.name}`} onClick={() => setHistory(p)}><History size={16} /></button>
                      {canWrite && <button className="icon-btn" title="Edit" aria-label={`Edit ${p.name}`} onClick={() => setBuilder({ policy: p })}><Pencil size={16} /></button>}
                      {canWrite && <button className="icon-btn" title="Delete" aria-label={`Delete ${p.name}`} onClick={() => { setDel(p); setDelErr(null); }}><Trash2 size={16} /></button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <Tester ws={ws} agents={agents} categories={categories} />
      {builder && <PolicyBuilder ws={ws} categories={categories} agents={agents} policy={builder.policy} onClose={() => setBuilder(null)} onSaved={() => { setBuilder(null); reload(); }} />}
      {history && <HistoryDrawer ws={ws} policy={history} onClose={() => setHistory(null)} />}
      {del && <Confirm title="Delete this policy?" danger confirmLabel="Delete policy" busy={busy} error={delErr} onConfirm={remove} onClose={() => setDel(null)}>
        <p><b>{del.name}</b> will stop applying immediately. Actions it used to allow may become blocked.</p></Confirm>}
    </>
  );
}
