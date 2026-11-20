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

export async function api(method, path, body) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(API_URL + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0);
  }

  let data = null;
  try { data = await res.json(); } catch { /* empty or non-JSON answer */ }

  if (res.status === 401 && token && !path.startsWith("/api/auth/")) {
    clearToken();
    location.href = "login.html";
  }
  if (!res.ok) throw new ApiError((data && data.error) || `Request failed (${res.status}).`, res.status);
  return data;
}

export const get = (path) => api("GET", path);
export const post = (path, body = {}) => api("POST", path, body);
export const patch = (path, body) => api("PATCH", path, body);
export const del = (path) => api("DELETE", path);
