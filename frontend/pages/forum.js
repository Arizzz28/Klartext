// Forum for suggestions: write an idea, vote, comment. Staff with moderation rights can set a status or pin posts.
import { del, get, patch, post } from "../api.js";
import { act, confirmDialog, emptyState, field, h, longDate, modal } from "../ui.js";

export const usesList = false;
const STATUS = { open: "Open", planned: "Planned", done: "Done", declined: "Declined" };

export async function render({ main, state }) {
  const page = h("div", { class: "page" }, h("h1", {}, "Forum"), h("p", { class: "muted" }, "Ideas, wishes and questions for Chatisfying. Vote for what you like."));
  const box = h("div");
  const title = h("input", { class: "input", maxlength: "120", required: true, placeholder: "Your idea in one line" });
  const text = h("textarea", { class: "input", rows: "3", maxlength: "3000", placeholder: "More details (optional)" });
  page.append(h("section", { class: "card" }, h("form", { onSubmit: async (e) => { e.preventDefault(); if (await act(post("/api/forum", { title: title.value, body: text.value }), load)) { title.value = ""; text.value = ""; } } },
    field("New post", title), text, h("button", { class: "btn primary", type: "submit" }, "Post"))), box);
  main.append(page);
  const mod = state.can("chat.moderate");

  async function load() {
    const posts = await get("/api/forum");
    box.replaceChildren(...(posts.length ? posts.map((p) => h("section", { class: "card forum-post" },
      h("div", { class: "forum-row" },
        h("button", { class: `vote${p.voted ? " on" : ""}`, type: "button", "aria-label": "Vote", "aria-pressed": String(p.voted), onClick: () => act(post(`/api/forum/${p.id}/vote`), load) }, "▲", h("strong", {}, String(p.votes))),
        h("div", { class: "item-text" }, h("strong", {}, p.pinned ? "📌 " : "", p.title, " ", h("span", { class: `tag status-${p.status}` }, STATUS[p.status])),
          h("span", { class: "item-sub" }, `${p.author} · ${longDate(p.created)}`), p.body ? h("p", { class: "pre" }, p.body) : null)),
      h("div", { class: "button-row" },
        h("button", { class: "btn small", type: "button", onClick: () => comments(p) }, `Comments (${p.comments})`),
        mod ? h("select", { class: "input small-select", "aria-label": "Status", onChange: (e) => act(patch(`/api/forum/${p.id}`, { status: e.target.value }), load) }, Object.entries(STATUS).map(([v, l]) => h("option", { value: v, selected: p.status === v }, l))) : null,
        mod ? h("button", { class: "btn small", type: "button", onClick: () => act(patch(`/api/forum/${p.id}`, { pinned: !p.pinned }), load) }, p.pinned ? "Unpin" : "Pin") : null,
        (mod || p.author_username === state.me.username) ? h("button", { class: "btn small danger-text", type: "button", onClick: async () => { if (await confirmDialog("Delete post", "Delete this post and its comments?", "Delete", true)) act(del(`/api/forum/${p.id}`), load); } }, "Delete") : null))) : [emptyState("No posts yet")]));
  }

  async function comments(p) {
    const list = h("ul", { class: "rows" });
    const input = h("input", { class: "input", maxlength: "1000", required: true, placeholder: "Write a comment" });
    async function draw() {
      const rows = await get(`/api/forum/${p.id}/comments`);
      list.replaceChildren(...(rows.length ? rows.map((c) => h("li", { class: "row" }, h("div", { class: "item-text" }, h("strong", {}, c.author), h("span", {}, c.body), h("span", { class: "item-sub" }, longDate(c.created))),
        (mod || c.author_username === state.me.username) ? h("button", { class: "btn small danger-text", type: "button", onClick: () => act(del(`/api/forum/${p.id}/comments/${c.id}`), draw) }, "Delete") : null)) : [h("li", { class: "muted" }, "No comments yet.")]));
    }
    const form = h("form", { class: "inline-form", onSubmit: async (e) => { e.preventDefault(); if (await act(post(`/api/forum/${p.id}/comments`, { body: input.value }), draw)) { input.value = ""; load(); } } },
      input, h("button", { class: "btn primary", type: "submit" }, "Send"));
    modal(p.title, h("div", { class: "dialog-body" }, list, form));
    await draw();
  }
  await load();
}
