import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity, Bot, ChevronDown, CircleHelp, LayoutDashboard, LogOut, Menu, MessageCircle,
  Plus, Settings as SettingsIcon, ShieldCheck, SlidersHorizontal, X,
} from 'lucide-react';
import { api, getToken, onAuthLost, refreshIfNeeded, setToken } from './api';
import { useFetch } from './hooks';
import Auth from './Auth';
import { ResetPassword, VerifyBanner, VerifyEmail } from './EmailActions';
import Assistant from './components/Assistant';
import { Dialog, ErrorBox, Field, InlineError, ROLE_LABEL, ToastProvider, useToast } from './components/ui';
import Dashboard from './pages/Dashboard';
import Agents from './pages/Agents';
import Policies from './pages/Policies';
import Events from './pages/Events';
import Approvals from './pages/Approvals';
import Settings from './pages/Settings';
import Onboarding from './pages/Onboarding';

const WS_KEY = 'falcon_eye_workspace';
const PAGES = {
  overview: { label: 'Overview', icon: LayoutDashboard, title: 'Security overview', text: 'Live view of what your AI agents are doing.' },
  agents: { label: 'Agents', icon: Bot, title: 'Agents', text: 'Connect and manage the AI agents Falcon Eye protects.' },
  policies: { label: 'Policies', icon: SlidersHorizontal, title: 'Policies', text: 'Write the rules that decide what agents may do.' },
  events: { label: 'Events', icon: Activity, title: 'Events', text: 'A clear record of every decision your firewall made.' },
  approvals: { label: 'Approvals', icon: ShieldCheck, title: 'Approvals', text: 'Review sensitive actions that need a human decision.' },
  settings: { label: 'Settings', icon: SettingsIcon, title: 'Settings', text: 'Workspace, members, account and audit log.' },
};
const PAGE_COMPONENT = { overview: Dashboard, agents: Agents, policies: Policies, events: Events, approvals: Approvals, settings: Settings };

