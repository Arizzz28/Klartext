// Private notes. Only you can read them; staff with the special "notes" permission can look - and you get told when they do.
import { del, get, post, put } from "../api.js";
import { act, confirmDialog, emptyState, formatTime, h, toast } from "../ui.js";

export const usesList = true;

export async function render({ list, main, arg, state }) {
  const body = h("div", { class: "items" });
  list.append(h("header", { class: "pane-head" }, h("h1", {}, "Notes"),
    h("button", { class: "btn small", type: "button", onClick: async () => {
      try { const r = await post("/api/notes", { title: "New note", body: "" }); location.hash = `#/notes/${r.id}`; } catch (e) { toast(e.message, "error"); }
    } }, "New note")),
    h("p", { class: "hint pad" }, "Only you can read your notes. Staff with a special permission may look at them - this is logged and you will see a notification."), body);
  let notes = [];
  async function loadList() {
    notes = await get("/api/notes");
    body.replaceChildren(...(notes.length ? notes.map((n) => h("a", { class: `item${String(n.id) === arg ? " active" : ""}`, href: `#/notes/${n.id}` },
      h("div", { class: "item-text" }, h("strong", { class: "item-title" }, n.title || "(no title)"), h("span", { class: "item-sub" }, (n.body || "").slice(0, 60))),
      h("time", { class: "muted" }, formatTime(n.updated)))) : [emptyState("No notes yet")]));
  }
  await loadList();
  const note = notes.find((n) => String(n.id) === arg);
  if (!arg || !note) { main.append(emptyState("Pick or create a note")); }
  else {
    const title = h("input", { class: "input", maxlength: "120", value: note.title, "aria-label": "Title" });
    const text = h("textarea", { class: "input note-body", maxlength: "20000", "aria-label": "Note" }, note.body);
    const status = h("span", { class: "muted" }, "Saved");
    let timer;
    const save = async () => {
      status.textContent = "Saving…";
      try { await put(`/api/notes/${note.id}`, { title: title.value, body: text.value }); status.textContent = "Saved"; loadList(); }
      catch (e) { status.textContent = e.message; }
    };
    const later = () => { status.textContent = "…"; clearTimeout(timer); timer = setTimeout(save, 700); };
    title.addEventListener("input", later); text.addEventListener("input", later);
    main.append(h("div", { class: "page" }, h("a", { class: "btn small back", href: "#/notes" }, "‹ Notes"), title, text,
      h("div", { class: "button-row" }, status, h("button", { class: "btn small danger-text", type: "button", onClick: async () => {
        if (await confirmDialog("Delete note", "Delete this note?", "Delete", true)) await act(del(`/api/notes/${note.id}`), () => { location.hash = "#/notes"; });
      } }, "Delete"))));
    return () => clearTimeout(timer);
  }
}
