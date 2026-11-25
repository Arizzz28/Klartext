// Calendar: a month view with your events and the ones friends shared with you.
import { del, get, post, put } from "../api.js";
import { act, confirmDialog, field, fromLocalInput, h, longDate, modal, toLocalInput } from "../ui.js";

export const usesList = false;

export async function render({ main }) {
  let cursor = new Date(); cursor.setDate(1); cursor.setHours(0, 0, 0, 0);
  const page = h("div", { class: "page wide" }, h("h1", {}, "Calendar"));
  const head = h("div", { class: "cal-head" });
  const grid = h("div", { class: "cal-grid" });
  const agenda = h("section", { class: "card" });
  page.append(head, grid, agenda);
  main.append(page);

  async function load() {
    const start = new Date(cursor), end = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1);
    const events = await get(`/api/events?from=${start.getTime() / 1000}&to=${end.getTime() / 1000}`);
    head.replaceChildren(
      h("button", { class: "btn small", type: "button", onClick: () => { cursor.setMonth(cursor.getMonth() - 1); load(); } }, "‹"),
      h("strong", { class: "cal-title" }, cursor.toLocaleDateString("en-GB", { month: "long", year: "numeric" })),
      h("button", { class: "btn small", type: "button", onClick: () => { cursor.setMonth(cursor.getMonth() + 1); load(); } }, "›"),
      h("button", { class: "btn small primary", type: "button", onClick: () => editor(null) }, "New event"));
    const days = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate();
    const offset = (cursor.getDay() + 6) % 7;
    const cells = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"].map((d) => h("div", { class: "cal-dow" }, d));
    for (let i = 0; i < offset; i++) cells.push(h("div", { class: "cal-cell empty" }));
    for (let d = 1; d <= days; d++) {
      const dayEvents = events.filter((e) => new Date(e.start * 1000).getDate() === d);
      const isToday = new Date().toDateString() === new Date(cursor.getFullYear(), cursor.getMonth(), d).toDateString();
      cells.push(h("div", { class: `cal-cell${isToday ? " today" : ""}`, onClick: () => editor(null, new Date(cursor.getFullYear(), cursor.getMonth(), d, 12).getTime() / 1000) },
        h("span", { class: "cal-day" }, String(d)), ...dayEvents.slice(0, 3).map((e) => h("span", { class: "cal-ev" }, e.title)), dayEvents.length > 3 ? h("span", { class: "cal-ev" }, `+${dayEvents.length - 3}`) : null));
    }
    grid.replaceChildren(...cells);
    agenda.replaceChildren(h("h2", {}, "This month"), events.length ? h("ul", { class: "rows" }, events.map((e) => h("li", { class: "row" },
      h("div", { class: "item-text" }, h("strong", {}, e.title), h("span", { class: "item-sub" }, [longDate(e.start), e.mine ? (e.shared_with.length ? `shared with ${e.shared_with.join(", ")}` : "") : `from @${e.owner}`].filter(Boolean).join(" · "))),
      e.mine ? h("button", { class: "btn small", type: "button", onClick: () => editor(e) }, "Edit") : null))) : h("p", { class: "muted" }, "Nothing planned."));
  }

  function editor(ev, presetTs) {
    const title = h("input", { class: "input", maxlength: "120", required: true, value: ev?.title || "" });
    const start = h("input", { class: "input", type: "datetime-local", required: true, value: toLocalInput(ev?.start || presetTs || Date.now() / 1000 + 3600) });
    const end = h("input", { class: "input", type: "datetime-local", value: toLocalInput(ev?.end) });
    const note = h("textarea", { class: "input", rows: "3", maxlength: "1000" }, ev?.note || "");
    const share = h("input", { class: "input", placeholder: "usernames, comma separated", value: (ev?.shared_with || []).join(", ") });
    const msg = h("p", { class: "form-msg", role: "alert" });
    const form = h("form", { class: "dialog-body" }, field("Title", title), field("Starts", start), field("Ends (optional)", end), field("Note", note), field("Share with", share), msg,
      h("div", { class: "dialog-actions" }, ev ? h("button", { class: "btn danger", type: "button", onClick: async () => {
        if (await confirmDialog("Delete event", `Delete “${ev.title}”?`, "Delete", true)) { await act(del(`/api/events/${ev.id}`), load); box.close(); }
      } }, "Delete") : null, h("button", { class: "btn primary", type: "submit" }, "Save")));
    const box = modal(ev ? "Edit event" : "New event", form);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = { title: title.value, start: fromLocalInput(start.value), end: fromLocalInput(end.value), note: note.value,
        share_with: share.value.split(",").map((x) => x.trim()).filter(Boolean) };
      try { await (ev ? put(`/api/events/${ev.id}`, body) : post("/api/events", body)); box.close(); load(); }
      catch (err) { msg.textContent = err.message; msg.className = "form-msg error"; }
    });
  }
  await load();
}
