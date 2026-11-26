// Plans: which ranks exist, what each one gives you, what it costs in coins, and where to send an offer.
// No real money is involved anywhere in this app.
import { get, post } from "../api.js";
import { act, emptyState, h, rankTag } from "../ui.js";

export const usesList = false;

export async function render({ main, state }) {
  const page = h("div", { class: "page wide" }, h("h1", {}, "Plans"));
  main.append(page);
  let data;
  try { data = await get("/api/plans"); } catch (e) { page.append(emptyState("Couldn't load", e.message)); return; }

  page.append(h("p", { class: "muted" }, `Your rank: ${data.my_rank.name}. Ranks unlock features. You can rent one with coins (Missions tab) or send an offer.`));

  const cards = data.ranks.map((r) => {
    const card = h("section", { class: "card plan" + (r.is_mine ? " mine" : "") },
      h("h2", {}, rankTag(r), r.is_mine ? " · your rank" : ""),
      r.perks_text ? h("p", {}, r.perks_text) : null,
      r.new_features.length ? h("div", {}, h("strong", {}, "What is new here"), h("ul", {}, r.new_features.map((f) => h("li", {}, f)))) : null,
      h("details", {}, h("summary", {}, `All ${r.features.length} features`), h("ul", {}, r.features.map((f) => h("li", {}, f)))),
      h("p", { class: "muted" }, `${r.designs} design mode${r.designs === 1 ? "" : "s"}`),
      r.price ? h("p", {}, h("span", { class: "tag" }, `${r.price} coins for ${r.days} day${r.days === 1 ? "" : "s"}`), " ",
        state.can("shop.use") && !r.is_mine ? h("a", { href: "#/missions" }, "Rent it in the Missions tab") : null) : h("p", { class: "muted" }, "Not for rent. Ask with an offer."));
    return card;
  });
  page.append(data.ranks.length ? h("div", { class: "plans-grid" }, cards) : emptyState("No plans yet"));

  if (data.can_offer && data.offers_enabled) {
    const text = h("textarea", { class: "input", rows: "3", maxlength: "600", placeholder: "What can you offer? (help, an idea, a favour)" });
    page.append(h("section", { class: "card" }, h("h2", {}, "Make an offer"), h("p", { class: "muted" }, data.offers_rules),
      h("form", { onSubmit: (e) => { e.preventDefault(); act(post("/api/offers", { text: text.value }), () => { text.value = ""; }); } },
        text, h("div", { class: "button-row" }, h("button", { class: "btn primary", type: "submit" }, "Send offer")))));
  }
  if (data.support) page.append(h("section", { class: "card" }, h("h2", {}, "Support the servers"), h("p", {}, data.support)));
}
