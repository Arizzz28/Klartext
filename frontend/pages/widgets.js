// Widgets: small boxes with live information. You choose which ones you want.
import { get, put } from "../api.js";
import { field, h, longDate, modal, toast } from "../ui.js";

export const usesList = false;

const ALL = {
  clock: "Clock", unread: "Unread messages", coins: "My coins", tasks_today: "Tasks due today", next_event: "Next event",
  mission_progress: "Missions", visitors: "Visitors (24 h)", quote: "Thought of the day",
};
const QUOTES = ["Small steps every day.", "Done is better than perfect.", "Ask a friend how they are doing today.", "Take a short break and drink some water.",
  "One thing at a time.", "Be kind - it costs nothing."];
const safe = (p, fallback) => p.catch(() => fallback);

export async function render({ main, state }) {
  const page = h("div", { class: "page wide" });
  main.append(page);
  const wanted = () => (Array.isArray(state.me.prefs?.widgets) ? state.me.prefs.widgets : ["clock", "unread", "coins", "tasks_today", "next_event"]);
  const clockEl = h("strong", { class: "big" });
  const tick = () => { clockEl.textContent = new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }); };
  tick();
  const timer = setInterval(tick, 10000);

  const box = (title, ...content) => h("div", { class: "stat widget" }, h("span", { class: "widget-title" }, title), ...content);

  async function build(id) {
    if (id === "clock") return box("Clock", clockEl, h("small", {}, new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })));
    if (id === "unread") { const u = state.unread; return box("Unread", h("strong", { class: "big" }, String(u.chats + u.groups)), h("small", {}, `${u.chats} private · ${u.groups} in groups`)); }
    if (id === "coins") { const c = await safe(get("/api/coins"), null); return box("My coins", h("strong", { class: "big" }, c ? String(c.coins) : "–"), h("a", { href: "#/missions" }, "Open missions")); }
    if (id === "tasks_today") {
      const tasks = await safe(get("/api/tasks"), []);
      const end = new Date(); end.setHours(23, 59, 59, 999);
      const due = tasks.filter((t) => !t.done && t.due && t.due <= end.getTime() / 1000);
      return box("Due today", h("strong", { class: "big" }, String(due.length)), h("small", {}, due.slice(0, 3).map((t) => t.title).join(" · ") || "Nothing due"));
    }
    if (id === "next_event") {
      const ev = (await safe(get(`/api/events?from=${Date.now() / 1000}`), []))[0];
      return box("Next event", ev ? h("strong", {}, ev.title) : h("strong", {}, "–"), h("small", {}, ev ? longDate(ev.start) : "Nothing planned"));
    }
    if (id === "mission_progress") {
      const d = await safe(get("/api/missions"), { missions: [] });
      const open = d.missions.filter((m) => !m.claimed);
      return box("Missions", h("strong", { class: "big" }, String(open.filter((m) => m.claimable).length)), h("small", {}, "ready to collect"), h("a", { href: "#/missions" }, `${open.length} open`));
    }
    if (id === "visitors") {
      const d = await safe(get("/api/me/visitors"), { visitors: [] });
      const n = d.visitors.filter((v) => v.ts > Date.now() / 1000 - 86400).length;
      return box("Visitors", h("strong", { class: "big" }, String(n)), h("a", { href: "#/visitors" }, "Open list"));
    }
    if (id === "quote") return box("Thought of the day", h("strong", {}, QUOTES[new Date().getDate() % QUOTES.length]));
    return null;
  }

  async function draw() {
    const items = (await Promise.all(wanted().filter((id) => ALL[id]).map(build))).filter(Boolean);
    page.replaceChildren(h("div", { class: "toolbar-row split" }, h("h1", {}, "Widgets"), h("button", { class: "btn small", type: "button", onClick: choose }, "Choose widgets")),
      h("div", { class: "stats" }, items.length ? items : [h("p", { class: "muted" }, "No widgets selected.")]));
  }

  function choose() {
    const checks = Object.entries(ALL).map(([id, label]) => {
      const el = h("input", { type: "checkbox", checked: wanted().includes(id), value: id });
      return { el, row: h("label", { class: "choice" }, el, h("span", {}, h("strong", {}, label))) };
    });
    const form = h("form", { class: "dialog-body" }, ...checks.map((c) => c.row), h("div", { class: "dialog-actions" }, h("button", { class: "btn primary", type: "submit" }, "Save")));
    const box2 = modal("Choose widgets", form);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try { state.me = await put("/api/me/prefs", { widgets: checks.filter((c) => c.el.checked).map((c) => c.el.value) }); box2.close(); draw(); }
      catch (err) { toast(err.message, "error"); }
    });
  }
  await draw();
  return () => clearInterval(timer);
}
