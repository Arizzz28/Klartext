// Main logic: builds the page frame (sidebar, list, main area, tab bubble) and switches pages by URL hash.
import { get, post, put } from "./api.js";
import { logout, requireLogin } from "./auth.js";
import { showConsent } from "./consent.js";
import { startLoading } from "./loading.js";
import { openTabEditor } from "./tabeditor.js";
import { TABS, availableTabs, can, pinnedTabs, startTabId } from "./tabs.js";
import { avatar, brand, confirmDialog, debounce, formatTime, h, icon, modal, rankTag, setBadge, toast } from "./ui.js";
import { enablePush, needsHomeScreen, pushState, pushSupported } from "./push.js";

const DEFAULT_LAYOUT = { side: "left", list_side: "inner", list_width: 330, rail: true };

// Shared with all pages
export const state = {
  me: null, config: {}, unread: { dm: {}, group: {}, chats: 0, groups: 0, notifications: 0, invitations: 0, whatsnew: 0 },
  can: (perm) => can(state.me, perm), refreshUnread, onMeChanged, logout,
  refreshInvites: () => refreshUnread(),
  reloadMe: async () => { state.me = await get("/api/me"); onMeChanged(); },
};

let shell, listHost, mainHost, meBox, bannerBox, sidebarEl, navBox, bubbleEl, resizerEl;
const badgeEls = {};
let cleanup = null;
let routeToken = 0;
let started = false;

async function init() {
  const loader = startLoading();
  const app = document.getElementById("app");
  try {
    state.me = await requireLogin();
  } catch (e) {
    loader.done();
    app.className = "boot";
    // "Log out" is here so a blocked or broken account never gets stuck on this screen.
    app.replaceChildren(h("p", {}, e.message), h("button", { class: "btn primary", onClick: () => location.reload() }, "Try again"),
      h("button", { class: "btn", onClick: logout }, "Log out"));
    return;
  }
  if (!state.me) return;
  try { state.config = await get("/api/config"); } catch { /* the app works without it */ }
  window.addEventListener("chatisfying:pc-lost", () => toast("The PC server is not reachable. Using the normal server.", "info"));
  if (state.can("pc.backend") && state.me.prefs?.use_pc) {         // the Owner's PC may do the computing while it is online
    const { setBase: sb } = await import("./api.js");
    const check = async (first) => {
      try {
        const r = await get("/api/pc/route");
        sb(r.url);
        if (first && r.message) toast(r.message, "info");
      } catch { /* stay on the main server */ }
    };
    await check(true);
    setInterval(() => { if (!document.hidden) check(false); }, 60000);
  }
  window.addEventListener("storage", (e) => { if (e.key === "chatisfying_token") location.reload(); });
  window.addEventListener("chatisfying:consent", () => needConsent());
  window.addEventListener("chatisfying:read", () => refreshUnread());

  applyDesign();
  if (!state.me.consent_ok) {                 // nothing else loads until the current texts are accepted
    app.className = "boot";
    app.replaceChildren();
    loader.done();
    needConsent();
    return;
  }
  await start(app, loader);
}

function needConsent() {
  if (document.querySelector(".consent")) return;
  showConsent(state, () => location.reload());
}

async function start(app, loader) {
  if (started) return;
  started = true;
  buildShell(app);
  // Opened without a page in the address (fresh login, home-screen icon): go to the start page. replaceState instead
  // of changing location.hash, so the Back button does not bounce the person back to this moment.
  if (!/^#\/?[^/]/.test(location.hash)) history.replaceState(null, "", "#/" + startTabId(state.me, state.config));
  window.addEventListener("hashchange", route);
  await refreshUnread();
  await route();
  setInterval(() => { if (!document.hidden) refreshUnread(); }, 10000);
  if (state.can("tabs.prank")) {                         // a waiting prank (only if this person switched pranks on)
    const { get: g2 } = await import("./api.js"), { showPrank } = await import("./pages/prank.js");
    setInterval(async () => { if (document.hidden) return; try { const r = await g2("/api/prank/inbox"); if (r.prank) showPrank(r.prank.kind, r.prank.from); } catch { /* ignore */ } }, 20000);
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshUnread(); });
  loader?.done();
  if (state.me.must_change_password) forcePasswordChange();
  else maybeOfferPush();
}

// ---------------------------------------------------------------- design and layout
function applyDesign() {
  document.documentElement.dataset.design = state.me?.design || "classic";
}

function layout() {
  const mine = state.can("layout.move") ? state.me.prefs?.layout : null;
  return { ...DEFAULT_LAYOUT, ...(mine || {}) };
}

