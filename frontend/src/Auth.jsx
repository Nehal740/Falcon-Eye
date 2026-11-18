import { useState } from 'react';
import { Check, Eye, EyeOff, Lock, ShieldCheck, Zap, Users } from 'lucide-react';
import { api, friendly } from './api';

function Rule({ ok, children }) {
  return <li className={ok ? 'ok' : ''}><Check size={12} /> {children}</li>;
}

export default function Auth({ onAuthed, notice }) {
  const [mode, setMode] = useState('login');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const isLogin = mode === 'login';

  const longEnough = password.length >= 10;
  const mixed = /[A-Za-z]/.test(password) && /[0-9]/.test(password);

  async function submit(e) {
    e.preventDefault();
    setError(null);
    if (!isLogin && !longEnough) {
      setError({ message: 'Your password needs at least 10 characters.', hint: 'Try a short sentence, for example three random words.', fields: { password: 'At least 10 characters.' } });
      return;
    }
    setLoading(true);
    try {
      const body = isLogin ? { email, password } : { full_name: fullName, email, password };
      const data = await api.post(isLogin ? '/auth/login' : '/auth/register', body, { auth: false });
      onAuthed(data.access_token);
    } catch (err) {
      setError(friendly(err));
    } finally {
      setLoading(false);
    }
  }

  const fields = (error && error.fields) || {};

  return (
    <main className="auth-screen">
      <section className="auth-hero" aria-hidden="true">
        <img src="/falcon-eye-banner.jpg" alt="" />
        <h2>Powerful security. Simple experience.</h2>
        <ul>
          <li><ShieldCheck size={16} /> Every AI agent action is checked against your rules</li>
          <li><Users size={16} /> A human decides the sensitive ones</li>
          <li><Zap size={16} /> Every decision is recorded and easy to review</li>
        </ul>
      </section>

      <section className="auth-card">
        <div className="auth-brand">
          <img className="auth-logo" src="/falcon-eye-icon.png" alt="" width="52" height="52" />
          <div>
            <div className="auth-name">Falcon Eye</div>
            <div className="brand-caption">AI AGENT FIREWALL</div>
          </div>
        </div>

        <div className="auth-heading">
          <h1>{isLogin ? 'Welcome back' : 'Create your account'}</h1>
          <p>{isLogin ? 'Sign in to your security workspace.' : 'You will get your own private workspace right away.'}</p>
        </div>

        {notice && <div className="auth-info" role="status">{notice}</div>}

        <form onSubmit={submit} className="auth-form" noValidate>
          {!isLogin && (
            <div className="auth-field">
              <label htmlFor="fullName">Full name</label>
              <input id="fullName" className="auth-input" value={fullName} onChange={(e) => setFullName(e.target.value)}
                placeholder="Your full name" required minLength={2} autoComplete="name" aria-invalid={!!fields.full_name} />
              {fields.full_name && <small className="auth-field-error">{fields.full_name}</small>}
            </div>
          )}
          <div className="auth-field">
            <label htmlFor="email">Email address</label>
            <input id="email" className="auth-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com" required autoComplete="email" aria-invalid={!!fields.email} />
            {fields.email && <small className="auth-field-error">{fields.email}</small>}
          </div>
          <div className="auth-field">
            <label htmlFor="password">Password</label>
            <div className="pw-wrap">
              <input id="password" className="auth-input" type={show ? 'text' : 'password'} value={password}
                onChange={(e) => setPassword(e.target.value)} placeholder={isLogin ? 'Enter your password' : 'At least 10 characters'}
                required autoComplete={isLogin ? 'current-password' : 'new-password'} aria-invalid={!!fields.password} />
              <button type="button" className="pw-toggle" onClick={() => setShow(!show)} aria-label={show ? 'Hide password' : 'Show password'}>
                {show ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            {fields.password && <small className="auth-field-error">{fields.password}</small>}
            {!isLogin && (
              <ul className="pw-rules">
                <Rule ok={longEnough}>At least 10 characters</Rule>
                <Rule ok={mixed}>Letters and numbers (recommended)</Rule>
              </ul>
            )}
          </div>

          {error && (
            <div className="auth-error" role="alert">
              <b>{error.title ? `${error.title}. ` : ''}{error.message}</b>
              {error.hint && <span> {error.hint}</span>}
            </div>
          )}

          <button className="auth-submit" type="submit" disabled={loading}>
            {loading ? 'Please wait…' : isLogin ? 'Sign in to Falcon Eye' : 'Create account'}
          </button>
        </form>

        <div className="auth-switch">
          {isLogin ? 'New to Falcon Eye?' : 'Already have an account?'}
          <button type="button" onClick={() => { setMode(isLogin ? 'register' : 'login'); setError(null); }}>
            {isLogin ? 'Create an account' : 'Sign in'}
          </button>
        </div>
        <div className="auth-security"><Lock size={11} /> Passwords are hashed. Sessions expire automatically.</div>
      </section>
    </main>
  );
}
