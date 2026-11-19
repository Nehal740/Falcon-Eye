import { useEffect, useRef, useState } from 'react';
import { Check, Eye, EyeOff, MailCheck } from 'lucide-react';
import { api, friendly } from './api';
import { useToast } from './components/ui';

function Brand() {
  return (
    <div className="auth-brand">
      <img className="auth-logo" src="/falcon-eye-icon.png" alt="" width="52" height="52" />
      <div>
        <div className="auth-name">Falcon Eye</div>
        <div className="brand-caption">AI AGENT FIREWALL</div>
      </div>
    </div>
  );
}

function Shell({ title, text, children }) {
  return (
    <main className="auth-screen">
      <section className="auth-card">
        <Brand />
        <div className="auth-heading"><h1>{title}</h1>{text && <p>{text}</p>}</div>
        {children}
      </section>
    </main>
  );
}

function ErrorLine({ error }) {
  if (!error) return null;
  return (
    <div className="auth-error" role="alert">
      <b>{error.message}</b>{error.hint && <span> {error.hint}</span>}
    </div>
  );
}

// Opened from the link in the "choose a new password" email.
export function ResetPassword({ token, onDone }) {
  const [password, setPassword] = useState('');
  const [again, setAgain] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState('');

  const longEnough = password.length >= 10;
  const mixed = /[A-Za-z]/.test(password) && /[0-9]/.test(password);
  const matches = password.length > 0 && password === again;

  async function submit(e) {
    e.preventDefault();
    setError(null);
    if (!token) { setError({ message: 'This link is incomplete.', hint: 'Open the link from your email again, or request a new one.' }); return; }
    if (!longEnough || !mixed) { setError({ message: 'Your password needs at least 10 characters, with letters and numbers.' }); return; }
    if (!matches) { setError({ message: 'The two passwords are not the same.' }); return; }
    setLoading(true);
    try {
      const data = await api.post('/auth/reset-password', { token, new_password: password }, { auth: false });
      setDone(data.message);
    } catch (err) {
      setError(friendly(err));
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <Shell title="Password changed">
        <div className="auth-info" role="status">{done}</div>
        <button className="auth-submit" type="button" onClick={() => onDone({ signedOut: true })}>Go to sign in</button>
      </Shell>
    );
  }

  return (
    <Shell title="Choose a new password" text="Pick a password you do not use anywhere else.">
      <form className="auth-form" onSubmit={submit} noValidate>
        <div className="auth-field">
          <label htmlFor="np">New password</label>
          <div className="pw-wrap">
            <input id="np" className="auth-input" type={show ? 'text' : 'password'} value={password}
              onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" placeholder="At least 10 characters" required />
            <button type="button" className="pw-toggle" onClick={() => setShow(!show)} aria-label={show ? 'Hide password' : 'Show password'}>
              {show ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
          <ul className="pw-rules">
            <li className={longEnough ? 'ok' : ''}><Check size={12} /> At least 10 characters</li>
            <li className={mixed ? 'ok' : ''}><Check size={12} /> Letters and numbers</li>
          </ul>
        </div>
        <div className="auth-field">
          <label htmlFor="np2">Repeat the password</label>
          <input id="np2" className="auth-input" type={show ? 'text' : 'password'} value={again}
            onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
        </div>
        <ErrorLine error={error} />
        <button className="auth-submit" type="submit" disabled={loading}>{loading ? 'Please wait…' : 'Change password'}</button>
      </form>
      <div className="auth-switch"><button type="button" onClick={() => onDone({ signedOut: false })}>Back to sign in</button></div>
    </Shell>
  );
}

// Opened from the link in the "confirm your email" email.
export function VerifyEmail({ token, onDone }) {
  const [state, setState] = useState({ status: 'loading', message: '', error: null });
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true; // React may run effects twice in development; the link works only once
    if (!token) { setState({ status: 'error', error: { message: 'This link is incomplete.', hint: 'Open the link from your email again.' } }); return; }
    api.post('/auth/verify-email', { token }, { auth: false })
      .then((d) => setState({ status: 'ok', message: d.message }))
      .catch((err) => setState({ status: 'error', error: friendly(err) }));
  }, [token]);

  return (
    <Shell title={state.status === 'ok' ? 'Email confirmed' : state.status === 'error' ? 'We could not confirm your email' : 'Confirming your email…'}>
      {state.status === 'ok' && <div className="auth-info" role="status"><MailCheck size={14} /> {state.message}</div>}
      {state.status === 'error' && <ErrorLine error={state.error} />}
      {state.status !== 'loading' && (
        <button className="auth-submit" type="button" onClick={() => onDone({})}>Continue to Falcon Eye</button>
      )}
    </Shell>
  );
}

// Shown inside the app until the address is confirmed.
export function VerifyBanner({ email }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [hidden, setHidden] = useState(false);
  if (hidden) return null;
  async function resend() {
    setBusy(true);
    try {
      const d = await api.post('/auth/resend-verification');
      toast(d.message);
    } catch (err) {
      toast(friendly(err).message, 'error');
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="verify-banner" role="status">
      <span><b>Please confirm your email address.</b> We sent a link to {email}.</span>
      <span className="verify-actions">
        <button className="ghost-btn" onClick={resend} disabled={busy}>{busy ? 'Sending…' : 'Resend email'}</button>
        <button className="ghost-btn" onClick={() => setHidden(true)} aria-label="Hide this message">Hide</button>
      </span>
    </div>
  );
}
