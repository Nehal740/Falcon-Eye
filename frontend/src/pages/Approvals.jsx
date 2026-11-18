import { useState } from 'react';
import { CheckCircle2, History } from 'lucide-react';
import { api, qs } from '../api';
import { useFetch } from '../hooks';
import { Empty, ErrorBox, Loading, Pager, ReadOnlyNote } from '../components/ui';
import { ApprovalCard, useDecision } from '../components/ApprovalParts';

const LIMIT = 12;

export default function Approvals({ ctx }) {
  const { ws, canWrite, categories } = ctx;
  const [tab, setTab] = useState('PENDING');
  const [offset, setOffset] = useState(0);
  const pending = tab === 'PENDING';
  const { data, error, loading, reload } = useFetch(
    () => api.get(`/workspaces/${ws.id}/approvals${qs({ status: pending ? 'PENDING' : 'ALL', limit: LIMIT, offset })}`),
    [ws.id, tab, offset], { interval: 10000 },
  );
  const { ask, dialog } = useDecision(ws.id, () => { reload(); ctx.refreshPending(); });
  let items = (data && data.items) || [];
  if (!pending) items = items.filter((a) => a.status !== 'PENDING');
  const total = (data && data.total) || 0;

  return (
    <section className="panel full-panel">
      <div className="panel-head wrap">
        <div><h2>{pending ? 'Waiting for a decision' : 'Approval history'}</h2>
          <p>{pending ? 'Review each request, then approve or reject it.' : 'Past decisions, who made them, and when.'}</p></div>
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={pending} className={pending ? 'on' : ''} onClick={() => { setTab('PENDING'); setOffset(0); }}>Pending</button>
          <button role="tab" aria-selected={!pending} className={!pending ? 'on' : ''} onClick={() => { setTab('HISTORY'); setOffset(0); }}>History</button>
        </div>
      </div>
      <ReadOnlyNote canWrite={ctx.canDecide} />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? <Loading /> : items.length === 0 ? (
        pending
          ? <Empty icon={CheckCircle2} title="No pending approvals" text="When a policy says “ask a human first”, the request will appear here." />
          : <Empty icon={History} title="No decisions yet" text="Approved and rejected requests will be listed here." />
      ) : (
        <div className="approval-grid">
          {items.map((a) => <ApprovalCard key={a.approval_id} item={a} onAsk={ask} canWrite={ctx.canDecide} categories={categories} expanded history={!pending} />)}
        </div>
      )}
      <Pager total={total} offset={offset} limit={LIMIT} onChange={setOffset} />
      {dialog}
    </section>
  );
}
