import { useState } from 'react';
import {
  Activity, AlertCircle, AlertTriangle, ArrowUpRight, Bot, CheckCircle2, Clock3, Info,
  ShieldAlert, ShieldCheck, SlidersHorizontal,
} from 'lucide-react';
import { api } from '../api';
import { useFetch } from '../hooks';
import { Empty, ErrorBox, Loading, Stat, ReadOnlyNote, fmtDate } from '../components/ui';
import { EventDetail, EventTable } from '../components/EventParts';
import { ApprovalCard, useDecision } from '../components/ApprovalParts';
import { Dialog } from '../components/ui';

function DailyChart({ daily }) {
  const max = Math.max(1, ...daily.map((d) => d.allowed + d.blocked + d.require_approval));
  const total = daily.reduce((n, d) => n + d.allowed + d.blocked + d.require_approval, 0);
  if (!total) {
    return <Empty icon={Activity} title="No decisions in the last 7 days" text="The chart fills in as your agents send actions." />;
  }
  return (
    <div>
      <div className="bars" role="img" aria-label={`Decisions per day for the last 7 days: ${daily.map((d) => `${d.date}: ${d.allowed} allowed, ${d.require_approval} need approval, ${d.blocked} blocked`).join('; ')}`}>
        {daily.map((d) => {
          const sum = d.allowed + d.blocked + d.require_approval;
          const day = new Date(`${d.date}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short' });
          return (
            <div className="bar-col" key={d.date} title={`${d.date}: ${d.allowed} allowed, ${d.require_approval} need approval, ${d.blocked} blocked`}>
              <span className="bar-num">{sum || ''}</span>
              <div className="bar-stack" style={{ height: `${(sum / max) * 100}%` }}>
                <i className="seg red" style={{ flex: d.blocked }} />
                <i className="seg amber" style={{ flex: d.require_approval }} />
                <i className="seg green" style={{ flex: d.allowed }} />
              </div>
              <span className="bar-day">{day}</span>
            </div>
          );
        })}
      </div>
      <div className="legend"><span><i className="seg green" /> Allowed</span><span><i className="seg amber" /> Needs approval</span><span><i className="seg red" /> Blocked</span></div>
    </div>
  );
}

const ALERT_ICON = { critical: AlertCircle, warning: AlertTriangle, info: Info };

export default function Dashboard({ ctx }) {
  const { ws, canWrite, go, categories } = ctx;
  const { data, error, loading, reload } = useFetch(() => api.get(`/workspaces/${ws.id}/dashboard`), [ws.id], { interval: 10000 });
  const [selected, setSelected] = useState(null);
  const { ask, dialog } = useDecision(ws.id, () => { reload(); ctx.refreshPending(); });

  if (loading && !data) return <Loading text="Loading your dashboard…" />;
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const t = data.totals;
  const h = data.last_24h;

  return (
    <>
      {error && <ErrorBox error={error} onRetry={reload} />}
      <ReadOnlyNote canWrite={canWrite} />

      {data.alerts.length > 0 && (
        <section className="alerts" aria-label="Security alerts">
          {data.alerts.map((a) => {
            const Icon = ALERT_ICON[a.severity] || Info;
            return (
              <div key={a.id} className={`alert-row ${a.severity}`}>
                <Icon size={18} />
                <div><b>{a.title}</b><p>{a.message}</p></div>
                {a.page && <button className="link-btn" onClick={() => go(a.page.toLowerCase())}>Open <ArrowUpRight size={14} /></button>}
              </div>
            );
          })}
        </section>
      )}

      <section className="stats-grid six">
        <Stat label="Agents" value={t.agents} note={`${t.active_agents} active`} icon={Bot} tone="blue" />
        <Stat label="Evaluated actions" value={t.events} note={`${h.events} in the last 24 hours`} icon={Activity} tone="blue" />
        <Stat label="Allowed" value={t.allowed} note={`${h.allowed} in the last 24 hours`} icon={ShieldCheck} tone="green" />
        <Stat label="Blocked" value={t.blocked} note={`${h.blocked} in the last 24 hours`} icon={ShieldAlert} tone="red" />
        <Stat label="Pending approvals" value={t.pending_approvals} note="Waiting for a human" icon={Clock3} tone="amber" />
        <Stat label="Policies" value={t.policies} note={`${t.enabled_policies} turned on`} icon={SlidersHorizontal} tone="blue" />
      </section>

      <section className="dashboard-grid">
        <div className="panel activity-panel">
          <div className="panel-head">
            <div><h2>Recent security events</h2><p>Latest decisions · refreshes every 10 seconds</p></div>
            <button className="link-btn" onClick={() => go('events')}>View all <ArrowUpRight size={14} /></button>
          </div>
          <EventTable items={data.recent_events} loading={false} onSelect={setSelected} />
        </div>

        <div className="panel approvals-panel">
          <div className="panel-head">
            <div><h2>Needs your attention</h2><p>Human approval queue</p></div>
            <span className="count-pill">{t.pending_approvals}</span>
          </div>
          {data.pending_approvals.length ? (
            <div className="approval-stack">
              {data.pending_approvals.map((a) => (
                <ApprovalCard key={a.approval_id} item={a} onAsk={ask} canWrite={ctx.canDecide} categories={categories} />
              ))}
            </div>
          ) : <Empty icon={CheckCircle2} title="You’re all caught up" text="No requests are waiting for a decision." />}
          {t.pending_approvals > data.pending_approvals.length && (
            <button className="link-btn centered" onClick={() => go('approvals')}>View all approvals</button>
          )}
        </div>
      </section>

      <section className="grid-3">
        <div className="panel">
          <div className="panel-head"><div><h2>Last 7 days</h2><p>Decisions per day</p></div></div>
          <DailyChart daily={data.daily} />
        </div>

        <div className="panel">
          <div className="panel-head"><div><h2>Most active agents</h2><p>By number of actions</p></div></div>
          {data.top_agents.length ? (
            <ul className="mini-list">
              {data.top_agents.map((a) => (
                <li key={a.agent_id}><span><Bot size={14} /> {a.name || a.agent_id}</span><span>{a.events} actions · {a.blocked} blocked</span></li>
              ))}
            </ul>
          ) : <Empty icon={Bot} title="No agent activity yet" text="Agents appear here after their first request." />}
        </div>

        <div className="panel">
          <div className="panel-head"><div><h2>Policy activity</h2><p>How often each policy decided</p></div>
            <button className="link-btn" onClick={() => go('policies')}>Manage <ArrowUpRight size={14} /></button></div>
          {data.policy_stats.length ? (
            <ul className="mini-list">
              {data.policy_stats.map((p) => (
                <li key={p.id}><span>{p.name}{!p.enabled && <em className="off-tag">off</em>}</span><span>{p.matches} decisions</span></li>
              ))}
            </ul>
          ) : <Empty icon={SlidersHorizontal} title="No policies yet" text="Without a policy every action is blocked." />}
        </div>
      </section>

      <p className="soft-note">Updated {fmtDate(data.generated_at)}</p>

      {selected && (
        <Dialog side title="Event details" subtitle={selected.action} onClose={() => setSelected(null)}>
          <EventDetail event={selected} categories={categories} go={(p) => { setSelected(null); go(p); }} />
        </Dialog>
      )}
      {dialog}
    </>
  );
}
