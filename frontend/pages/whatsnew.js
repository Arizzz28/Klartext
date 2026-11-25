// What's new: release notes. Every person has their own "seen" mark, so the counter only shows what YOU have not read.
import { get, post } from "../api.js";
import { act, field, h, longDate, emptyState } from "../ui.js";
import { del as remove, post as add } from "../api.js";

export const usesList = false;

export async function render({ main, state }) {
  const page = h("div", { class: "page" }, h("h1", {}, "What's new"));
  main.append(page);
  async function load() {
    const rows = await get("/api/releases");
    page.replaceChildren(h("h1", {}, "What's new"), state.can("admin.releases") ? publishForm() : null,
      ...(rows.length ? rows.map((r) => h("section", { class: "card" }, h("h2", {}, r.title, " ", h("span", { class: "tag" }, r.id), r.seen ? null : h("span", { class: "tag new-tag" }, "new")),
        h("p", { class: "muted" }, longDate(r.created)), h("p", { class: "pre" }, r.body),
        state.can("admin.releases") ? h("button", { class: "btn small danger-text", type: "button", onClick: () => act(remove(`/api/releases/${encodeURIComponent(r.id)}`), load) }, "Delete") : null)) : [emptyState("Nothing yet")]));
    if (rows.some((r) => !r.seen)) { await post("/api/releases/seen"); window.dispatchEvent(new CustomEvent("chatisfying:read")); }
  }
  function publishForm() {
    const id = h("input", { class: "input", placeholder: "3.1.0", maxlength: "20", required: true });
    const title = h("input", { class: "input", maxlength: "100", required: true });
    const text = h("textarea", { class: "input", rows: "4", maxlength: "4000" });
    return h("section", { class: "card" }, h("h2", {}, "Publish an entry"), h("form", { onSubmit: (e) => { e.preventDefault(); act(add("/api/releases", { id: id.value, title: title.value, body: text.value }), load); } },
      field("Release ID", id), field("Title", title), field("Text", text), h("button", { class: "btn primary", type: "submit" }, "Publish")));
  }
  await load();
}
