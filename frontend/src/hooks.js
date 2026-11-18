import { useCallback, useEffect, useRef, useState } from 'react';

// Loads data, optionally re-loading on an interval (paused while the tab is hidden).
export function useFetch(fn, deps, { interval = 0 } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const counter = useRef(0);

  const load = useCallback(async (silent) => {
    const mine = ++counter.current;
    if (!silent) setState((s) => ({ ...s, loading: true }));
    try {
      const data = await fnRef.current();
      if (mine === counter.current) setState({ data, error: null, loading: false });
    } catch (e) {
      if (mine === counter.current) setState((s) => ({ data: s.data, error: e, loading: false }));
    }
  }, []);

  useEffect(() => { load(false); /* eslint-disable-next-line */ }, deps);

  useEffect(() => {
    if (!interval) return undefined;
    const tick = () => { if (!document.hidden) load(true); };
    const timer = setInterval(tick, interval);
    document.addEventListener('visibilitychange', tick);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', tick); };
  }, [interval, load]);

  return { ...state, reload: () => load(true), reloadLoud: () => load(false) };
}

export function useDebounced(value, delay = 350) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}
