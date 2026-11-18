import { useState } from 'react';
import { Bot, KeyRound, Pencil, Plus, Power, Trash2, ShieldOff } from 'lucide-react';
import { api, friendly, qs } from '../api';
import { useFetch } from '../hooks';
import {
  ConnBadge, Confirm, Dialog, Empty, ErrorBox, Field, InlineError, Loading, Notice, ReadOnlyNote,
  fmtDate, timeAgo, useToast,
} from '../components/ui';
import { ConnectionTest, IntegrationGuide, KeyReveal } from '../components/Guide';
import { EventTable } from '../components/EventParts';

/* ---------- Add agent wizard ---------- */
function AddAgentWizard({ ws, onClose, onCreated }) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [created, setCreated] = useState(null); // {agent, api_key}
  const [saved, setSaved] = useState(false);
  const labels = ['Details', 'Your key', 'Connect', 'Test'];
  const fields = error ? (friendly(error).fields || {}) : {};

  async function create() {
    setBusy(true); setError(null);
    try {
      const d = await api.post(`/workspaces/${ws.id}/agents`, { name: name.trim(), description: desc.trim() });
      setCreated(d); setStep(1); onCreated();
    } catch (e) { setError(e); } finally { setBusy(false); }
  }

  const footer = (
    <>
      {step === 0 && <button className="ghost-btn" onClick={onClose}>Cancel</button>}
      {step === 0 && <button className="primary-btn big" disabled={busy || name.trim().length < 2} onClick={create}>{busy ? 'Creating…' : 'Create agent'}</button>}
      {step === 1 && <button className="primary-btn big" disabled={!saved} onClick={() => setStep(2)}>Next: connect</button>}
      {step === 2 && <><button className="ghost-btn" onClick={() => setStep(1)}>Back</button><button className="primary-btn big" onClick={() => setStep(3)}>Next: test</button></>}
      {step === 3 && <><button className="ghost-btn" onClick={() => setStep(2)}>Back</button><button className="primary-btn big" onClick={onClose}>Done</button></>}
    </>
  );

  return (
    <Dialog title="Add an AI agent" subtitle={`Step ${step + 1} of 4 · ${labels[step]}`} onClose={step === 1 && !saved ? () => {} : onClose} wide footer={footer}>
      <div className="progress" aria-hidden="true">{labels.map((l, i) => <i key={l} className={i <= step ? 'on' : ''} />)}</div>
      {step === 0 && (
        <div className="stack">
          <p>Give your agent a name you will recognise. You get a secret key in the next step.</p>
          <Field label="Agent name" htmlFor="ag-name" hint="For example: Billing assistant" error={fields.name}>
            <input id="ag-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} autoFocus />
          </Field>
          <Field label="Description (optional)" htmlFor="ag-desc" hint="What it does and where it runs." error={fields.description}>
            <textarea id="ag-desc" rows={3} value={desc} onChange={(e) => setDesc(e.target.value)} maxLength={300} />
          </Field>
          <InlineError error={error} />
        </div>
      )}
      {step === 1 && created && (
        <div className="stack">
          <Notice tone="ok">Agent <b>{created.agent.name}</b> was created. Its ID is <span className="mono">{created.agent.agent_id}</span>.</Notice>
          <KeyReveal apiKey={created.api_key} confirmed={saved} onConfirm={setSaved} />
        </div>
      )}
      {step === 2 && created && <IntegrationGuide apiKey={created.api_key} />}
      {step === 3 && created && (
        <div className="stack">
          <p>Run the first command from the previous step (or let your agent send a request). This page checks automatically every few seconds.</p>
          <ConnectionTest wid={ws.id} agentId={created.agent.id} />
          <p className="soft-note">You can finish now. The agent will show “Connected” on the Agents page once it calls Falcon Eye.</p>
        </div>
      )}
    </Dialog>
  );
}

