import { Bot, FileText } from 'lucide-react';
import { Empty, Loading, Status, fmtDate } from './ui';

export function catLabel(categories, key) {
  const c = (categories || []).find((x) => x.key === key);
  return c ? c.label : (key || '—');
}

export function EventTable({ items, loading, onSelect, emptyText }) {
  if (loading && !items.length) return <Loading text="Loading firewall activity…" />;
  if (!items.length) {
    return (
      <Empty icon={FileText} title="No activity yet"
        text={emptyText || 'When your agents send actions to the firewall, each decision will appear here.'} />
    );
  }
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr><th>AGENT</th><th>ACTION</th><th>RESOURCE</th><th>DECISION</th><th>TIME</th></tr>
        </thead>
        <tbody>
          {items.map((e) => (
            <tr key={e.event_id} className={onSelect ? 'clickable' : ''} onClick={onSelect ? () => onSelect(e) : undefined}>
              <td><span className="agent-name"><span className="agent-symbol"><Bot size={14} /></span>{e.agent_name || e.agent_id}</span></td>
              <td className="mono">
                {onSelect
                  ? <button className="linklike" onClick={(ev) => { ev.stopPropagation(); onSelect(e); }}>{e.action}</button>
                  : e.action}
              </td>
              <td className="resource">{e.resource || '—'}</td>
              <td><Status value={e.decision} /></td>
              <td className="muted-cell">{fmtDate(e.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EventDetail({ event, categories, go }) {
  const rows = [
    ['Decision', <Status key="d" value={event.decision} />],
    ['Why', event.decision_reason || '—'],
    ['Agent', `${event.agent_name || event.agent_id} (${event.agent_id})`],
    ['Action', <span key="a" className="mono">{event.action}</span>],
    ['Category', catLabel(categories, event.category)],
    ['Resource', event.resource || '—'],
    ['Reason given by the agent', event.agent_reason || '—'],
    ['Policy that decided', event.policy_name || 'No policy matched (default: block)'],
    ['When', fmtDate(event.created_at)],
    ['Event ID', <span key="e" className="mono">{event.event_id}</span>],
  ];
  return (
    <div className="stack">
      <dl className="detail-list">
        {rows.map(([k, v]) => (<div key={k}><dt>{k}</dt><dd>{v}</dd></div>))}
        {event.approval_id && (
          <div><dt>Approval request</dt><dd>
            <span className="mono">{event.approval_id}</span>{' '}
            {go && <button className="linklike" onClick={() => go('approvals')}>Open approvals</button>}
          </dd></div>
        )}
      </dl>
      {event.metadata && Object.keys(event.metadata).length > 0 && (
        <div>
          <h3 className="mini-title">Extra details sent by the agent</h3>
          <pre className="json-box" tabIndex={0}>{JSON.stringify(event.metadata, null, 2)}</pre>
        </div>
      )}
      <p className="soft-note">Falcon Eye records its decision only. It never performs the action itself.</p>
    </div>
  );
}
