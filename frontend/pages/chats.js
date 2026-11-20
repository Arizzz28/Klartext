// Private chats: list of conversations and people on the left, the open chat on the right.
import { get, post } from "../api.js";
import { createChatPane } from "../chatpane.js";
import { avatar, debounce, emptyState, formatTime, h, icon, listItem } from "../ui.js";

export const usesList = true;

export async function render({ list, main, arg, state }) {
  const search = h("input", { class: "input", type: "search", placeholder: "Find people", "aria-label": "Find people" });
  const body = h("div", { class: "items" });
  list.append(
    h("header", { class: "pane-head" }, h("h1", {}, "Chats")),
    h("div", { class: "pane-search" }, search),
    body);

  let destroyed = false;

  async function loadList() {
    const q = search.value.trim();
    try {
      const [convos, users] = await Promise.all([
        q ? [] : get("/api/messages/conversations"),
        get("/api/users?q=" + encodeURIComponent(q)),
      ]);
      if (destroyed) return;
      const items = [];
      if (convos.length) {
        items.push(h("h2", { class: "section-title" }, "Recent"));
        for (const c of convos) {
          items.push(listItem({
            entity: c.user, title: c.user.display_name,
            subtitle: (c.last.from === state.me.username ? "You: " : "") + c.last.text,
            time: formatTime(c.last.ts), href: `#/chats/${encodeURIComponent(c.user.username)}`,
            active: arg && arg.toLowerCase() === c.user.username.toLowerCase(),
          }));
        }
      }
      const talked = new Set(convos.map((c) => c.user.username));
      const others = users.filter((u) => !talked.has(u.username));
      if (others.length) {
        items.push(h("h2", { class: "section-title" }, q ? "People" : "Everyone"));
        for (const u of others) {
          items.push(listItem({
            entity: u, title: u.display_name, subtitle: "@" + u.username,
            href: `#/chats/${encodeURIComponent(u.username)}`,
            active: arg && arg.toLowerCase() === u.username.toLowerCase(),
          }));
        }
      }
      if (!items.length) {
        items.push(emptyState(q ? "No one found" : "No other people yet", q ? "Try a different name." : "New accounts show up here once an admin approves them."));
      }
      body.replaceChildren(...items);
    } catch (e) {
      if (!destroyed) body.replaceChildren(emptyState("Couldn't load the list", e.message));
    }
  }

  search.addEventListener("input", debounce(loadList, 250));
  loadList();
  const listTimer = setInterval(loadList, 8000);
  let pane = null;

  if (arg) {
    try {
      const other = await get("/api/users/" + encodeURIComponent(arg));
      const base = "/api/messages/" + encodeURIComponent(other.username);
      const header = h("header", { class: "chat-head" },
        h("a", { class: "icon-btn back", href: "#/chats", "aria-label": "Back to chats" }, icon("back")),
        avatar(other),
        h("div", { class: "chat-title" }, h("strong", {}, other.display_name), h("span", { class: "muted" }, "@" + other.username)));
      pane = createChatPane({
        me: state.me, header,
        load: (after) => get(`${base}?after=${after}`),
        send: (text) => post(base, { text }),
        onSent: loadList,
      });
      main.append(pane.root);
      pane.focus();
    } catch (e) {
      main.append(h("div", { class: "chat-head" }, h("a", { class: "icon-btn back", href: "#/chats", "aria-label": "Back to chats" }, icon("back"))),
        emptyState("Can't open this chat", e.message));
    }
  } else {
    main.append(emptyState("Pick someone to talk to", "Choose a person on the left to start a conversation."));
  }

  return () => { destroyed = true; clearInterval(listTimer); if (pane) pane.destroy(); };
}
