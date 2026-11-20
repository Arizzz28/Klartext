// Main logic: builds the page frame (sidebar, list, main area) and switches pages by URL hash.
import { get } from "./api.js";
import { logout, requireLogin } from "./auth.js";
import { avatar, brand, h, icon } from "./ui.js";
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
  { page: "admin", label: "Admin", icon: "admin", adminOnly: true },
];

// Shared with all pages
export const state = { me: null, refreshInvites, onMeChanged: renderMe };

let shell, listHost, mainHost, meBox, inviteBadge;
const navLinks = {};
let cleanup = null;
let routeToken = 0;

async function init() {
  const app = document.getElementById("app");
  try {
    state.me = await requireLogin();
  } catch (e) {
    app.className = "boot";
    app.replaceChildren(h("p", {}, e.message), h("button", { class: "btn primary", onClick: () => location.reload() }, "Try again"));
    return;
  }
  if (!state.me) return;

  buildShell(app);
  window.addEventListener("hashchange", route);
  route();
  refreshInvites();
  setInterval(refreshInvites, 15000);
}

function buildShell(app) {
  inviteBadge = h("span", { class: "badge", hidden: true, "aria-label": "Pending invitations" });
  const links = NAV.filter((n) => !n.adminOnly || state.me.is_admin).map((n) => {
    const a = h("a", { class: "nav-link", href: `#/${n.page}` }, icon(n.icon), h("span", { class: "label" }, n.label));
    if (n.page === "groups") a.append(inviteBadge);
    navLinks[n.page] = a;
    return a;
  });
  meBox = h("div", { class: "me" });
  const sidebar = h("nav", { class: "sidebar", "aria-label": "Main navigation" }, brand(), h("div", { class: "nav" }, links), meBox);
  listHost = h("aside", { class: "list" });
  mainHost = h("main", { class: "main" });
  shell = h("div", { class: "shell" }, sidebar, listHost, mainHost);
  app.className = "";
  app.replaceChildren(shell);
  renderMe();
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
  } catch { /* not important enough to show an error */ }
}

async function route() {
  if (cleanup) { try { cleanup(); } catch { /* ignore */ } cleanup = null; }
  const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  const name = parts[0] || "chats";
  const arg = parts[1] || null;
  const page = pages[name];
  if (!page || (name === "admin" && !state.me.is_admin)) { location.hash = "#/chats"; return; }

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
