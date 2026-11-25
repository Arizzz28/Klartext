// Dialog to choose which tabs sit in the sidebar and in what order (permission tabs.editor).
import { put } from "./api.js";
import { availableTabs, pinnedTabs } from "./tabs.js";
import { h, icon, modal, toast } from "./ui.js";

export function openTabEditor(state) {
  const all = availableTabs(state.me).filter((t) => t.id !== "settings");
  let order = pinnedTabs(state.me).filter((t) => t.id !== "settings").map((t) => t.id);
  const rest = () => all.map((t) => t.id).filter((id) => !order.includes(id));
  const list = h("ul", { class: "rows tab-editor" });
  const byId = Object.fromEntries(all.map((t) => [t.id, t]));

  function draw() {
    const row = (id, pinned, i) => h("li", { class: "row" }, icon(byId[id].icon), h("strong", { class: "item-text" }, byId[id].label),
      pinned ? h("button", { class: "icon-btn small", type: "button", "aria-label": "Move up", disabled: i === 0, onClick: () => { [order[i - 1], order[i]] = [order[i], order[i - 1]]; draw(); } }, "↑") : null,
      pinned ? h("button", { class: "icon-btn small", type: "button", "aria-label": "Move down", disabled: i === order.length - 1, onClick: () => { [order[i + 1], order[i]] = [order[i], order[i + 1]]; draw(); } }, "↓") : null,
      h("button", { class: "btn small", type: "button", onClick: () => { order = pinned ? order.filter((x) => x !== id) : [...order, id]; draw(); } }, pinned ? "Hide" : "Show"));
    list.replaceChildren(
      h("h3", { class: "section-title" }, "In the sidebar"), ...order.map((id, i) => row(id, true, i)),
      h("h3", { class: "section-title" }, "Only in the tab bubble / “More”"), ...rest().map((id) => row(id, false, 0)));
  }
  draw();
  const body = h("div", { class: "dialog-body" }, h("p", { class: "muted" }, "Settings is always in the sidebar. All your tabs are always reachable through the bubble."), list,
    h("div", { class: "dialog-actions" },
      h("button", { class: "btn", type: "button", onClick: () => box.close() }, "Cancel"),
      h("button", { class: "btn primary", type: "button", onClick: async () => {
        try { state.me = await put("/api/me/prefs", { tabs: order }); state.onMeChanged(); box.close(); toast("Saved."); }
        catch (e) { toast(e.message, "error"); }
      } }, "Save")));
  const box = modal("Edit tabs", body);
}
