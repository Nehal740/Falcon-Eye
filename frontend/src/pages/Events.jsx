import { useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { api, qs } from '../api';
import { useDebounced, useFetch } from '../hooks';
import { Dialog, ErrorBox, Pager } from '../components/ui';
import { EventDetail, EventTable } from '../components/EventParts';

const LIMIT = 25;

export default function Events({ ctx }) {
  const { ws, categories, go } = ctx;
  const [q, setQ] = useState('');
  const [decision, setDecision] = useState('');
  const [agent, setAgent] = useState('');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(null);
  const dq = useDebounced(q);
  const agents = useFetch(() => api.get(`/workspaces/${ws.id}/agents`), [ws.id]);
  const { data, error, loading, reload } = useFetch(
    () => api.get(`/workspaces/${ws.id}/events${qs({ q: dq.trim(), decision, agent_id: agent, limit: LIMIT, offset })}`),
    [ws.id, dq, decision, agent, offset], { interval: 10000 },
  );
  useEffect(() => { setOffset(0); }, [dq, decision, agent]);
  const items = (data && data.items) || [];
  const total = (data && data.total) || 0;

  return (
    <>
      <section className="panel full-panel">
        <div className="panel-head wrap">
          <div><h2>Firewall event log</h2><p>{total} matching events · refreshes every 10 seconds</p></div>
          <div className="filters">
            <label className="search-field"><Search size={15} /><input aria-label="Search events" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search action or resource…" /></label>
            <select aria-label="Filter by decision" value={decision} onChange={(e) => setDecision(e.target.value)}>
              <option value="">All decisions</option><option value="ALLOW">Allowed</option><option value="BLOCK">Blocked</option><option value="REQUIRE_APPROVAL">Needs approval</option>
            </select>
            <select aria-label="Filter by agent" value={agent} onChange={(e) => setAgent(e.target.value)}>
              <option value="">All agents</option>
              {((agents.data && agents.data.items) || []).map((a) => <option key={a.id} value={a.agent_id}>{a.name}</option>)}
            </select>
          </div>
        </div>
        <ErrorBox error={error} onRetry={reload} />
        <EventTable items={items} loading={loading} onSelect={setSelected}
          emptyText={q || decision || agent ? 'No events match these filters. Try clearing them.' : undefined} />
        <Pager total={total} offset={offset} limit={LIMIT} onChange={setOffset} />
      </section>
      {selected && (
        <Dialog side title="Event details" subtitle={selected.action} onClose={() => setSelected(null)}>
          <EventDetail event={selected} categories={categories} go={(p) => { setSelected(null); go(p); }} />
        </Dialog>
      )}
    </>
  );
}
