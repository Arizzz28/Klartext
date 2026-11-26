// Desktop mode: tabs open as movable windows on top of the page. Needs the permission "layout.windows" and the person's own switch
// (bubble popup -> "Window mode"). A window can be dragged by its title bar, folded into the bubble dock (the little chips next to the
// bubble) and closed. How many may be open at once is set by the admins (Settings -> windows.max_open, default 4).
// Pages are the same ones the normal layout uses: a window gives each page its own "list" and "main" container.
import { h, icon, toast } from "./ui.js";
import { TABS } from "./tabs.js";

const open = new Map();                       // tab id -> { el, folded }
let dock = null, zTop = 50;

function ensureDock() {
  if (!dock) { dock = h("div", { class: "win-dock" }); document.body.append(dock); }
  return dock;
}

function drawDock() {
  const d = ensureDock();
  d.replaceChildren(...[...open].filter(([, w]) => w.folded).map(([id]) => {
    const t = TABS.find((x) => x.id === id);
    return h("button", { class: "win-chip", type: "button", title: `Open ${t.label}`, onClick: () => fold(id, false) }, icon(t.icon), h("span", {}, t.label));
  }));
}

function fold(id, folded) {
  const w = open.get(id);
  if (!w) return;
  w.folded = folded;
  w.el.hidden = folded;
  if (!folded) w.el.style.zIndex = String(++zTop);
  drawDock();
}

function close(id) {
  const w = open.get(id);
  if (!w) return;
  try { w.cleanup?.(); } catch { /* ignore */ }
  w.el.remove();
  open.delete(id);
  drawDock();
}

export function closeAll() { [...open.keys()].forEach(close); }

export async function openWindow(tab, state, max = 4) {
  if (open.has(tab.id)) return fold(tab.id, false);
  if (open.size >= max) return toast(`You can have ${max} windows open. Close one first.`, "info");
  const list = h("div", { class: "pane-inner" }), main = h("div", { class: "pane-inner win-main" });
  const bar = h("div", { class: "win-bar" }, icon(tab.icon), h("strong", {}, tab.label),
    h("span", { class: "grow-space" }),
    h("button", { class: "btn small", type: "button", title: "Fold into the bubble", "aria-label": "Fold", onClick: () => fold(tab.id, true) }, "–"),
    h("button", { class: "btn small", type: "button", title: "Close", "aria-label": "Close", onClick: () => close(tab.id) }, "✕"));
  const el = h("div", { class: "win", role: "dialog", "aria-label": tab.label }, bar, h("div", { class: "win-body" }, tab.page.usesList ? list : null, main));
  const n = open.size;
  const saved = JSON.parse(localStorage.getItem(`chatisfying_win_${tab.id}`) || "null");
  el.style.left = `${saved?.x ?? 40 + n * 36}px`; el.style.top = `${saved?.y ?? 70 + n * 36}px`;
  el.style.zIndex = String(++zTop);
  document.body.append(el);
  const entry = { el, folded: false };
  open.set(tab.id, entry);
  el.addEventListener("pointerdown", () => { el.style.zIndex = String(++zTop); });
  // drag by the title bar (works with finger and mouse)
  let drag = null;
  bar.addEventListener("pointerdown", (e) => { if (e.target.closest("button")) return; drag = { sx: e.clientX, sy: e.clientY, x: el.offsetLeft, y: el.offsetTop }; bar.setPointerCapture?.(e.pointerId); });
  bar.addEventListener("pointermove", (e) => {
    if (!drag) return;
    el.style.left = `${Math.min(Math.max(0, drag.x + e.clientX - drag.sx), window.innerWidth - 80)}px`;
    el.style.top = `${Math.min(Math.max(0, drag.y + e.clientY - drag.sy), window.innerHeight - 40)}px`;
  });
  bar.addEventListener("pointerup", () => { if (drag) localStorage.setItem(`chatisfying_win_${tab.id}`, JSON.stringify({ x: el.offsetLeft, y: el.offsetTop })); drag = null; });
  try { entry.cleanup = await tab.page.render({ list, main, arg: null, state }); }
  catch (e) { main.replaceChildren(h("p", {}, `This page could not be loaded: ${e.message}`)); }
}
