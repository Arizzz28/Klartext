// Admin -> Translations: write, check and approve translations. Only approved ones are shown to people.
import { get, post, put } from "../api.js";
import { h, toast } from "../ui.js";

export async function i18nView() {
  const box = h("div");
  let flt = "open", q = "";
  async function load() {
    const d = await get(`/api/admin/i18n?lang=de&filter=${flt}&q=${encodeURIComponent(q)}`);
    const sel = h("select", { class: "input", onChange: (e) => { flt = e.target.value; load(); } },
      [["open", "Not translated yet"], ["draft", "Waiting for approval"], ["approved", "Approved"], ["all", "All"]].map(([v, l]) => h("option", { value: v, selected: flt === v }, l)));
    const search = h("input", { class: "input", placeholder: "Search…", value: q });
    search.addEventListener("change", () => { q = search.value; load(); });
    const add = h("input", { class: "input", maxlength: "300", placeholder: "Add a text that can be translated" });
    box.replaceChildren(
      h("h2", {}, "Translations: Deutsch"),
      h("p", {}, `${d.approved} of ${d.total} texts approved (${d.total ? Math.round((100 * d.approved) / d.total) : 0}%). Only approved translations are used. The language shows “partly translated” until all are approved.`),
      h("div", { class: "grow" }, sel, search,
        h("button", { class: "btn small", type: "button", onClick: async () => { const r = await post("/api/admin/i18n/approve-all", { lang: "de" }); toast(`${r.approved} approved.`); load(); } }, "Approve all waiting")),
      h("form", { class: "grow", onSubmit: async (e) => { e.preventDefault(); try { await post("/api/admin/i18n/source", { source: add.value }); add.value = ""; load(); } catch (er) { toast(er.message, "error"); } } },
        add, h("button", { class: "btn small", type: "submit" }, "Add a text")),
      ...d.rows.map((r) => {
        const ta = h("input", { class: "input", value: r.text, placeholder: "Translation" });
        const save = (approved) => async () => { try { await put("/api/admin/i18n", { lang: "de", source: r.source, text: ta.value, approved }); toast(approved ? "Approved." : "Saved as draft."); } catch (e) { toast(e.message, "error"); } };
        return h("div", { class: "row" }, h("div", { style: "flex:1;min-width:200px" }, h("strong", { translate: "no" }, r.source), ta),
          h("button", { class: "btn small", type: "button", onClick: save(false) }, "Save draft"),
          h("button", { class: `btn small${r.approved ? "" : " primary"}`, type: "button", onClick: save(true) }, r.approved ? "Re-approve" : "Approve"));
      }), d.rows.length === 100 ? h("p", { class: "muted" }, "Showing the first 100. Use the search or filter.") : null);
  }
  await load();
  return box;
}
