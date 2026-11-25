// Global search over people, groups, your chats, notes, tasks and events.
import { get } from "../api.js";
import { avatar, debounce, emptyState, formatTime, h } from "../ui.js";

export const usesList = false;

export async function render({ main }) {
  const input = h("input", { class: "input", type: "search", placeholder: "Search people, groups, messages, notes, tasks, events…", autofocus: true, "aria-label": "Search" });
  const results = h("div");
  main.append(h("div", { class: "page" }, h("h1", {}, "Search"), input, results));
  const run = debounce(async () => {
    const q = input.value.trim();
    if (q.length < 2) { results.replaceChildren(h("p", { class: "muted" }, "Type at least 2 letters. Only your own chats, notes and tasks are searched.")); return; }
    try {
      const r = await get(`/api/search?q=${encodeURIComponent(q)}`);
      const section = (title, rows) => rows.length ? h("section", { class: "card" }, h("h2", {}, title), h("ul", { class: "rows" }, rows)) : null;
      const out = [
        section("People", r.users.map((u) => h("li", { class: "row" }, avatar(u, "sm"), h("a", { class: "item-text", href: `#/chats/${encodeURIComponent(u.username)}` }, h("strong", {}, u.display_name), h("span", { class: "item-sub" }, "@" + u.username))))),
        section("Groups", r.groups.map((g) => h("li", { class: "row" }, h("a", { class: "item-text", href: `#/groups/${g.id}` }, h("strong", {}, g.name), h("span", { class: "item-sub" }, g.member ? "member" : "open group"))))),
        section("Messages", r.messages.map((m) => h("li", { class: "row" }, h("a", { class: "item-text", href: m.link }, h("strong", {}, `${m.from} · ${m.where}`), h("span", { class: "item-sub" }, m.text), h("span", { class: "item-sub" }, formatTime(m.ts)))))),
        section("Notes", r.notes.map((n) => h("li", { class: "row" }, h("a", { class: "item-text", href: `#/notes/${n.id}` }, n.title)))),
        section("Tasks", r.tasks.map((t) => h("li", { class: "row" }, h("a", { class: "item-text", href: "#/tasks" }, t.title)))),
        section("Events", r.events.map((e) => h("li", { class: "row" }, h("a", { class: "item-text", href: "#/calendar" }, e.title)))),
      ].filter(Boolean);
      results.replaceChildren(...(out.length ? out : [emptyState("Nothing found")]));
    } catch (e) { results.replaceChildren(emptyState("Search failed", e.message)); }
  }, 300);
  input.addEventListener("input", run);
  run();
  input.focus();
}
