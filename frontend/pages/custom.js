// Your own tabs: a note page or a list of links. Only https links are clickable.
import { del, get, post, put } from "../api.js";
import { act, confirmDialog, emptyState, field, h, toast } from "../ui.js";

export const usesList = true;
const LINE = /^(.{1,80})\s*\|\s*(https:\/\/\S{3,300})$/;

export async function render({ list, main, arg }) {
  const body = h("div", { class: "items" });
  list.append(h("header", { class: "pane-head" }, h("h1", {}, "My tabs"),
    h("button", { class: "btn small", type: "button", onClick: () => { location.hash = "#/custom/new"; } }, "New tab")), body);
  const tabs = await get("/api/custom-tabs");
  body.replaceChildren(...(tabs.length ? tabs.map((t) => h("a", { class: `item${String(t.id) === arg ? " active" : ""}`, href: `#/custom/${t.id}` },
    h("div", { class: "item-text" }, h("strong", { class: "item-title" }, t.title), h("span", { class: "item-sub" }, t.kind === "links" ? "Links" : "Text")))) : [emptyState("No tabs yet", "Create a page for your own links or notes.")]));
  if (!arg) { main.append(emptyState("Pick a tab or create a new one")); return; }
  const tab = arg === "new" ? null : tabs.find((t) => String(t.id) === arg);
  if (arg !== "new" && !tab) { main.append(emptyState("Tab not found")); return; }

  const title = h("input", { class: "input", maxlength: "30", required: true, value: tab?.title || "" });
  const kind = h("select", { class: "input" }, [["text", "Text"], ["links", "List of links"]].map(([v, l]) => h("option", { value: v, selected: (tab?.kind || "text") === v }, l)));
  const content = h("textarea", { class: "input note-body", maxlength: "5000", placeholder: "Text, or one link per line:  Name | https://address" }, tab?.content || "");
  const preview = h("div", { class: "card" });
  const draw = () => {
    if (kind.value === "links") {
      const links = content.value.split("\n").map((l) => l.trim()).filter(Boolean);
      preview.replaceChildren(h("ul", { class: "rows" }, links.map((l) => { const m = LINE.exec(l); return m ? h("li", { class: "row" }, h("a", { href: m[2], target: "_blank", rel: "noopener noreferrer" }, m[1])) : h("li", { class: "row late" }, `Not a valid line: ${l}`); })));
    } else preview.replaceChildren(h("p", { class: "pre" }, content.value));
  };
  content.addEventListener("input", draw); kind.addEventListener("change", draw); draw();
  main.append(h("div", { class: "page" }, h("form", { onSubmit: async (e) => {
    e.preventDefault();
    try {
      const data = { title: title.value, kind: kind.value, content: content.value };
      if (tab) { await put(`/api/custom-tabs/${tab.id}`, data); toast("Saved."); } else { const r = await post("/api/custom-tabs", data); location.hash = `#/custom/${r.id}`; }
    } catch (err) { toast(err.message, "error"); }
  } }, field("Title", title), field("Type", kind), field("Content", content), h("div", { class: "button-row" }, h("button", { class: "btn primary", type: "submit" }, "Save"),
    tab ? h("button", { class: "btn danger", type: "button", onClick: async () => { if (await confirmDialog("Delete tab", `Delete “${tab.title}”?`, "Delete", true)) await act(del(`/api/custom-tabs/${tab.id}`), () => { location.hash = "#/custom"; }); } }, "Delete") : null)),
  h("h2", {}, "Preview"), preview));
}
