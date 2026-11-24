// Main logic: builds the page frame (sidebar, list, main area) and switches pages by URL hash.
import { get, post } from "./api.js";
import { logout, requireLogin } from "./auth.js";
import { startLoading } from "./loading.js";
import { avatar, brand, h, icon, modal, toast } from "./ui.js";
import * as chats from "./pages/chats.js";
import * as groups from "./pages/groups.js";
import * as profile from "./pages/profile.js";
import * as settings from "./pages/settings.js";
import * as admin from "./pages/admin.js";

const pages = { chats, groups, profile, settings, admin };
const NAV = [
  { page: "chats", label: "Chats", icon: "chats" },
  { page: "groups", label: "Groups", icon: "groups" },
  { page: "profile", label: "Profile", icon: "profile" },
  { page: "settings", label: "Settings", icon: "settings" },
  { page: "admin", label: "Admin", icon: "admin", roles: ["admin", "moderator"] },
];

// Shared with all pages
export const state = { me: null, config: {}, refreshInvites, onMeChanged: renderMe };

let shell, listHost, mainHost, meBox, inviteBadge, bannerBox;
const navLinks = {};
let cleanup = null;
let routeToken = 0;

async function init() {
  const loader = startLoading();
  const app = document.getElementById("app");
  try {
    state.me = await requireLogin();
  } catch (e) {
    loader.done();
    app.className = "boot";
    app.replaceChildren(h("p", {}, e.message), h("button", { class: "btn primary", onClick: () => location.reload() }, "Try again"));
    return;
  }
  if (!state.me) return;

  try { state.config = await get("/api/config"); } catch { /* the app works without it */ }

  buildShell(app);
  window.addEventListener("storage", (e) => { if (e.key === "chatisfying_token") location.reload(); });
  window.addEventListener("hashchange", route);
  await route();
  refreshInvites();
  setInterval(refreshInvites, 15000);
  loader.done();
  if (state.me.must_change_password) forcePasswordChange();
}

function buildShell(app) {
  inviteBadge = h("span", { class: "badge", hidden: true, "aria-label": "Pending invitations" });
  const links = NAV.filter((n) => !n.roles || n.roles.includes(state.me.role)).map((n) => {
    const label = n.page === "admin" && state.me.role === "moderator" ? "Moderation" : n.label;
    const a = h("a", { class: "nav-link", href: `#/${n.page}` }, icon(n.icon), h("span", { class: "label" }, label));
    if (n.page === "groups") a.append(inviteBadge);
    navLinks[n.page] = a;
    return a;
  });
  meBox = h("div", { class: "me" });
  const sidebar = h("nav", { class: "sidebar", "aria-label": "Main navigation" }, brand(), h("div", { class: "nav" }, links), meBox);
  listHost = h("aside", { class: "list" });
  mainHost = h("main", { class: "main" });
  shell = h("div", { class: "shell" }, sidebar, listHost, mainHost);
  bannerBox = h("div", { class: "announcement", role: "status", hidden: true });
  app.className = "ready";
  app.replaceChildren(bannerBox, shell);
  drawBanner();
  renderMe();
}

function drawBanner() {
  const text = state.config.announcement || "";
  bannerBox.textContent = text;
  bannerBox.hidden = !text;
}

function renderMe() {
  meBox.replaceChildren(
    avatar(state.me, "sm"),
    h("div", { class: "me-text label" }, h("strong", {}, state.me.display_name), h("span", {}, "@" + state.me.username)),
    h("button", { class: "icon-btn label", type: "button", title: "Log out", "aria-label": "Log out", onClick: logout }, icon("logout")));
}

async function refreshInvites() {
  try {
    const invites = await get("/api/invitations");
    inviteBadge.textContent = invites.length;
    inviteBadge.hidden = invites.length === 0;
    state.config = { ...state.config, ...(await get("/api/config")) };      // also picks up a new announcement
    drawBanner();
  } catch { /* not important enough to show an error */ }
}

// Accounts created or reset by an admin must choose their own password before using the app.
function forcePasswordChange() {
  const input = (autocomplete) => h("input", { class: "input", type: "password", required: true, minlength: "8", autocomplete });
  const cur = input("current-password"), next = input("new-password"), again = input("new-password");
  const msg = h("p", { class: "form-msg", role: "alert" });
  const field = (label, el) => h("label", { class: "field" }, h("span", { class: "field-label" }, label), el);
  const form = h("form", { class: "dialog-body" },
    h("p", {}, "An admin set your password. Please choose a new one before you continue."),
    field("Current password", cur), field("New password (min. 8 characters)", next), field("Repeat new password", again),
    msg, h("div", { class: "dialog-actions" }, h("button", { class: "btn primary", type: "submit" }, "Change password")));
  modal("Choose a new password", form, null, false);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (next.value !== again.value) { msg.textContent = "The new passwords don't match."; msg.className = "form-msg error"; return; }
    try {
      await post("/api/me/password", { current: cur.value, new: next.value });
      toast("Password changed. Please log in again.");
      setTimeout(logout, 1200);
    } catch (err) { msg.textContent = err.message; msg.className = "form-msg error"; }
  });
}

async function route() {
  if (cleanup) { try { cleanup(); } catch { /* ignore */ } cleanup = null; }
  const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  const name = parts[0] || "chats";
  const arg = parts[1] || null;
  const page = pages[name];
  const allowed = name !== "admin" || ["admin", "moderator"].includes(state.me.role);
  if (!page || !allowed) { location.hash = "#/chats"; return; }

  shell.classList.toggle("no-list", !page.usesList);
  shell.classList.toggle("chat-open", Boolean(arg));
  for (const [key, link] of Object.entries(navLinks)) {
    link.classList.toggle("active", key === name);
    if (key === name) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
  }

  // Every page gets fresh containers. If the user navigates away while a page is still loading,
  // the old page only touches containers that are no longer on screen.
  const list = h("div", { class: "pane-inner" });
  const main = h("div", { class: "pane-inner" });
  listHost.replaceChildren(list);
  mainHost.replaceChildren(main);

  const token = ++routeToken;
  const result = await page.render({ list, main, arg, state });
  if (token !== routeToken) { if (result) result(); return; }
  cleanup = result || null;
}

init();