function applyLayout(page) {
  const lay = layout();
  shell.classList.toggle("side-right", lay.side === "right");
  shell.classList.toggle("list-right", lay.list_side === "outer");
  // Is the chat list on the right-hand side of the chat? (needed to know which way the drag handle works)
  shell.classList.toggle("list-after", (lay.side === "left") === (lay.list_side === "outer"));
  shell.classList.toggle("rail", Boolean(lay.rail));
  shell.style.setProperty("--list-w", `${lay.list_width}px`);
  if (page) shell.classList.toggle("no-list", !page.usesList);
}

async function saveLayout(changes) {
  if (!state.can("layout.move")) return;
  const next = { ...layout(), ...changes };
  try { state.me = await put("/api/me/prefs", { layout: next }); } catch (e) { toast(e.message, "error"); }
  applyLayout();
}

// ---------------------------------------------------------------- shell
function buildShell(app) {
  navBox = h("div", { class: "nav" });
  meBox = h("div", { class: "me" });
  sidebarEl = h("nav", { class: "sidebar", "aria-label": "Main navigation" }, brand(), navBox, meBox);
  listHost = h("aside", { class: "list" });
  resizerEl = h("div", { class: "resizer", role: "separator", "aria-orientation": "vertical", title: "Drag to change the width", hidden: !state.can("layout.move") });
  mainHost = h("main", { class: "main" });
  shell = h("div", { class: "shell v3" }, sidebarEl, listHost, mainHost);
  setupResizer(resizerEl);
  bannerBox = h("div", { class: "announcement", role: "status", hidden: true });
  app.className = "ready";
  app.replaceChildren(bannerBox, shell);
  drawBanner();
  drawNav();
  renderMe();
  applyLayout();
  drawBubble();
}

function setupResizer(handle) {
  handle.addEventListener("pointerdown", (e) => {
    if (!state.can("layout.move")) return;
    e.preventDefault();
    handle.setPointerCapture?.(e.pointerId);
    // Dragging towards the chat makes the list wider. If the list sits right of the chat, "towards" is to the left.
    const start = e.clientX, from = layout().list_width, dir = shell.classList.contains("list-after") ? -1 : 1;
    let width = from;
    const move = (ev) => {
      width = Math.min(520, Math.max(220, Math.round(from + (ev.clientX - start) * dir)));
      shell.style.setProperty("--list-w", `${width}px`);
    };
    const up = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
      saveLayout({ list_width: width });
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
  });
}

function drawBanner() {
  const text = state.config.announcement || "";
  bannerBox.textContent = text;
  bannerBox.hidden = !text;
}

function tabBadge(id) {
  const u = state.unread;
  if (id === "chats") return u.chats;
  if (id === "groups") return u.groups + u.invitations;
  if (id === "whatsnew") return u.whatsnew;
  return 0;
}

function navLink(tab) {
  const badge = h("span", { class: "badge", hidden: true, "aria-label": "Unread" });
  badgeEls[tab.id] = badge;
  const a = h("a", { class: "nav-link", href: `#/${tab.id}`, "data-tab": tab.id, title: tab.label },
    icon(tab.icon), h("span", { class: "label" }, tab.id === "admin" && !state.can("admin.users") ? "Moderation" : tab.label), badge);
  setBadge(badge, tabBadge(tab.id));
  return a;
}

function drawNav() {
  const pinned = pinnedTabs(state.me);
  const more = h("button", { class: "nav-link nav-more", type: "button", title: "All tabs", onClick: () => toggleBubblePopup(true) },
    icon("grid"), h("span", { class: "label" }, "More"));
  navBox.replaceChildren(...pinned.map(navLink), more);
  markActive();
}

