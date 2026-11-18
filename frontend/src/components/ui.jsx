import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import {
  AlertCircle, Check, CheckCircle2, Copy, Info, Loader2, X,
} from 'lucide-react';
import { friendly } from '../api';

export function fmtDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}

export function timeAgo(value) {
  if (!value) return 'never';
  const secs = Math.round((Date.now() - new Date(value).getTime()) / 1000);
  if (Number.isNaN(secs)) return '—';
  if (secs < 45) return 'just now';
  if (secs < 3600) return `${Math.round(secs / 60)} min ago`;
  if (secs < 86400) return `${Math.round(secs / 3600)} h ago`;
  return `${Math.round(secs / 86400)} d ago`;
}

export const ROLE_LABEL = { owner: 'Owner', admin: 'Admin', member: 'Member (can review approvals)', viewer: 'Viewer (read-only)' };

const DECISION = {
  ALLOW: ['Allowed', 'green'],
  BLOCK: ['Blocked', 'red'],
  REQUIRE_APPROVAL: ['Needs approval', 'amber'],
  PENDING: ['Pending', 'amber'],
  APPROVED: ['Approved', 'green'],
  REJECTED: ['Rejected', 'red'],
  EXPIRED: ['Expired', 'gray'],
};
export function Status({ value }) {
  const v = (value || 'UNKNOWN').toUpperCase();
  const [label, tone] = DECISION[v] || [v.replaceAll('_', ' '), 'gray'];
  return <span className={`status ${tone}`}><i />{label}</span>;
}

const CONN = {
  connected: ['Connected', 'green'],
  waiting: ['Waiting for first connection', 'gray'],
  inactive: ['Quiet lately', 'amber'],
  no_key: ['No active key', 'red'],
  idle: ['Idle', 'amber'],
  never_connected: ['Waiting for first connection', 'gray'],
  disabled: ['Turned off', 'gray'],
  revoked: ['Key revoked', 'red'],
};
export function ConnBadge({ value }) {
  const [label, tone] = CONN[value] || [value || 'Unknown', 'gray'];
  return <span className={`status ${tone}`}><i />{label}</span>;
}

export function Stat({ label, value, note, icon: Icon, tone }) {
  return (
    <article className="stat-card">
      <div className={`stat-icon ${tone}`}><Icon size={19} /></div>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      <div className="stat-note">{note}</div>
    </article>
  );
}

export function Empty({ icon: Icon, title, text, children }) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Icon size={23} /></div>
      <strong>{title}</strong>
      <p>{text}</p>
      {children}
    </div>
  );
}

export function Loading({ text = 'Loading…' }) {
  return <div className="table-message" role="status"><Loader2 size={16} className="spin" /> {text}</div>;
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null;
  const f = friendly(error);
  return (
    <div className="error-banner" role="alert">
      <AlertCircle size={19} />
      <div>
        <b>{f.title}</b>
        <p><strong>What happened:</strong> {f.message}</p>
        <p><strong>What you can do:</strong> {f.hint}</p>
      </div>
      {onRetry && <button onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function InlineError({ error }) {
  if (!error) return null;
  const f = friendly(error);
  return (
    <div className="inline-error" role="alert">
      <b>{f.message}</b>
      <span>{f.hint}</span>
    </div>
  );
}

export function Notice({ tone = 'info', icon: Icon = Info, children }) {
  return <div className={`notice ${tone}`}><Icon size={17} /><div>{children}</div></div>;
}

export function Field({ label, hint, error, htmlFor, children }) {
  return (
    <div className={`fld ${error ? 'has-error' : ''}`}>
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && !error && <small>{hint}</small>}
      {error && <small className="fld-error">{error}</small>}
    </div>
  );
}

export function CopyButton({ text, label = 'Copy', small = false }) {
  const [done, setDone] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); } catch { /* ignore */ }
      document.body.removeChild(ta);
    }
    setDone(true);
    setTimeout(() => setDone(false), 1800);
  }
  return (
    <button type="button" className={`ghost-btn ${small ? 'small' : ''}`} onClick={copy}>
      {done ? <Check size={14} /> : <Copy size={14} />} {done ? 'Copied' : label}
    </button>
  );
}

export function CodeBlock({ code, label }) {
  return (
    <div className="code-block">
      <div className="code-head"><span>{label}</span><CopyButton text={code} small /></div>
      <pre tabIndex={0}><code>{code}</code></pre>
    </div>
  );
}

/* ---------- Dialog / drawer with focus handling and Escape ---------- */
const dialogStack = [];
let dialogId = 0;

export function Dialog({ title, subtitle, onClose, children, footer, side = false, wide = false }) {
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const [id] = useState(() => ++dialogId);

  useEffect(() => {
    const previous = document.activeElement;
    dialogStack.push(id);
    ref.current?.focus();
    document.body.style.overflow = 'hidden';
    function onKey(e) {
      if (dialogStack[dialogStack.length - 1] !== id) return;
      if (e.key === 'Escape') { e.preventDefault(); closeRef.current(); return; }
      if (e.key === 'Tab' && ref.current) {
        const items = ref.current.querySelectorAll(
          'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'
        );
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && (document.activeElement === first || document.activeElement === ref.current)) {
          e.preventDefault(); last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault(); first.focus();
        }
      }
    }
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      const i = dialogStack.indexOf(id);
      if (i >= 0) dialogStack.splice(i, 1);
      if (!dialogStack.length) document.body.style.overflow = '';
      if (previous && previous.focus) previous.focus();
    };
  }, [id]);

  return (
    <div className={`dialog-layer ${side ? 'side' : ''}`}>
      <div className="dialog-scrim" onClick={() => closeRef.current()} />
      <section
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`dialog ${side ? 'drawer' : ''} ${wide ? 'wide' : ''}`}
      >
        <header className="dialog-head">
          <div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
          <button className="icon-btn" onClick={() => closeRef.current()} aria-label="Close"><X size={18} /></button>
        </header>
        <div className="dialog-body">{children}</div>
        {footer && <footer className="dialog-foot">{footer}</footer>}
      </section>
    </div>
  );
}

export function Confirm({ title, children, confirmLabel = 'Confirm', danger = false, busy = false, error, onConfirm, onClose }) {
  return (
    <Dialog
      title={title}
      onClose={onClose}
      footer={<>
        <button className="ghost-btn" onClick={onClose} disabled={busy}>Cancel</button>
        <button className={danger ? 'danger-btn' : 'primary-btn'} onClick={onConfirm} disabled={busy}>
          {busy ? 'Working…' : confirmLabel}
        </button>
      </>}
    >
      <div className="stack">{children}<InlineError error={error} /></div>
    </Dialog>
  );
}

/* ---------- Toasts ---------- */
const ToastContext = createContext(() => {});
export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const push = useCallback((message, tone = 'ok') => {
    const id = Math.random().toString(36).slice(2);
    setItems((l) => [...l, { id, message, tone }]);
    setTimeout(() => setItems((l) => l.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toast-stack" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast-item ${t.tone}`}>
            {t.tone === 'error' ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}{t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function ReadOnlyNote({ canWrite }) {
  if (canWrite) return null;
  return (
    <Notice icon={Info}>
      <b>You have read-only access.</b> You can look at everything in this workspace, but only an owner or admin can make changes or decide approvals.
    </Notice>
  );
}

export function Pager({ total, offset, limit, onChange }) {
  if (total <= limit) return null;
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.ceil(total / limit);
  return (
    <div className="pager">
      <button className="ghost-btn small" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button>
      <span>Page {page} of {pages} · {total} total</span>
      <button className="ghost-btn small" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next</button>
    </div>
  );
}
