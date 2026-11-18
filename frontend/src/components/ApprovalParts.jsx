import { useState } from 'react';
import { Check, Clock3, ShieldAlert } from 'lucide-react';
import { api, ApiError } from '../api';
import { Dialog, Field, InlineError, Status, fmtDate, useToast } from './ui';
import { catLabel } from './EventParts';

export function ApprovalCard({ item, onAsk, canWrite, categories, expanded = false, history = false }) {
  return (
    <article className={`approval-card ${expanded ? 'expanded' : ''}`}>
      <div className="approval-top">
        <div className="approval-symbol"><ShieldAlert size={18} /></div>
        <div className="approval-title">
          <strong>{item.action}</strong>
          <span>{item.agent_name || item.agent_id} · {catLabel(categories, item.category)}</span>
        </div>
        <Status value={item.status} />
      </div>
      <div className="resource-line"><span>RESOURCE</span><strong>{item.resource || '—'}</strong></div>
      {item.reason && <p className="reason">“{item.reason}”</p>}
      <div className="approval-time"><Clock3 size={13} />Requested {fmtDate(item.created_at)}</div>
      {history ? (
        <div className="approval-meta">
          {item.decided_at
            ? <>Decided {fmtDate(item.decided_at)}{item.decided_by ? ` by ${item.decided_by}` : ''}</>
            : <>Expired {fmtDate(item.expires_at)}</>}
          {item.decision_comment && <p className="reason">Note: {item.decision_comment}</p>}
        </div>
      ) : (
        <>
          {item.expires_at && <div className="approval-meta">Expires {fmtDate(item.expires_at)}</div>}
          {canWrite ? (
            <div className="approval-actions">
              <button className="reject-btn" onClick={() => onAsk(item, 'REJECTED')}>Reject</button>
              <button className="approve-btn" onClick={() => onAsk(item, 'APPROVED')}><Check size={15} /> Approve</button>
            </div>
          ) : <div className="approval-meta">You have view-only access, so you cannot decide this request.</div>}
        </>
      )}
    </article>
  );
}

// Returns { ask, dialog }. Render {dialog} somewhere in the page.
export function useDecision(wid, onDone) {
  const [target, setTarget] = useState(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const toast = useToast();

  const ask = (item, decision) => { setTarget({ item, decision }); setNote(''); setError(null); };
  const close = () => { if (!busy) setTarget(null); };

  async function submit() {
    setBusy(true); setError(null);
    try {
      await api.post(`/workspaces/${wid}/approvals/${target.item.approval_id}/decision`,
        { decision: target.decision, comment: note.trim() });
      toast(target.decision === 'APPROVED' ? 'Request approved. The agent can now see the decision.' : 'Request rejected.');
      setTarget(null);
      onDone();
    } catch (e) {
      if (e instanceof ApiError && (e.code === 'already_decided' || e.status === 409)) {
        toast('Someone already decided this request, or it expired. The list was refreshed.', 'error');
        setTarget(null);
        onDone();
      } else {
        setError(e);
      }
    } finally {
      setBusy(false);
    }
  }

  const approve = target && target.decision === 'APPROVED';
  const dialog = target ? (
    <Dialog
      title={approve ? 'Approve this request?' : 'Reject this request?'}
      onClose={close}
      footer={<>
        <button className="ghost-btn" onClick={close} disabled={busy}>Cancel</button>
        <button className={approve ? 'approve-btn big' : 'danger-btn'} onClick={submit} disabled={busy}>
          {busy ? 'Saving…' : approve ? 'Yes, approve' : 'Yes, reject'}
        </button>
      </>}
    >
      <div className="stack">
        <p><b>{target.item.agent_name || target.item.agent_id}</b> wants to run <span className="mono">{target.item.action}</span> on <b>{target.item.resource || 'an unspecified resource'}</b>.</p>
        {target.item.reason && <p className="reason">“{target.item.reason}”</p>}
        <p className="soft-note">Your decision is saved with your name and the time. Falcon Eye does not run the action; the agent reads your decision and acts on it.</p>
        <Field label="Note (optional)" htmlFor="dec-note" hint="Shown in the approval history.">
          <textarea id="dec-note" rows={3} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <InlineError error={error} />
      </div>
    </Dialog>
  ) : null;
  return { ask, dialog };
}
