import { useEffect, useRef, useState } from 'react';
import { Bot, Send, X } from 'lucide-react';
import RichText from './RichText';
import { api, friendly } from '../api';
import { useFetch } from '../hooks';

const SUGGESTIONS = [
  'How do I connect my first agent?',
  'What does REQUIRE_APPROVAL mean?',
  'Why was my action blocked?',
  'How do I write a policy?',
];

export default function Assistant({ ws, chat, setChat, onClose }) {
  const status = useFetch(() => api.get(`/workspaces/${ws.id}/assistant/status`), [ws.id]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const live = status.data && status.data.live_ai_configured;

  useEffect(() => { inputRef.current?.focus(); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }); }, [chat, busy]);
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function send(text) {
    const q = text.trim();
    if (!q || busy) return;
    const history = chat.filter((m) => !m.error).slice(-6).map((m) => ({ role: m.role, text: m.text.slice(0, 1500) }));
    setChat((c) => [...c, { role: 'user', text: q }]);
    setInput(''); setBusy(true);
    try {
      const d = await api.post(`/workspaces/${ws.id}/assistant/chat`, { message: q, history });
      setChat((c) => [...c, { role: 'assistant', text: d.answer, mode: d.mode, sources: d.sources || [], notice: d.notice }]);
    } catch (e) {
      const f = friendly(e);
      setChat((c) => [...c, { role: 'assistant', error: true, text: `${f.message} ${f.hint}` }]);
    } finally { setBusy(false); }
  }

  return (
    <aside className="assistant-panel" role="dialog" aria-label="Falcon Eye assistant">
      <div className="assistant-header">
        <div className="assistant-avatar"><Bot size={20} /></div>
        <div>
          <b>Falcon Eye assistant</b>
          <small><i className={live ? '' : 'off'} /> {status.data ? (live ? 'AI model connected' : 'Documentation search only') : 'Checking…'}</small>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close assistant"><X size={18} /></button>
      </div>
      <div className="assistant-notice">
        {status.data && !live
          ? 'No AI model is configured on this server, so answers are passages from the documentation.'
          : 'The assistant only explains. It cannot approve, change policies or run actions.'}
      </div>
      <div className="chat-history" aria-live="polite">
        {chat.length === 0 && (
          <div className="chat-empty">
            <p>Hi! Ask me how Falcon Eye works. For example:</p>
            <div className="chips col">{SUGGESTIONS.map((s) => <button key={s} className="chip" onClick={() => send(s)}>{s}</button>)}</div>
          </div>
        )}
        {chat.map((m, i) => (
          <div key={i} className={`chat-message ${m.role} ${m.error ? 'error' : ''}`}>
            <div className="chat-text">{m.role === 'assistant' && !m.error ? <RichText text={m.text} /> : m.text}</div>
            {m.role === 'assistant' && m.mode && <span className={`mode-badge ${m.mode === 'ai' ? 'llm' : 'docs_only'}`}>{m.mode === 'ai' ? 'AI answer' : 'From documentation'}</span>}
            {m.notice && <div className="chat-notice">{m.notice}</div>}
            {m.sources && m.sources.length > 0 && <div className="chat-sources">Sources: {m.sources.map((s) => s.title).join(', ')}</div>}
          </div>
        ))}
        {busy && <div className="chat-message assistant">Thinking…</div>}
        <div ref={endRef} />
      </div>
      <form className="chat-form" onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <input ref={inputRef} aria-label="Your question" value={input} maxLength={1000} onChange={(e) => setInput(e.target.value)} placeholder="Ask about Falcon Eye…" />
        <button type="submit" aria-label="Send" disabled={busy || !input.trim()}><Send size={16} /></button>
      </form>
    </aside>
  );
}
