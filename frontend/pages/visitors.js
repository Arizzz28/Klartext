// Who looked at your profile recently.
import { get } from "../api.js";
import { avatar, emptyState, h, longDate } from "../ui.js";

export const usesList = false;

export async function render({ main }) {
  const data = await get("/api/me/visitors");
  main.append(h("div", { class: "page" }, h("h1", {}, "Profile visitors"),
    !data.enabled ? h("p", { class: "notice" }, "Visitor tracking is switched off by the Owner.") : h("p", { class: "muted" }, `Shows who opened your profile in the last ${data.keep_days} days (once per person and hour).`),
    data.visitors.length ? h("ul", { class: "rows" }, data.visitors.map((v) => h("li", { class: "row" }, avatar(v, "sm"),
      h("div", { class: "item-text" }, h("strong", {}, v.display_name), h("span", { class: "item-sub" }, `@${v.username} · ${longDate(v.ts)}`)))))
      : emptyState("No visitors yet")));
}
