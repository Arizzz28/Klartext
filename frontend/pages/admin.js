// Global administration: approve people, edit the whitelist, remove groups.
import { del, get, post } from "../api.js";
import { confirmDialog, emptyState, h, toast } from "../ui.js";

export const usesList = false;

export async function render({ main }) {
  let tab = "users";
  const content = h("div", { class: "admin-content" });
  const tabsEl = h("div", { class: "tabs", role: "tablist" });

  function drawTabs() {
    tabsEl.replaceChildren(...[["users", "Users"], ["whitelist", "Whitelist"], ["groups", "Groups"]].map(([id, label]) =>
      h("button", {
        class: `tab${tab === id ? " active" : ""}`, type: "button", role: "tab", "aria-selected": String(tab === id),
        onClick: () => { tab = id; drawTabs(); load(); },
      }, label)));
  }

  async function act(promise) {
    try { const res = await promise; toast(res.message); load(); }
    catch (e) { toast(e.message, "error"); }
  }

  async function load() {
    try {
      if (tab === "users") content.replaceChildren(await usersView());
      else if (tab === "whitelist") content.replaceChildren(await whitelistView());
      else content.replaceChildren(await groupsView());
    } catch (e) { content.replaceChildren(emptyState("Couldn't load this tab", e.message)); }
  }

  async function usersView() {
    const users = await get("/api/admin/users");
    const pending = users.filter((u) => u.status === "pending").length;
    return h("div", {},
      pending ? h("p", { class: "notice" }, `${pending} account${pending === 1 ? " is" : "s are"} waiting for approval.`) : null,
      h("ul", { class: "rows" }, users.map((u) => h("li", { class: "row" },
        h("div", { class: "item-text" },
          h("strong", {}, u.display_name, u.is_admin ? " · admin" : ""),
          h("span", { class: "item-sub" }, `@${u.username} · ${u.email}`)),
        h("span", { class: `tag status-${u.status}` }, u.status === "banned" ? "suspended" : u.status),
        u.is_admin ? null : h("div", { class: "row-actions" },
          u.status !== "active" ? h("button", { class: "btn small primary", type: "button", onClick: () => act(post(`/api/admin/users/${encodeURIComponent(u.username)}/approve`)) }, u.status === "banned" ? "Restore" : "Approve") : null,
          u.status !== "banned" ? h("button", { class: "btn small danger-text", type: "button", onClick: () => act(post(`/api/admin/users/${encodeURIComponent(u.username)}/suspend`)) }, "Suspend") : null)))));
  }

  async function whitelistView() {
    const names = await get("/api/admin/whitelist");
    const input = h("input", { class: "input", placeholder: "Username to allow", maxlength: "20", "aria-label": "Username to allow" });
    return h("div", {},
      h("form", { class: "invite-form", onSubmit: (e) => { e.preventDefault(); if (input.value.trim()) act(post("/api/admin/whitelist", { username: input.value.trim() })); } },
        input, h("button", { class: "btn primary", type: "submit" }, "Add")),
      names.length
        ? h("ul", { class: "rows" }, names.map((n) => h("li", { class: "row" },
          h("strong", { class: "item-text" }, n),
          h("button", { class: "btn small danger-text", type: "button", onClick: () => act(del(`/api/admin/whitelist/${encodeURIComponent(n)}`)) }, "Remove"))))
        : emptyState("The whitelist is empty", "Only the admin username can register until you add names."));
  }

  async function groupsView() {
    const groups = await get("/api/admin/groups");
    if (!groups.length) return emptyState("No groups yet");
    return h("ul", { class: "rows" }, groups.map((gr) => h("li", { class: "row" },
      h("div", { class: "item-text" },
        h("strong", {}, gr.name),
        h("span", { class: "item-sub" }, `${gr.member_count} members · created by @${gr.created_by} · ${gr.join_mode === "open" ? "open" : "invite-only"}`)),
      h("button", {
        class: "btn small danger-text", type: "button",
        onClick: async () => {
          if (await confirmDialog("Delete group", `Delete “${gr.name}” and all its messages? This can't be undone.`, "Delete group", true)) {
            act(del(`/api/admin/groups/${encodeURIComponent(gr.id)}`));
          }
        },
      }, "Delete"))));
  }

  drawTabs();
  main.append(h("div", { class: "page wide" }, h("h1", {}, "Administration"), tabsEl, content));
  load();
}
