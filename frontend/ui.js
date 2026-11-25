// Small reusable UI helpers. Everything is built with textContent, never innerHTML with user data,
// so messages and names can't inject HTML (XSS protection).

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "value" || key === "checked") el[key] = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return el;
}

const ICONS = {
  chats: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.4A8 8 0 1 1 21 12Z"/>',
  groups: '<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><circle cx="17" cy="9" r="2.6"/><path d="M17 14.2c2.4 0 4 1.7 4 4.3"/>',
  profile: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>',
  settings: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
  admin: '<path d="M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6l8-3Z"/><path d="m9 12 2 2 4-4"/>',
  logout: '<path d="M9 4H5v16h4M16 8l4 4-4 4M20 12H9"/>',
  back: '<path d="m15 5-7 7 7 7"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  send: '<path d="M4 12 20 4l-4 16-4-6-8-2Z"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  smile: '<circle cx="12" cy="12" r="9"/><path d="M8.5 14.2a4.2 4.2 0 0 0 7 0M9 9.5h.01M15 9.5h.01"/>',
  clip: '<path d="m20 11-8.6 8.6a5 5 0 0 1-7-7l9-9a3.3 3.3 0 0 1 4.7 4.7l-9 9a1.7 1.7 0 0 1-2.4-2.4L14.5 6"/>',
  reply: '<path d="M10 8 4 13l6 5v-3.5c5 0 8 1.5 10 5-.5-5.5-3.5-9-10-9.5Z"/>',
  edit: '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4Z"/><path d="m13.5 6.5 4 4"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6"/>',
  flag: '<path d="M5 21V4m0 0h11l-2 4 2 4H5"/>',
  more: '<circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/>',
  file: '<path d="M7 3h7l5 5v13H7V3Z"/><path d="M14 3v5h5"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.7"/><path d="m21 16-5-5-9 9"/>',
  missions: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v9M9.6 9.6c.4-.9 1.4-1.4 2.4-1.4s2.3.5 2.3 1.7c0 2.2-4.8 1.1-4.8 3.4 0 1.2 1.2 1.7 2.5 1.7s2-.5 2.4-1.4"/>',
  calendar: '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
  tasks: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="m8 12 3 3 5-6"/>',
  notes: '<path d="M6 3h9l4 4v14H6V3Z"/><path d="M9 11h7M9 15h7M9 7h3"/>',
  widgets: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  music: '<path d="M9 18V6l10-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="16" r="2.5"/>',
  visitors: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="3"/>',
  games: '<rect x="3" y="7" width="18" height="11" rx="5"/><path d="M8 10.5v4M6 12.5h4M15.5 11h.01M18 14h.01"/>',
  forum: '<path d="M4 5h16v11H9l-5 4V5Z"/><path d="M8 9h8M8 12h5"/>',
  ai: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3ZM18.5 16l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2Z"/>',
  whatsnew: '<path d="M5 4h14v16l-3-2-4 2-4-2-3 2V4Z"/><path d="M9 9h6M9 13h4"/>',
  custom: '<path d="M4 7a3 3 0 0 1 3-3h4v6H4V7ZM13 4h4a3 3 0 0 1 3 3v3h-7V4ZM4 12h7v8H7a3 3 0 0 1-3-3v-5ZM13 12h7v5a3 3 0 0 1-3 3h-4v-8Z"/>',
  grid: '<circle cx="6" cy="6" r="1.6"/><circle cx="12" cy="6" r="1.6"/><circle cx="18" cy="6" r="1.6"/><circle cx="6" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="18" cy="12" r="1.6"/><circle cx="6" cy="18" r="1.6"/><circle cx="12" cy="18" r="1.6"/><circle cx="18" cy="18" r="1.6"/>',
  bell: '<path d="M6 17V11a6 6 0 0 1 12 0v6l1.5 2h-15L6 17ZM10 21h4"/>',
  swap: '<path d="M7 7h12l-3-3M17 17H5l3 3"/>',
  rail: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
  page: '<path d="M7 3h7l4 4v14H7zM14 3v4h4"/>',      // used when a new tab names an icon that does not exist yet
};