/* ---------- Agent detail ---------- */
function AgentDetail({ ws, canWrite, agentId, categories, onClose, onChanged, onDeleted }) {
  const toast = useToast();
  const { data: agent, error, reload } = useFetch(() => api.get(`/workspaces/${ws.id}/agents/${agentId}`), [agentId], { interval: 10000 });
  const publicId = agent ? agent.agent_id : null;
  const events = useFetch(() => (publicId ? api.get(`/workspaces/${ws.id}/events${qs({ agent_id: publicId, limit: 8 })}`) : Promise.resolve({ items: [] })), [publicId], { interval: 10000 });
  const [edit, setEdit] = useState(null);
  const [confirm, setConfirm] = useState(null); // 'rotate' | 'revoke' | 'delete' | 'toggle'
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [newKey, setNewKey] = useState(null);
  const [keySaved, setKeySaved] = useState(false);
  const [showGuide, setShowGuide] = useState(false);

  async function act(fn, okMsg) {
    setBusy(true); setErr(null);
    try { await fn(); if (okMsg) toast(okMsg); setConfirm(null); reload(); onChanged(); }
    catch (e) { setErr(e); } finally { setBusy(false); }
  }
  const base = `/workspaces/${ws.id}/agents/${agentId}`;
  const saveEdit = () => act(async () => { await api.patch(base, { name: edit.name.trim(), description: edit.description.trim() }); setEdit(null); }, 'Agent updated.');
  const rotate = () => act(async () => { const d = await api.post(`${base}/credentials/rotate`); setNewKey(d.api_key); setKeySaved(false); }, 'New key created. The old key no longer works.');
  const revoke = () => act(() => api.post(`${base}/credentials/revoke`), 'Key revoked. The agent can no longer connect.');
  const toggle = () => act(() => api.patch(base, { status: agent.status === 'active' ? 'disabled' : 'active' }), agent.status === 'active' ? 'Agent turned off.' : 'Agent turned on.');
  const del = () => act(async () => { await api.del(base); onDeleted(); }, 'Agent deleted. Its history is kept.');

  return (
    <Dialog side title={agent ? agent.name : 'Agent'} subtitle={agent ? agent.agent_id : ''} onClose={newKey && !keySaved ? () => {} : onClose}>
      {error && !agent && <ErrorBox error={error} onRetry={reload} />}
      {!agent && !error && <Loading />}
      {agent && (
        <div className="stack">
          <div className="detail-top">
            <ConnBadge value={agent.connection_status} />
            <span className="muted-cell">Last seen {timeAgo(agent.last_seen_at)}{agent.last_seen_at ? ` (${fmtDate(agent.last_seen_at)})` : ''}</span>
          </div>
          {edit ? (
            <div className="stack">
              <Field label="Name" htmlFor="ed-n"><input id="ed-n" value={edit.name} maxLength={100} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
              <Field label="Description" htmlFor="ed-d"><textarea id="ed-d" rows={3} maxLength={300} value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} /></Field>
              <div className="btn-row"><button className="ghost-btn" onClick={() => setEdit(null)}>Cancel</button><button className="primary-btn" disabled={busy || edit.name.trim().length < 2} onClick={saveEdit}>Save changes</button></div>
            </div>
          ) : <p>{agent.description || <span className="muted-cell">No description.</span>}</p>}

          <div className="mini-stats">
            <div><b>{agent.stats.total}</b><span>actions</span></div>
            <div><b>{agent.stats.allowed}</b><span>allowed</span></div>
            <div><b>{agent.stats.blocked}</b><span>blocked</span></div>
            <div><b>{agent.stats.pending}</b><span>pending</span></div>
          </div>

          <div className="key-info"><KeyRound size={15} /> {agent.has_active_key ? <>Key starts with <span className="mono">{agent.key_prefix}…</span> (the full key is never shown again)</> : 'This agent has no active key. Rotate the key to create one.'}</div>

          {canWrite ? (
            <div className="btn-grid">
              <button className="ghost-btn" onClick={() => setEdit({ name: agent.name, description: agent.description || '' })}><Pencil size={14} /> Edit details</button>
              <button className="ghost-btn" onClick={() => setConfirm('toggle')}><Power size={14} /> {agent.status === 'active' ? 'Turn off' : 'Turn on'}</button>
              <button className="ghost-btn" onClick={() => setConfirm('rotate')}><KeyRound size={14} /> Rotate key</button>
              <button className="ghost-btn" disabled={!agent.has_active_key} onClick={() => setConfirm('revoke')}><ShieldOff size={14} /> Revoke key</button>
              <button className="danger-btn" onClick={() => setConfirm('delete')}><Trash2 size={14} /> Delete agent</button>
            </div>
          ) : <ReadOnlyNote canWrite={false} />}

          <h3 className="mini-title">Connection</h3>
          <ConnectionTest wid={ws.id} agentId={agentId} auto={false} />
          <button className="link-btn" onClick={() => setShowGuide(!showGuide)}>{showGuide ? 'Hide' : 'Show'} integration guide</button>
          {showGuide && <IntegrationGuide apiKey={null} />}

          <h3 className="mini-title">Recent activity</h3>
          <EventTable items={(events.data && events.data.items) || []} loading={events.loading} emptyText="This agent has not sent any actions yet." />
        </div>
      )}

      {confirm === 'toggle' && agent && (
        <Confirm title={agent.status === 'active' ? 'Turn this agent off?' : 'Turn this agent on?'} confirmLabel={agent.status === 'active' ? 'Turn off' : 'Turn on'} busy={busy} error={err} onConfirm={toggle} onClose={() => { setConfirm(null); setErr(null); }}>
          <p>{agent.status === 'active' ? 'While it is off, every request from this agent is refused. Nothing is deleted.' : 'The agent can send requests again.'}</p>
        </Confirm>
      )}
      {confirm === 'rotate' && (
        <Confirm title="Rotate the key?" confirmLabel="Create new key" busy={busy} error={err} onConfirm={rotate} onClose={() => { setConfirm(null); setErr(null); }}>
          <p>A new key is created and the old one stops working immediately. Update your agent with the new key.</p>
        </Confirm>
      )}
      {confirm === 'revoke' && (
        <Confirm title="Revoke the key?" danger confirmLabel="Revoke key" busy={busy} error={err} onConfirm={revoke} onClose={() => { setConfirm(null); setErr(null); }}>
          <p>Use this if the key may have leaked. The agent is cut off immediately. You can create a new key later with “Rotate key”.</p>
        </Confirm>
      )}
      {confirm === 'delete' && (
        <Confirm title="Delete this agent?" danger confirmLabel="Delete agent" busy={busy} error={err} onConfirm={del} onClose={() => { setConfirm(null); setErr(null); }}>
          <p>The agent is removed from your list, its keys are revoked and policies that only applied to it are turned off. Its past activity stays in the event log.</p>
        </Confirm>
      )}
      {newKey && (
        <Dialog title="Your new key" onClose={() => { if (keySaved) setNewKey(null); }} footer={<button className="primary-btn big" disabled={!keySaved} onClick={() => setNewKey(null)}>Done</button>}>
          <KeyReveal apiKey={newKey} confirmed={keySaved} onConfirm={setKeySaved} />
        </Dialog>
      )}
    </Dialog>
  );
}

