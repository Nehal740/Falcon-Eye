// Falcon Eye API client: token storage, automatic refresh, friendly errors.
const BASE = '/api';
const TOKEN_KEY = 'falcon_eye_token';
const REFRESH_WINDOW_MS = 10 * 60 * 1000;

let authLostHandler = null;
export const onAuthLost = (fn) => { authLostHandler = fn; };

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* storage may be unavailable */ }
}

function tokenExpiry(token) {
  try {
    const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(part)).exp * 1000;
  } catch { return 0; }
}

export class ApiError extends Error {
  constructor(status, code, message, hint, fields) {
    super(message);
    this.status = status;
    this.code = code;
    this.hint = hint || '';
    this.fields = fields || null;
  }
}

// The backend lists field problems as [{field, message}]; forms want {field: message}.
function fieldMap(fields) {
  if (!fields) return null;
  if (!Array.isArray(fields)) return fields;
  const out = {};
  fields.forEach((f) => { if (f && f.field && !(f.field in out)) out[f.field] = f.message; });
  return out;
}

async function raw(method, path, body, token, signal) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  let res;
  try {
    res = await fetch(BASE + path, {
      method, headers, signal,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    if (e && e.name === 'AbortError') throw e;
    throw new ApiError(0, 'network', 'Falcon Eye could not reach the server.');
  }
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON body */ }
  if (!res.ok) {
    const err = data && data.error;
    if (err) throw new ApiError(res.status, err.code || 'error', err.message, err.hint, fieldMap(err.fields));
    if (res.status === 502 || res.status === 503 || res.status === 504) {
      throw new ApiError(res.status, 'network', 'The Falcon Eye backend is not responding.');
    }
    throw new ApiError(res.status, 'server_error', 'The server returned an unexpected response.');
  }
  return data;
}

let refreshing = null;
export async function refreshIfNeeded(force = false) {
  const token = getToken();
  if (!token) return;
  const exp = tokenExpiry(token);
  if (!force && (!exp || exp - Date.now() > REFRESH_WINDOW_MS)) return;
  if (!refreshing) {
    refreshing = raw('POST', '/auth/refresh', undefined, token)
      .then((d) => { if (d && d.access_token) setToken(d.access_token); })
      .catch(() => { /* the real request will report a 401 if the token is dead */ })
      .finally(() => { refreshing = null; });
  }
  await refreshing;
}

async function request(method, path, body, opts = {}) {
  const useAuth = opts.auth !== false;
  if (useAuth) await refreshIfNeeded();
  try {
    return await raw(method, path, body, useAuth ? getToken() : null, opts.signal);
  } catch (e) {
    if (useAuth && e instanceof ApiError && e.status === 401 &&
        ['not_signed_in'].includes(e.code)) {
      setToken(null);
      if (authLostHandler) authLostHandler();
    }
    throw e;
  }
}

export const api = {
  get: (p, o) => request('GET', p, undefined, o),
  post: (p, b, o) => request('POST', p, b === undefined ? {} : b, o),
  put: (p, b, o) => request('PUT', p, b, o),
  patch: (p, b, o) => request('PATCH', p, b, o),
  del: (p, o) => request('DELETE', p, undefined, o),
};

export function qs(params) {
  const u = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') u.set(k, v);
  });
  const s = u.toString();
  return s ? `?${s}` : '';
}

const KNOWN = {
  network: ['Can’t reach Falcon Eye', 'Make sure the backend is running (python -m uvicorn main:app --reload) and then try again.'],
  not_allowed: ['You don’t have permission', 'Ask a workspace owner or admin to make this change or to upgrade your role.'],
  forbidden: ['You don’t have permission', 'Ask a workspace owner or admin to make this change or to upgrade your role.'],
  not_found: ['We couldn’t find that', 'It may have been deleted. Refresh the page and try again.'],
  rate_limited: ['Too many attempts', 'Wait a moment and try again.'],
  account_locked: ['Account temporarily locked', 'Too many failed sign-ins. Wait a few minutes before trying again.'],
  invalid_credentials: ['Sign-in failed', 'Check your email and password. Passwords are case-sensitive.'],
  validation_error: ['Please check the form', 'Fix the highlighted fields and try again.'],
  conflict: ['That conflicts with existing data', 'Change the value and try again.'],
  already_decided: ['Already decided', 'Someone else already handled this request, or it expired. The list has been refreshed.'],
  server_error: ['Something went wrong on our side', 'Try again in a moment. If it keeps happening, check the backend logs.'],
};

export function friendly(err) {
  if (!(err instanceof ApiError)) {
    return { title: 'Something went wrong', message: (err && err.message) || 'An unexpected error occurred.', hint: 'Refresh the page and try again.', fields: null };
  }
  const k = KNOWN[err.code] || [];
  return {
    title: k[0] || 'Something went wrong',
    message: err.code === 'network' ? 'Falcon Eye could not reach the server.' : err.message,
    hint: err.hint || k[1] || 'Try again. If the problem continues, check the backend logs.',
    fields: err.fields,
  };
}
