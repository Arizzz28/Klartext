// Login, registration and logout. Also drives the login page (login.html).
import { api, clearToken, get, getToken, post, setToken } from "./api.js";
import { brand, h } from "./ui.js";

export async function login(username, password) {
  const data = await post("/api/auth/login", { username, password });
  setToken(data.token);
  return data.user;
}

export async function logout() {
  try { await post("/api/auth/logout"); } catch { /* token may already be invalid */ }
  clearToken();
  location.href = "login.html";
}

export const registerStart = (username, email) => post("/api/auth/register/start", { username, email });
export const registerVerify = (username, code) => post("/api/auth/register/verify", { username, code });
export const registerComplete = (username, password) => post("/api/auth/register/complete", { username, password });

// Returns the logged-in user, or sends the browser to the login page.
export async function requireLogin() {
  if (!getToken()) { location.replace("login.html"); return null; }
  return get("/api/me");
}

// ---------- login page ----------
function field(label, attrs) {
  const input = h("input", { class: "input", ...attrs });
  return { input, row: h("label", { class: "field" }, h("span", { class: "field-label" }, label), input) };
}

async function run(button, msg, fn) {
  button.disabled = true;
  msg.textContent = "";
  msg.className = "form-msg";
  try { await fn(); }
  catch (e) { msg.textContent = e.message; msg.className = "form-msg error"; }
  finally { button.disabled = false; }
}

function initLoginPage() {
  if (getToken()) { location.replace("index.html"); return; }

  const root = document.getElementById("login-root");
  const reg = { username: "", email: "" };
  let mode = "login";          // "login" | "register"
  let step = "start";          // "start" | "code" | "password" | "done"
  let notice = "";

  function tabs() {
    const tab = (id, label) => h("button", {
      class: `tab${mode === id ? " active" : ""}`, type: "button", role: "tab",
      "aria-selected": String(mode === id),
      onClick: () => { mode = id; step = "start"; notice = ""; draw(); },
    }, label);
    return h("div", { class: "tabs", role: "tablist" }, tab("login", "Log in"), tab("register", "Create account"));
  }

  function loginForm() {
    const u = field("Username", { type: "text", autocomplete: "username", required: true, autofocus: true });
    const p = field("Password", { type: "password", autocomplete: "current-password", required: true });
    const btn = h("button", { class: "btn primary block", type: "submit" }, "Log in");
    const msg = h("p", { class: notice ? "form-msg ok" : "form-msg", role: "alert" }, notice);
    return h("form", {
      onSubmit: (e) => {
        e.preventDefault();
        run(btn, msg, async () => { await login(u.input.value.trim(), p.input.value); location.href = "index.html"; });
      },
    }, u.row, p.row, msg, btn);
  }

  function registerForm() {
    const msg = h("p", { class: "form-msg", role: "alert" });
    if (step === "start") {
      const u = field("Username", { type: "text", autocomplete: "username", required: true, minlength: "3", maxlength: "20", value: reg.username });
      const m = field("Email", { type: "email", autocomplete: "email", required: true, value: reg.email });
      const btn = h("button", { class: "btn primary block", type: "submit" }, "Send code");
      return h("form", {
        onSubmit: (e) => {
          e.preventDefault();
          run(btn, msg, async () => {
            reg.username = u.input.value.trim(); reg.email = m.input.value.trim();
            await registerStart(reg.username, reg.email);
            step = "code"; draw();
          });
        },
      }, h("p", { class: "hint" }, "Your username has to be on the whitelist. Ask an admin if it isn't."), u.row, m.row, msg, btn);
    }
    if (step === "code") {
      const c = field("6-digit code", { type: "text", inputmode: "numeric", autocomplete: "one-time-code", required: true, maxlength: "6", pattern: "[0-9]{6}" });
      const btn = h("button", { class: "btn primary block", type: "submit" }, "Verify email");
      return h("form", {
        onSubmit: (e) => {
          e.preventDefault();
          run(btn, msg, async () => { await registerVerify(reg.username, c.input.value.trim()); step = "password"; draw(); });
        },
      }, h("p", { class: "hint" }, `We sent a code to ${reg.email}. It is valid for 10 minutes.`), c.row, msg, btn);
    }
    if (step === "password") {
      const p1 = field("Password (min. 8 characters)", { type: "password", autocomplete: "new-password", required: true, minlength: "8" });
      const p2 = field("Repeat password", { type: "password", autocomplete: "new-password", required: true, minlength: "8" });
      const btn = h("button", { class: "btn primary block", type: "submit" }, "Create account");
      return h("form", {
        onSubmit: (e) => {
          e.preventDefault();
          run(btn, msg, async () => {
            if (p1.input.value !== p2.input.value) throw new Error("The passwords don't match.");
            const res = await registerComplete(reg.username, p1.input.value);
            notice = res.message; mode = "login"; step = "start"; draw();
          });
        },
      }, p1.row, p2.row, msg, btn);
    }
    return h("div");
  }

  function draw() {
    root.replaceChildren(h("div", { class: "login-card" },
      brand(true), tabs(), mode === "login" ? loginForm() : registerForm()));
    root.querySelector("input")?.focus();
  }
  draw();
}

if (document.body.dataset.page === "login") initLoginPage();