/* ---------- Page ---------- */
export default function Agents({ ctx }) {
  const { ws, canWrite, categories } = ctx;
  const { data, error, loading, reload } = useFetch(() => api.get(`/workspaces/${ws.id}/agents`), [ws.id], { interval: 10000 });
  const [adding, setAdding] = useState(false);
  const [selected, setSelected] = useState(null);
  const items = (data && data.items) || [];

  return (
    <>
      <section className="panel full-panel">
        <div className="panel-head">
          <div><h2>Your AI agents</h2><p>{items.length} registered</p></div>
          {canWrite && <button className="primary-btn" onClick={() => setAdding(true)}><Plus size={15} /> Add agent</button>}
        </div>
        <ReadOnlyNote canWrite={canWrite} />
        {error && <ErrorBox error={error} onRetry={reload} />}
        {loading && !data ? <Loading /> : items.length === 0 ? (
          <Empty icon={Bot} title="No agents yet" text="Register an AI agent to start checking its actions. It only takes a minute.">
            {canWrite && <button className="primary-btn" onClick={() => setAdding(true)}><Plus size={15} /> Add your first agent</button>}
          </Empty>
        ) : (
          <div className="agent-grid">
            {items.map((a) => (
              <button key={a.id} className="agent-card" onClick={() => setSelected(a.id)}>
                <div className="agent-card-top"><span className="agent-symbol big"><Bot size={18} /></span><div><b>{a.name}</b><span className="mono">{a.agent_id}</span></div></div>
                <ConnBadge value={a.connection_status} />
                <p>{a.description || 'No description'}</p>
                <div className="agent-card-stats"><span>{a.stats.total} actions</span><span>{a.stats.blocked} blocked</span><span>{a.stats.pending} pending</span></div>
                <small>Last seen {timeAgo(a.last_seen_at)}</small>
              </button>
            ))}
          </div>
        )}
      </section>
      {adding && <AddAgentWizard ws={ws} onClose={() => { setAdding(false); reload(); }} onCreated={reload} />}
      {selected && <AgentDetail ws={ws} canWrite={canWrite} agentId={selected} categories={categories} onClose={() => setSelected(null)} onChanged={reload} onDeleted={() => { setSelected(null); reload(); }} />}
    </>
  );
}