function markActive() {
  const name = currentName();
  for (const a of navBox?.querySelectorAll?.(".nav-link[data-tab]") || []) {
    const on = a.dataset.tab === name;
    a.classList.toggle("active", on);
    if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
}

function renderMe() {
  const lay = layout();
  const tools = [];
  tools.push(h("button", { class: "icon-btn label", type: "button", title: "Notifications", "aria-label": "Notifications", onClick: showNotifications },
    icon("bell"), (badgeEls.bell = h("span", { class: "badge", hidden: true }))));
  if (state.can("layout.move")) {
    tools.push(h("button", { class: "icon-btn label", type: "button", title: "Move the sidebar to the other side", "aria-label": "Move the sidebar",
      onClick: () => saveLayout({ side: lay.side === "right" ? "left" : "right" }) }, icon("swap")));
    tools.push(h("button", { class: "icon-btn label", type: "button", title: "Wide / narrow sidebar", "aria-label": "Wide or narrow sidebar",
      onClick: () => saveLayout({ rail: !layout().rail }) }, icon("rail")));
  }
  const bell = tools[0];
  setBadge(badgeEls.bell, state.unread.notifications);
  meBox.replaceChildren(
    h("div", { class: "me-row" }, avatar(state.me, "sm"),
      h("div", { class: "me-text label" }, h("strong", {}, state.me.display_name), h("span", {}, "@" + state.me.username)),
      h("button", { class: "icon-btn label", type: "button", title: "Log out", "aria-label": "Log out", onClick: logout }, icon("logout"))),
    h("div", { class: "me-tools" }, rankTag(state.me.rank), ...tools));
  void bell;
}

function onMeChanged() {
  applyDesign();
  if (shell) { drawNav(); renderMe(); applyLayout(); drawBubble(); }
}

// ---------------------------------------------------------------- unread counters and notifications
let unreadBusy = false, lastConfig = 0;
async function refreshUnread() {
  if (unreadBusy) return;                    // never pile up requests when the server is slow
  unreadBusy = true;
  try {
    state.unread = await get("/api/unread");
    for (const [id, el] of Object.entries(badgeEls)) if (id !== "bell") setBadge(el, tabBadge(id));
    if (badgeEls.bell) setBadge(badgeEls.bell, state.unread.notifications);
    if (bubbleEl) setBadge(bubbleEl.querySelector(".badge"), state.unread.chats + state.unread.groups + state.unread.notifications + state.unread.invitations);
    const total = state.unread.chats + state.unread.groups;
    document.title = (total ? `(${total}) ` : "") + "Chatisfying · klartext";
    window.dispatchEvent(new CustomEvent("chatisfying:unread"));
    if (Date.now() - lastConfig > 60000) {      // the settings (announcement ...) change rarely: once a minute is enough
      lastConfig = Date.now();
      state.config = { ...state.config, ...(await get("/api/config")) };
      if (bannerBox) drawBanner();
    }
  } catch { /* not important enough to show an error */ }
  unreadBusy = false;
}

async function showNotifications() {
  const body = h("div", { class: "dialog-body" }, h("p", { class: "muted" }, "Loading…"));
  const box = modal("Notifications", body);
  try {
    const data = await get("/api/notifications");
    const rows = data.items.map((n) => h("li", { class: `row${n.is_read ? "" : " unread-row"}` },
      h("div", { class: "item-text" }, n.link ? h("a", { href: n.link, onClick: () => box.close() }, n.text) : h("span", {}, n.text),
        h("span", { class: "item-sub" }, formatTime(n.created)))));
    body.replaceChildren(rows.length ? h("ul", { class: "rows" }, rows) : h("p", { class: "muted" }, "Nothing new."),
      h("div", { class: "dialog-actions" }, h("button", { class: "btn", type: "button", onClick: async () => { await post("/api/notifications/read", {}); refreshUnread(); box.close(); } }, "Mark all as read")));
    if (data.unread) { await post("/api/notifications/read", {}); refreshUnread(); }
  } catch (e) { body.replaceChildren(h("p", {}, e.message)); }
}

// ---------------------------------------------------------------- floating tab bubble
function drawBubble() {
  bubbleEl?.remove();
  bubbleEl = null;
  const cfg = state.me.prefs?.bubble;
  if (!state.can("tabs.bubble") || cfg?.on === false) return;
  const pos = cfg?.pos || { x: 0.9, y: 0.8 };
  bubbleEl = h("button", { class: "tab-bubble", type: "button", "aria-label": "Open tabs", title: "Tabs (drag me anywhere)" }, icon("grid"), h("span", { class: "badge", hidden: true }));
  const place = (x, y) => {
    bubbleEl.style.left = `${Math.min(Math.max(0, x), window.innerWidth - 56)}px`;
    bubbleEl.style.top = `${Math.min(Math.max(0, y), window.innerHeight - 56)}px`;
  };
  place(pos.x * window.innerWidth, pos.y * window.innerHeight);
  document.body.append(bubbleEl);
  let drag = null;
  bubbleEl.addEventListener("pointerdown", (e) => {
    drag = { sx: e.clientX, sy: e.clientY, x: bubbleEl.offsetLeft, y: bubbleEl.offsetTop, moved: false };
    bubbleEl.setPointerCapture?.(e.pointerId);
  });
  bubbleEl.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
    if (Math.abs(dx) + Math.abs(dy) > 6) drag.moved = true;
    if (drag.moved) place(drag.x + dx, drag.y + dy);
  });
  bubbleEl.addEventListener("pointerup", async () => {
    if (!drag) return;
    const moved = drag.moved;
    drag = null;
    if (!moved) { toggleBubblePopup(); return; }
    try {
      state.me = await put("/api/me/prefs", { bubble: { on: true, pos: { x: bubbleEl.offsetLeft / window.innerWidth, y: bubbleEl.offsetTop / window.innerHeight } } });
    } catch { /* position is not saved, no harm */ }
  });
  setBadge(bubbleEl.querySelector(".badge"), state.unread.chats + state.unread.groups + state.unread.notifications + state.unread.invitations);
}

