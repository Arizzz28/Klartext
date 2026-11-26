// All communication with the backend goes through this file.
import { API_URL } from "./config.js";

const TOKEN_KEY = "chatisfying_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

// Where requests go. Normally the main server; if the Owner's PC server is online and this person uses it, the PC's address.
// If the PC does not answer, we go back to the main server at once (and tell the person).
let base = API_URL;
export const setBase = (url) => { base = url || API_URL; };
export const usingPc = () => base !== API_URL;

export async function api(method, path, body, _retry = true) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(base + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    if (base !== API_URL && _retry) {
      base = API_URL;
      window.dispatchEvent(new CustomEvent("chatisfying:pc-lost"));
      return api(method, path, body, false);
    }
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0);
  }

  let data = null;
  try { data = await res.json(); } catch { /* empty or non-JSON answer */ }

  if (res.status === 401 && token && !path.startsWith("/api/auth/")) {
    clearToken();
    location.href = "login.html";
  }
  if (res.status === 403 && data && data.code === "consent_required") window.dispatchEvent(new CustomEvent("chatisfying:consent"));
  if (!res.ok) {
    const err = new ApiError((data && data.error) || `Request failed (${res.status}).`, res.status);
    err.code = data && data.code;
    throw err;
  }
  return data;
}

const running = new Map();
export const get = (path) => {                // two identical GETs at the same time -> one request (less lag on a slow server)
  if (running.has(path)) return running.get(path);
  const p = api("GET", path).finally(() => running.delete(path));
  running.set(path, p);
  return p;
};
export const post = (path, body = {}) => api("POST", path, body);
export const put = (path, body = {}) => api("PUT", path, body);
export const patch = (path, body) => api("PATCH", path, body);
export const del = (path) => api("DELETE", path);
export const swallow = (promise, fallback = null) => promise.catch(() => fallback);