function readPage() {
  const p = window.location.hash.replace(/^#\/?/, '');
  return PAGES[p] ? p : 'overview';
}
// Links in emails look like  /#/reset-password?token=...  or  /#/verify-email?token=...
function readEmailRoute() {
  const [name, query = ''] = window.location.hash.replace(/^#\/?/, '').split('?');
  if (name !== 'reset-password' && name !== 'verify-email') return null;
  return { name, token: new URLSearchParams(query).get('token') || '' };
}
function readWs() { try { return localStorage.getItem(WS_KEY); } catch { return null; } }
function writeWs(id) { try { localStorage.setItem(WS_KEY, String(id)); } catch { /* ignore */ } }

function Splash({ text }) {
  return (
    <div className="splash" role="status">
      <img src="/falcon-eye-icon.png" alt="Falcon Eye" width="84" height="84" />
      <p>{text}</p>
    </div>
  );
}

function NewWorkspaceDialog({ onClose, onCreated }) {
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  async function create(e) {
    e.preventDefault(); setBusy(true); setError(null);
    try { const w = await api.post('/workspaces', { name: name.trim() }); onCreated(w); }
    catch (x) { setError(x); } finally { setBusy(false); }
  }
  return (
    <Dialog title="Create a workspace" subtitle="A separate space with its own agents, policies and activity." onClose={onClose}
      footer={<><button className="ghost-btn" onClick={onClose}>Cancel</button>
        <button className="primary-btn big" form="new-ws" disabled={busy || name.trim().length < 2}>{busy ? 'Creating…' : 'Create workspace'}</button></>}>
      <form id="new-ws" className="stack" onSubmit={create}>
        <Field label="Workspace name" htmlFor="nw-name" hint="For example: Marketing team"><input id="nw-name" autoFocus value={name} maxLength={100} onChange={(e) => setName(e.target.value)} /></Field>
        <InlineError error={error} />
      </form>
    </Dialog>
  );
}

function Shell({ me, reloadMe, onLogout }) {
  const toast = useToast();
  const [page, setPage] = useState(readPage);
  const [mobileNav, setMobileNav] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [chat, setChat] = useState([]);
  const [switcher, setSwitcher] = useState(false);
  const [creating, setCreating] = useState(false);
  const [skipOnboarding, setSkipOnboarding] = useState(false);
  const [wsId, setWsId] = useState(() => readWs());

  const workspaces = me.workspaces;
  const ws = useMemo(() => workspaces.find((w) => String(w.id) === String(wsId)) || workspaces[0], [workspaces, wsId]);
  const canWrite = ws.role === 'owner' || ws.role === 'admin';
  const canDecide = canWrite || ws.role === 'member';

  useEffect(() => { writeWs(ws.id); }, [ws.id]);
  useEffect(() => {
    const on = () => setPage(readPage());
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  useEffect(() => {
    const t = setInterval(() => { refreshIfNeeded(); }, 60000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => { if (switcher) { const f = (e) => { if (e.key === 'Escape') setSwitcher(false); }; document.addEventListener('keydown', f); return () => document.removeEventListener('keydown', f); } return undefined; }, [switcher]);

  const categoriesQ = useFetch(() => api.get('/action-categories'), []);
  const pendingQ = useFetch(() => api.get(`/workspaces/${ws.id}/approvals?status=PENDING&limit=1`), [ws.id], { interval: 15000 });
  const healthQ = useFetch(() => api.get('/health', { auth: false }), [], { interval: 30000 });
  const pending = (pendingQ.data && pendingQ.data.total) || 0;
  const health = healthQ.error ? 'down' : healthQ.data ? healthQ.data.status : 'checking';

  const go = useCallback((p) => { window.location.hash = `#/${p}`; setMobileNav(false); window.scrollTo(0, 0); }, []);
  const selectWs = (id) => { setWsId(id); setSwitcher(false); setMobileNav(false); setChat([]); };

  const ctx = {
    ws, canWrite, canDecide, go, me: me.user, workspaces, onLogout,
    categories: (categoriesQ.data && categoriesQ.data.items) || [],
    refreshMe: reloadMe,
    emailAvailable: !!me.email_available,
    refreshPending: pendingQ.reload,
    onWorkspaceDeleted: async () => { await reloadMe(); setWsId(null); go('overview'); },
  };
  const info = PAGES[page];
  const Page = PAGE_COMPONENT[page];
  const showOnboarding = me.user.onboarding_completed === false && !skipOnboarding;

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); const m = document.getElementById('main'); if (m) m.focus(); }}>Skip to content</a>
      <aside className={`sidebar ${mobileNav ? 'show' : ''}`} aria-label="Main navigation">
        <div className="brand-row">
          <img className="brand-img" src="/falcon-eye-icon.png" alt="" width="40" height="40" />
          <div className="brand-name">Falcon Eye<small>AI AGENT FIREWALL</small></div>
          <button className="mobile-close icon-btn" onClick={() => setMobileNav(false)} aria-label="Close menu"><X /></button>
        </div>

        <div className="side-caption">WORKSPACE</div>
        <div className="ws-switch">
          <button className="workspace" aria-haspopup="listbox" aria-expanded={switcher} onClick={() => setSwitcher(!switcher)}>
            <span className="workspace-avatar">{ws.name.slice(0, 1).toUpperCase()}</span>
            <span className="workspace-text"><b>{ws.name}</b><small>{ROLE_LABEL[ws.role] || ws.role}</small></span>
            <ChevronDown size={15} />
          </button>
          {switcher && (
            <div className="ws-menu" role="listbox" aria-label="Choose workspace">
              {workspaces.map((w) => (
                <button key={w.id} role="option" aria-selected={w.id === ws.id} className={w.id === ws.id ? 'on' : ''} onClick={() => selectWs(w.id)}>
                  <span className="workspace-avatar sm">{w.name.slice(0, 1).toUpperCase()}</span>{w.name}
                </button>
              ))}
              <button className="new" onClick={() => { setSwitcher(false); setCreating(true); }}><Plus size={14} /> New workspace</button>
            </div>
          )}
        </div>

        <div className="side-caption nav-caption">PLATFORM</div>
        <nav>
          {['overview', 'agents', 'policies', 'events', 'approvals'].map((k) => {
            const Icon = PAGES[k].icon;
            return (
              <button key={k} className={`nav-link ${page === k ? 'selected' : ''}`} aria-current={page === k ? 'page' : undefined} onClick={() => go(k)}>
                <Icon size={18} /><span>{PAGES[k].label}</span>
                {k === 'approvals' && pending > 0 && <em aria-label={`${pending} pending`}>{pending}</em>}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-bottom">
          <button className={`nav-link ${page === 'settings' ? 'selected' : ''}`} onClick={() => go('settings')} aria-current={page === 'settings' ? 'page' : undefined}>
            <SettingsIcon size={18} /><span>Settings</span>
          </button>
          <div className="user-mini">
            <div className="user-avatar">{(me.user.full_name || '?').slice(0, 1).toUpperCase()}</div>
            <div><b>{me.user.full_name}</b><small>{ROLE_LABEL[ws.role] || ws.role}</small></div>
            <button className="icon-btn" onClick={onLogout} title="Sign out" aria-label="Sign out"><LogOut size={17} /></button>
          </div>
        </div>
      </aside>

      {mobileNav && <button className="scrim" onClick={() => setMobileNav(false)} aria-label="Close navigation" />}

      <main className="main-area" id="main" tabIndex={-1}>
        <header className="topbar">
          <button className="mobile-menu icon-btn" onClick={() => setMobileNav(true)} aria-label="Open menu"><Menu /></button>
          <div className="crumb">{ws.name} <span>/</span> <b>{info.label}</b></div>
          <div className="top-actions">
            <span className={`api-status ${health}`} role="status">
              <i /> {health === 'ok' ? 'Server online' : health === 'degraded' ? 'Server degraded' : health === 'down' ? 'Server unreachable' : 'Checking server…'}
            </span>
            <button className="help-btn" onClick={() => setAssistantOpen(true)}><CircleHelp size={16} /> Help</button>
          </div>
        </header>

        <div className="page-content">
          {me.email_available && me.user.email_verified === false && <VerifyBanner email={me.user.email} />}
          <div className="page-heading">
            <div>
              <div className="eyebrow">{ws.name.toUpperCase()}</div>
              <h1>{page === 'overview' ? `Hello, ${me.user.full_name.split(' ')[0]}` : info.title}</h1>
              <p>{info.text}</p>
            </div>
          </div>
          <Page key={`${page}-${ws.id}`} ctx={ctx} />
        </div>

        <footer className="footer">
          <span>Falcon Eye <i>·</i> AI Agent Firewall</span>
          <span>Powerful security. Simple experience.</span>
        </footer>
      </main>

      {!assistantOpen && (
        <button className="assistant-fab" onClick={() => setAssistantOpen(true)}><MessageCircle size={19} /><span>Ask Falcon Eye</span></button>
      )}
      {assistantOpen && <Assistant ws={ws} chat={chat} setChat={setChat} onClose={() => setAssistantOpen(false)} />}
      {creating && <NewWorkspaceDialog onClose={() => setCreating(false)} onCreated={async (w) => { setCreating(false); await reloadMe(); selectWs(w.id); toast('Workspace created.'); go('overview'); }} />}
      {showOnboarding && <Onboarding ws={ws} canWrite={canWrite} onFinish={() => { setSkipOnboarding(true); reloadMe(); }} />}
    </div>
  );
}

function Session({ onLogout, notice }) {
  const { data, error, loading, reload } = useFetch(() => api.get('/auth/me'), []);
  if (loading && !data) return <Splash text="Loading Falcon Eye…" />;
  if (error && !data) {
    return (
      <div className="splash"><img src="/falcon-eye-icon.png" alt="" width="72" height="72" />
        <div className="splash-box"><ErrorBox error={error} onRetry={reload} />
          <button className="ghost-btn" onClick={onLogout}>Sign out</button></div></div>
    );
  }
  if (!data || !data.workspaces || !data.workspaces.length) return <Splash text="Setting up your workspace…" />;
  return <Shell me={data} reloadMe={reload} onLogout={onLogout} notice={notice} />;
}

export default function App() {
  const [token, setTokenState] = useState(getToken);
  const [notice, setNotice] = useState('');
  const [emailRoute, setEmailRoute] = useState(readEmailRoute);

  // Remove the one-time token from the address bar as soon as it has been read.
  useEffect(() => {
    if (emailRoute) window.history.replaceState(null, '', window.location.pathname + window.location.search);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const on = () => { const r = readEmailRoute(); if (r) { setEmailRoute(r); window.history.replaceState(null, '', window.location.pathname + window.location.search); } };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);

  useEffect(() => {
    onAuthLost(() => { setTokenState(null); setNotice('Your session expired. Please sign in again.'); });
  }, []);

  const handleAuthed = (t) => { setToken(t); setNotice(''); setTokenState(t); };
  const handleLogout = useCallback(async () => {
    try { await api.post('/auth/logout'); } catch { /* token may already be invalid */ }
    setToken(null);
    setNotice('You have been signed out.');
    setTokenState(null);
  }, []);

  const finishEmailRoute = (opts = {}) => {
    if (opts.signedOut) { setToken(null); setTokenState(null); setNotice('Password changed. Please sign in.'); }
    setEmailRoute(null);
  };

  if (emailRoute) {
    return (
      <ToastProvider>
        {emailRoute.name === 'reset-password'
          ? <ResetPassword token={emailRoute.token} onDone={finishEmailRoute} />
          : <VerifyEmail token={emailRoute.token} onDone={finishEmailRoute} />}
      </ToastProvider>
    );
  }

  return (
    <ToastProvider>
      {token ? <Session onLogout={handleLogout} notice={notice} /> : <Auth onAuthed={handleAuthed} notice={notice} />}
    </ToastProvider>
  );
}
