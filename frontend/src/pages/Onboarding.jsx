import { useEffect, useState } from 'react';
import { Bot, Check, FlaskConical, ShieldAlert, ShieldCheck, SlidersHorizontal, UserCheck, Zap } from 'lucide-react';
import { api } from '../api';
import { Field, InlineError, Loading, Notice, Status, useToast } from '../components/ui';
import { KeyReveal } from '../components/Guide';

const STEPS = ['Welcome', 'Workspace', 'First agent', 'First policy', 'How it decides', 'Done'];

export default function Onboarding({ ws, canWrite, onFinish }) {
  const toast = useToast();
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const [wsName, setWsName] = useState(ws.name);
  const [agentName, setAgentName] = useState('');
  const [agentDesc, setAgentDesc] = useState('');
  const [agent, setAgent] = useState(null);       // {id,name}
  const [apiKey, setApiKey] = useState('');
  const [saved, setSaved] = useState(false);

  const [templates, setTemplates] = useState(null);
  const [tplKey, setTplKey] = useState('');
  const [policyMade, setPolicyMade] = useState(null);

  const [sim, setSim] = useState({ action: 'read_document', resource: '' });
  const [simResult, setSimResult] = useState(null);

  useEffect(() => {
    if (step === 3 && !templates) {
      api.get('/policy-templates').then((d) => {
        setTemplates(d.items);
        if (d.items.length) setTplKey(d.items[0].key);
      }).catch(setError);
    }
  }, [step, templates]);

  async function finish() {
    try { await api.post('/auth/onboarding/complete'); } catch { /* not critical */ }
    onFinish();
  }

  async function run(fn) {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError(e); } finally { setBusy(false); }
  }

  const next = () => { setError(null); setStep((s) => Math.min(STEPS.length - 1, s + 1)); };
  const back = () => { setError(null); setStep((s) => Math.max(0, s - 1)); };

  const saveWorkspace = () => run(async () => {
    if (canWrite && wsName.trim() && wsName.trim() !== ws.name) {
      await api.patch(`/workspaces/${ws.id}`, { name: wsName.trim() });
      toast('Workspace renamed.');
    }
    next();
  });

  const createAgent = () => run(async () => {
    const d = await api.post(`/workspaces/${ws.id}/agents`, { name: agentName.trim(), description: agentDesc.trim() });
    setAgent(d.agent); setApiKey(d.api_key); setSaved(false);
  });

  const createPolicy = () => run(async () => {
    const t = templates.find((x) => x.key === tplKey);
    const p = await api.post(`/workspaces/${ws.id}/policies`, {
      name: t.name, description: t.description, enabled: true, priority: 100, agent_id: null, rules: t.rules,
    });
    setPolicyMade(p);
    toast('Policy created.');
    next();
  });

  const simulate = (action, resource) => run(async () => {
    if (!agent) return;
    const r = await api.post(`/workspaces/${ws.id}/policies/simulate`, { agent_id: agent.id, action, resource: resource || '' });
    setSimResult({ ...r, action });
  });

  const tpl = templates && templates.find((t) => t.key === tplKey);

  return (
    <div className="onboard" role="dialog" aria-modal="true" aria-label="Welcome to Falcon Eye">
      <div className="onboard-card">
        <header className="onboard-head">
          <img src="/falcon-eye-icon.png" alt="" width="40" height="40" />
          <div><b>Set up Falcon Eye</b><span>Step {step + 1} of {STEPS.length} · {STEPS[step]}</span></div>
          {step < STEPS.length - 1 && <button className="linklike" onClick={finish}>Skip for now</button>}
        </header>
        <div className="progress" aria-hidden="true">
          {STEPS.map((s, i) => <i key={s} className={i <= step ? 'on' : ''} />)}
        </div>

        <div className="onboard-body">
          {step === 0 && (
            <div className="stack">
              <h2>Keep control of your AI agents</h2>
              <p>AI agents can send emails, read files and call other systems. Falcon Eye sits in front of them and answers one question every time: <b>“Is this action allowed?”</b></p>
              <div className="three-cards">
                <div><ShieldCheck size={22} /><b>Checks every action</b><p>Your rules decide: allow, block, or ask a human.</p></div>
                <div><UserCheck size={22} /><b>Humans stay in charge</b><p>Sensitive actions wait for your approval.</p></div>
                <div><Zap size={22} /><b>Everything is recorded</b><p>A clear history of what each agent tried to do.</p></div>
              </div>
              <p className="soft-note">This takes about two minutes. You can skip any step and come back later.</p>
            </div>
          )}

          {step === 1 && (
            <div className="stack">
              <h2>Name your workspace</h2>
              <p>A workspace keeps your agents, policies and activity together and private from other workspaces.</p>
              <Field label="Workspace name" htmlFor="ob-ws">
                <input id="ob-ws" value={wsName} onChange={(e) => setWsName(e.target.value)} maxLength={100} disabled={!canWrite} />
              </Field>
              {!canWrite && <Notice>Only an owner or admin can rename this workspace.</Notice>}
            </div>
          )}

          {step === 2 && (
            <div className="stack">
              <h2>Add your first AI agent</h2>
              {!agent ? (
                <>
                  <p>An “agent” is any AI program or automation (for example an n8n workflow or a Python script) that you want Falcon Eye to watch.</p>
                  {!canWrite && <Notice>Only an owner or admin can add agents. You can skip this step.</Notice>}
                  <Field label="Agent name" htmlFor="ob-an" hint="For example: Support email assistant">
                    <input id="ob-an" value={agentName} onChange={(e) => setAgentName(e.target.value)} maxLength={100} disabled={!canWrite} />
                  </Field>
                  <Field label="What does it do? (optional)" htmlFor="ob-ad">
                    <input id="ob-ad" value={agentDesc} onChange={(e) => setAgentDesc(e.target.value)} maxLength={300} disabled={!canWrite} />
                  </Field>
                </>
              ) : (
                <>
                  <Notice icon={Check} tone="ok"><b>{agent.name}</b> is registered.</Notice>
                  <KeyReveal apiKey={apiKey} confirmed={saved} onConfirm={setSaved} />
                  <p className="soft-note">Full connection instructions are in Agents → {agent.name} → Integration guide.</p>
                </>
              )}
            </div>
          )}

          {step === 3 && (
            <div className="stack">
              <h2>Choose a starter policy</h2>
              <p>Policies are your rules. <b>Anything not covered by a rule is blocked</b>, so a starter policy is the quickest way to get useful results. You can edit it later.</p>
              {!templates ? <Loading /> : (
                <div className="tpl-list" role="radiogroup" aria-label="Starter policies">
                  {templates.map((t) => (
                    <label key={t.key} className={`tpl ${tplKey === t.key ? 'on' : ''}`}>
                      <input type="radio" name="tpl" checked={tplKey === t.key} onChange={() => setTplKey(t.key)} />
                      <div><b>{t.name}</b><p>{t.description}</p></div>
                    </label>
                  ))}
                </div>
              )}
              {tpl && (
                <ul className="rule-preview">
                  {tpl.rules.map((r, i) => (
                    <li key={i}><Status value={r.effect} /> {r.effect === 'ALLOW' ? 'Allow' : r.effect === 'BLOCK' ? 'Block' : 'Ask a human for'} {r.target_type === 'category' ? `“${r.target_value.replaceAll('_', ' ')}” actions` : `actions named “${r.target_value}”`}</li>
                  ))}
                </ul>
              )}
              {policyMade && <Notice icon={Check} tone="ok">“{policyMade.name}” is already created.</Notice>}
              {!canWrite && <Notice>Only an owner or admin can create policies. You can skip this step.</Notice>}
            </div>
          )}

          {step === 4 && (
            <div className="stack">
              <h2>How Falcon Eye decides</h2>
              <div className="three-cards decisions">
                <div className="d-allow"><ShieldCheck size={22} /><b>ALLOW</b><p>A rule says this is fine. The agent may continue.</p></div>
                <div className="d-block"><ShieldAlert size={22} /><b>BLOCK</b><p>A rule forbids it, or nothing allows it. The agent must stop.</p></div>
                <div className="d-ask"><UserCheck size={22} /><b>REQUIRE APPROVAL</b><p>A person must approve it first. It appears in Approvals.</p></div>
              </div>
              <h3 className="mini-title"><FlaskConical size={14} /> Try it (nothing is recorded)</h3>
              {!agent ? <Notice>Add an agent in step 3 to try the simulator.</Notice> : (
                <>
                  <div className="chips">
                    {['read_document', 'send_external_email', 'delete_file'].map((a) => (
                      <button key={a} className="chip" disabled={busy} onClick={() => { setSim({ ...sim, action: a }); simulate(a, sim.resource); }}>{a}</button>
                    ))}
                  </div>
                  <div className="row-fields">
                    <Field label="Or type an action" htmlFor="ob-sa">
                      <input id="ob-sa" value={sim.action} onChange={(e) => setSim({ ...sim, action: e.target.value })} />
                    </Field>
                    <button className="primary-btn" disabled={busy || !sim.action.trim()} onClick={() => simulate(sim.action.trim(), sim.resource)}>Test</button>
                  </div>
                  {simResult && (
                    <div className="sim-result">
                      <Status value={simResult.decision} />
                      <p><span className="mono">{simResult.action}</span> → {simResult.reason}</p>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {step === 5 && (
            <div className="stack center-text">
              <div className="done-icon"><Check size={30} /></div>
              <h2>You’re ready</h2>
              <p>Your dashboard shows live activity as soon as an agent sends its first action.</p>
              <ul className="done-list">
                <li><Bot size={15} /> {agent ? `Agent “${agent.name}” registered` : 'No agent yet — add one from Agents'}</li>
                <li><SlidersHorizontal size={15} /> {policyMade ? `Policy “${policyMade.name}” active` : 'No policy yet — everything is blocked until you add one'}</li>
              </ul>
            </div>
          )}
          <InlineError error={error} />
        </div>

        <footer className="onboard-foot">
          <button className="ghost-btn" onClick={back} disabled={busy || step === 0 || (step === 2 && !!agent)}>Back</button>
          <div className="foot-right">
            {step === 0 && <button className="primary-btn big" onClick={next}>Get started</button>}
            {step === 1 && <button className="primary-btn big" disabled={busy || !wsName.trim()} onClick={saveWorkspace}>Continue</button>}
            {step === 2 && !agent && (<>
              <button className="ghost-btn" onClick={next} disabled={busy}>Skip</button>
              <button className="primary-btn big" disabled={busy || !canWrite || !agentName.trim()} onClick={createAgent}>Create agent</button>
            </>)}
            {step === 2 && agent && <button className="primary-btn big" disabled={!saved} onClick={next}>Continue</button>}
            {step === 3 && (<>
              <button className="ghost-btn" onClick={next} disabled={busy}>Skip</button>
              <button className="primary-btn big" disabled={busy || !canWrite || !tpl || !!policyMade} onClick={createPolicy}>Use this policy</button>
              {policyMade && <button className="primary-btn big" onClick={next}>Continue</button>}
            </>)}
            {step === 4 && <button className="primary-btn big" onClick={next}>Continue</button>}
            {step === 5 && <button className="primary-btn big" onClick={finish}>Open my dashboard</button>}
          </div>
        </footer>
      </div>
    </div>
  );
}
