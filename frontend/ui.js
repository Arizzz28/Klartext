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
};

export function icon(name) {
  const span = h("span", { class: "icon", "aria-hidden": "true" });
  span.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
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

export function emptyState(title, text = "") {
  return h("div", { class: "empty" }, h("strong", {}, title), text ? h("p", {}, text) : null);
}

// One row in the left list (a person or a group).
export function listItem({ entity, title, subtitle, time, href, active }) {
  return h("a", { class: `item${active ? " active" : ""}`, href },
    avatar(entity),
    h("div", { class: "item-text" },
      h("div", { class: "item-top" }, h("strong", { class: "item-title" }, title), time ? h("time", {}, time) : null),
      h("span", { class: "item-sub" }, subtitle || "")));
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

export function modal(title, content, onClose = null) {
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
  const onKey = (e) => { if (e.key === "Escape") close(); };
  const overlay = h("div", { class: "overlay", onClick: (e) => { if (e.target === overlay) close(); } },
    h("div", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-label": title },
      h("div", { class: "dialog-head" },
        h("h2", {}, title),
        h("button", { class: "icon-btn", type: "button", "aria-label": "Close", onClick: close }, icon("close"))),
      content));
  document.body.append(overlay);
  document.addEventListener("keydown", onKey);
  overlay.querySelector("input, textarea, button.primary")?.focus();
  return { close };
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