function toggleBubblePopup(force) {
  const existing = document.querySelector(".bubble-popup");
  if (existing) { existing.remove(); if (force !== true) return; }
  const close = () => { popup.remove(); document.removeEventListener("pointerdown", outside, true); };
  const outside = (e) => { if (!popup.contains(e.target) && !bubbleEl?.contains(e.target) && !e.target.closest?.(".nav-more")) close(); };
  const tiles = availableTabs(state.me).map((t) => {
    const n = tabBadge(t.id);
    const winMode = state.can("layout.windows") && state.me.prefs?.windows?.on;
    const a = h("a", { class: "tile", href: `#/${t.id}`, onClick: (e) => { close(); if (winMode) { e.preventDefault(); import("./windows.js").then((m) => m.openWindow(t, state, state.config?.windows?.max_open || 4)); } } }, icon(t.icon), h("span", {}, t.label), n ? h("span", { class: "badge" }, String(n)) : null);
    return a;
  });
  const popup = h("div", { class: "bubble-popup", role: "dialog", "aria-label": "All tabs" },
    h("div", { class: "tiles" }, tiles),
    h("div", { class: "popup-actions" },
      state.can("tabs.editor") ? h("button", { class: "btn small", type: "button", onClick: () => { close(); openTabEditor(state); } }, "Edit tabs") : null,
      state.can("layout.windows") ? h("button", { class: "btn small", type: "button", onClick: async () => {
        close();
        const on = !state.me.prefs?.windows?.on;
        try { state.me = await put("/api/me/prefs", { windows: { on } }); if (!on) (await import("./windows.js")).closeAll(); toast(on ? "Window mode on: tabs from the bubble open as windows." : "Window mode off."); }
        catch (e) { toast(e.message, "error"); }
      } }, state.me.prefs?.windows?.on ? "Window mode: off" : "Window mode: on") : null,
      state.can("tabs.bubble") ? h("button", { class: "btn small", type: "button", onClick: async () => {
        close();
        try { state.me = await put("/api/me/prefs", { bubble: { on: false, pos: state.me.prefs?.bubble?.pos || { x: 0.9, y: 0.8 } } }); drawBubble(); toast("Bubble hidden. You can turn it on again in Settings."); }
        catch (e) { toast(e.message, "error"); }
      } }, "Hide bubble") : null));
  document.body.append(popup);
  setTimeout(() => document.addEventListener("pointerdown", outside, true));
}

// ---------------------------------------------------------------- push opt-in
async function maybeOfferPush() {
  try {
    if (!state.can("push.use") || localStorage.getItem("chatisfying_push_dismissed")) return;
    const info = await get("/api/push/key");
    if (!info.enabled) return;
    const st = await pushState();
    if (st === "on" || st === "denied" || st === "unsupported") return;
    const hint = st === "needs-home-screen" || (!pushSupported() && needsHomeScreen())
      ? "On an iPad/iPhone: tap Share → “Add to Home Screen”, then open Chatisfying from there and turn this on in Settings."
      : "Get a notification when someone writes to you.";
    const bar = h("div", { class: "push-bar", role: "status" }, h("span", {}, hint),
      st === "off" ? h("button", { class: "btn small primary", type: "button", onClick: async () => {
        try { await enablePush(); toast("Push messages are on."); bar.remove(); } catch (e) { toast(e.message, "error"); }
      } }, "Turn on") : null,
      h("button", { class: "btn small", type: "button", onClick: () => { localStorage.setItem("chatisfying_push_dismissed", "1"); bar.remove(); } }, "Not now"));
    document.body.append(bar);
  } catch { /* push is optional */ }
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

// ---------------------------------------------------------------- routing
function currentName() {
  return location.hash.replace(/^#\/?/, "").split("/")[0] || "chats";
}

async function route() {
  if (cleanup) { try { cleanup(); } catch { /* ignore */ } cleanup = null; }
  const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  const name = parts[0] || "chats";
  const arg = parts[1] || null;
  const tab = TABS.find((t) => t.id === name);
  if (!tab || !state.can(tab.perm)) { location.hash = "#/chats"; return; }
  const page = tab.page;

  shell.classList.toggle("chat-open", Boolean(arg));
  applyLayout(page);
  markActive();

  // Every page gets fresh containers. If the user navigates away while a page is still loading,
  // the old page only touches containers that are no longer on screen.
  const list = h("div", { class: "pane-inner" });
  const main = h("div", { class: "pane-inner" });
  listHost.replaceChildren(list, resizerEl);
  mainHost.replaceChildren(main);

  const token = ++routeToken;
  let result;
  try {
    result = await page.render({ list, main, arg, state });
  } catch (e) {
    main.replaceChildren(h("div", { class: "empty" }, h("strong", {}, "This page could not be loaded"), h("p", {}, e.message)));
    return;
  }
  if (token !== routeToken) { if (result) result(); return; }
  cleanup = result || null;
}

init();
