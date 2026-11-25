// Tasks, optionally shared with friends. Everybody involved can tick a task off; only the owner can change or delete it.
import { del, get, post, put } from "../api.js";
import { act, emptyState, field, fromLocalInput, h, longDate, toLocalInput } from "../ui.js";

export const usesList = false;

export async function render({ main, state }) {
  const page = h("div", { class: "page" }, h("h1", {}, "Tasks"));
  main.append(page);
  const title = h("input", { class: "input", placeholder: "What has to be done?", maxlength: "200", required: true });
  const due = h("input", { class: "input", type: "datetime-local" });
  const share = h("input", { class: "input", placeholder: "Share with (usernames, comma separated)" });
  const listEl = h("ul", { class: "rows" });
  page.append(h("section", { class: "card" }, h("form", { class: "grid-form", onSubmit: async (e) => {
    e.preventDefault();
    const names = share.value.split(",").map((x) => x.trim()).filter(Boolean);
    const ok = await act(post("/api/tasks", { title: title.value, due: fromLocalInput(due.value), share_with: names }), load);
    if (ok) { title.value = ""; due.value = ""; share.value = ""; }
  } }, field("Task", title), field("Due (optional)", due), field("Share (optional)", share), h("button", { class: "btn primary", type: "submit" }, "Add task"))),
  h("section", { class: "card" }, listEl));

  async function load() {
    const tasks = await get("/api/tasks");
    listEl.replaceChildren(...(tasks.length ? tasks.map((t) => {
      const box = h("input", { type: "checkbox", checked: t.done, "aria-label": `Done: ${t.title}`, onChange: () => act(put(`/api/tasks/${t.id}`, { done: box.checked }), load) });
      const late = !t.done && t.due && t.due < Date.now() / 1000;
      return h("li", { class: `row${t.done ? " done" : ""}` }, box,
        h("div", { class: "item-text" }, h("strong", {}, t.title),
          h("span", { class: `item-sub${late ? " late" : ""}` }, [t.due ? `Due ${longDate(t.due)}` : "", t.mine ? (t.shared_with.length ? `Shared with ${t.shared_with.join(", ")}` : "") : `From @${t.owner}`].filter(Boolean).join(" · "))),
        t.mine ? h("button", { class: "btn small danger-text", type: "button", onClick: () => act(del(`/api/tasks/${t.id}`), load) }, "Delete") : null);
    }) : [emptyState("No tasks", "Add your first task above.")]));
  }
  await load();
}