export function icon(name) {
  const span = h("span", { class: "icon", "aria-hidden": "true" });
  span.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ICONS.page}</svg>`;
  return span;
}

// The brand: "Chatisfying" with the small German word "klartext" underneath.
export function brand(large = false) {
  return h("div", { class: `brand${large ? " brand-lg" : ""}` },
    h("img", { class: "brand-mark", src: "assets/images/logo.svg", alt: "" }),
    h("div", { class: "brand-text" },
      h("span", { class: "brand-name" }, "Chatisfying"),
      h("span", { class: "brand-sub" }, "klartext")));
}

function hashString(s) {
  let n = 0;
  for (const ch of s) n = (n * 31 + ch.codePointAt(0)) >>> 0;
  return n;
}

// Round picture, or the first letter on a colour derived from the name.
export function avatar(entity, size = "") {
  const name = entity.display_name || entity.name || entity.username || "?";
  const box = h("div", { class: `avatar ${size}`.trim(), "aria-hidden": "true" });
  if (entity.avatar) {
    box.append(h("img", { src: entity.avatar, alt: "" }));
  } else {
    box.textContent = name.trim().charAt(0).toUpperCase();
    box.style.setProperty("--hue", hashString(name) % 360);
  }
  return box;
}

export function formatTime(ts) {
  const d = new Date(ts * 1000);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// A small coloured tag for a rank, e.g. "Pro+".
export function rankTag(rank) {
  if (!rank) return null;
  const tag = h("span", { class: "tag rank-tag" }, rank.name);
  tag.style.setProperty("--rank", rank.color || "#888");
  return tag;
}

// A round counter for unread things. Hidden when the number is 0.
export function countBadge(n) {
  const b = h("span", { class: "badge", hidden: !n, "aria-label": `${n} unread` }, n > 99 ? "99+" : String(n || ""));
  return b;
}

export function setBadge(el, n) {
  el.textContent = n > 99 ? "99+" : String(n || "");
  el.hidden = !n;
}

export function longDate(ts) {
  return new Date(ts * 1000).toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

// A labelled form field.
export function field(label, el, hint = "") {
  return h("label", { class: "field" }, h("span", { class: "field-label" }, label), el, hint ? h("small", { class: "muted" }, hint) : null);
}

// Date + time <input> helpers (the browser gives local time; the server wants seconds since 1970).
export function toLocalInput(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}
export const fromLocalInput = (value) => (value ? new Date(value).getTime() / 1000 : null);

// Runs an async action, shows the server's message as a toast and reports errors the same way.
export async function act(promise, after) {
  try { const res = await promise; if (res?.message) toast(res.message); if (after) await after(res); return res; }
  catch (e) { toast(e.message, "error"); return null; }
}

export function emptyState(title, text = "") {
  return h("div", { class: "empty" }, h("strong", {}, title), text ? h("p", {}, text) : null);
}

// One row in the left list (a person or a group).
export function listItem({ entity, title, subtitle, time, href, active, unread = 0 }) {
  return h("a", { class: `item${active ? " active" : ""}${unread ? " has-unread" : ""}`, href },
    avatar(entity),
    h("div", { class: "item-text" },
      h("div", { class: "item-top" }, h("strong", { class: "item-title" }, title), time ? h("time", {}, time) : null),
      h("span", { class: "item-sub" }, subtitle || "")),
    unread ? h("span", { class: "badge", "aria-label": `${unread} unread` }, unread > 99 ? "99+" : String(unread)) : null);
}

let toastBox;
export function toast(message, kind = "info") {
  if (!toastBox) {
    toastBox = h("div", { class: "toasts", role: "status", "aria-live": "polite" });
    document.body.append(toastBox);
  }
  const el = h("div", { class: `toast ${kind}` }, message);
  toastBox.append(el);
  setTimeout(() => el.remove(), 4000);
}

export function modal(title, content, onClose = null, closable = true) {
  const previous = document.activeElement;
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    overlay.remove();
    document.removeEventListener("keydown", onKey);
    previous?.focus?.();
    if (onClose) onClose();
  };
  const onKey = (e) => { if (closable && e.key === "Escape") close(); };
  const dialog = h("div", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-label": title },
      h("div", { class: "dialog-head" },
        h("h2", {}, title),
        closable ? h("button", { class: "icon-btn", type: "button", "aria-label": "Close", onClick: close }, icon("close")) : null),
      content);
  const overlay = h("div", { class: "overlay", onClick: (e) => { if (closable && e.target === overlay) close(); } }, dialog);
  document.body.append(overlay);
  document.addEventListener("keydown", onKey);
  overlay.querySelector("input, textarea, button.primary")?.focus();
  return { close, root: dialog };
}

export function confirmDialog(title, text, confirmLabel = "Confirm", danger = false) {
  return new Promise((resolve) => {
    let answered = false;
    const finish = (value) => {
      if (answered) return;
      answered = true;
      resolve(value);
      box.close();
    };
    const body = h("div", { class: "dialog-body" },
      h("p", {}, text),
      h("div", { class: "dialog-actions" },
        h("button", { class: "btn", type: "button", onClick: () => finish(false) }, "Cancel"),
        h("button", { class: `btn ${danger ? "danger" : "primary"}`, type: "button", onClick: () => finish(true) }, confirmLabel)));
    const box = modal(title, body, () => finish(false));   // Esc / click outside count as "Cancel"
  });
}

// Crops a chosen image to a small square and returns it as a data URL (keeps the JSON files small).
export function fileToAvatar(file, size = 160) {
  return new Promise((resolve, reject) => {
    if (!file || !file.type.startsWith("image/")) return reject(new Error("Please choose an image file."));
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = size;
      const side = Math.min(img.width, img.height);
      canvas.getContext("2d").drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, size, size);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL("image/jpeg", 0.82));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("That image could not be read.")); };
    img.src = url;
  });
}

export const THEME_KEY = "chatisfying_theme";
export function applyTheme(mode) {
  if (mode === "light" || mode === "dark") document.documentElement.dataset.theme = mode;
  else delete document.documentElement.dataset.theme;
}
applyTheme(localStorage.getItem(THEME_KEY));

export function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

// Small pop-up menu next to a button. items: [{label, onClick, danger}]
export function openMenu(anchor, items) {
  document.querySelector(".menu")?.remove();
  const close = () => { menu.remove(); document.removeEventListener("pointerdown", outside, true); document.removeEventListener("keydown", onKey); };
  const outside = (e) => { if (!menu.contains(e.target)) close(); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  const menu = h("div", { class: "menu", role: "menu" }, items.map((item) =>
    h("button", { class: `menu-item${item.danger ? " danger-text" : ""}`, type: "button", role: "menuitem",
      onClick: () => { close(); item.onClick(); } }, item.label)));
  document.body.append(menu);
  const r = anchor.getBoundingClientRect();
  const left = Math.min(Math.max(8, r.right - menu.offsetWidth), window.innerWidth - menu.offsetWidth - 8);
  const top = r.bottom + 6 + menu.offsetHeight > window.innerHeight ? Math.max(8, r.top - menu.offsetHeight - 6) : r.bottom + 6;
  menu.style.left = left + "px";
  menu.style.top = top + "px";
  setTimeout(() => { document.addEventListener("pointerdown", outside, true); document.addEventListener("keydown", onKey); });
  return close;
}

// A chosen picture, scaled down to at most `max` pixels and below ~300 KB, as a data URL (chat backgrounds).
export function fileToBackground(file, max = 1280) {
  return new Promise((resolve, reject) => {
    if (!file || !file.type.startsWith("image/")) return reject(new Error("Please choose an image file."));
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      let scale = Math.min(1, max / Math.max(img.width, img.height));
      for (let attempt = 0; attempt < 6; attempt++) {
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(img.width * scale);
        canvas.height = Math.round(img.height * scale);
        canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
        const data = canvas.toDataURL("image/jpeg", 0.7);
        if (data.length < 400_000) return resolve(data);
        scale *= 0.75;
      }
      reject(new Error("That image is too detailed. Try a smaller one."));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("That image could not be read.")); };
    img.src = url;
  });
}

export function lightbox(src) {
  const close = () => { box.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  const box = h("div", { class: "lightbox", onClick: close }, h("img", { src, alt: "" }));
  document.body.append(box);
  document.addEventListener("keydown", onKey);
}
