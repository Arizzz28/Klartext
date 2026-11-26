// Fun tab: daily streak, badges, polls.
import { get, post } from "../api.js";
import { h, toast } from "../ui.js";

export const usesList = false;

export async function render({ main }) {
  const page = h("div", { class: "page" }, h("h1", {}, "Fun"));
  main.append(page);
  const streakBox = h("section", { class: "card" }), badgeBox = h("section", { class: "card" }), pollBox = h("section", { class: "card" });
  page.append(streakBox, badgeBox, pollBox);

  async function loadOverview() {
    const o = await get("/api/fun");
    streakBox.replaceChildren(h("h2", {}, "Daily streak"),
      h("p", {}, `Current streak: ${o.streak} day(s) · best: ${o.best}`),
      h("button", { class: "btn primary", type: "button", disabled: o.claimed_today, onClick: async () => {
        try { const r = await post("/api/fun/streak"); toast(r.message); loadOverview(); } catch (e) { toast(e.message, "error"); }
      } }, o.claimed_today ? "Collected today ✓" : `Collect +${o.next_reward} coins`),
      h("p", { class: "muted" }, "Come back every day: the reward grows up to day 7. Miss a day and the streak starts again."));
    badgeBox.replaceChildren(h("h2", {}, "Badges"), h("div", { class: "stats" }, o.badges.map((b) =>
      h("div", { class: "stat", style: b.earned ? "" : "opacity:.5" }, h("strong", {}, `${b.earned ? "🏅" : "🔒"} ${b.name}`), h("span", {}, b.text)))));
  }

  async function loadPolls() {
    const d = await get("/api/fun/polls");
    const q = h("input", { class: "input", maxlength: "150", placeholder: "Question" });
    const opts = [h("input", { class: "input", maxlength: "60", placeholder: "Answer 1" }), h("input", { class: "input", maxlength: "60", placeholder: "Answer 2" }), h("input", { class: "input", maxlength: "60", placeholder: "Answer 3 (optional)" })];
    const create = d.can_create ? h("form", { class: "stack", onSubmit: async (e) => {
      e.preventDefault();
      try { await post("/api/fun/polls", { question: q.value, options: opts.map((o) => o.value) }); q.value = ""; opts.forEach((o) => { o.value = ""; }); loadPolls(); } catch (er) { toast(er.message, "error"); }
    } }, h("h3", {}, "New poll"), q, ...opts, h("button", { class: "btn", type: "submit" }, "Create poll")) : null;
    pollBox.replaceChildren(h("h2", {}, "Polls"), create, ...(d.polls.length ? d.polls.map((p) => {
      const total = p.options.reduce((s, o) => s + o.votes, 0) || 1;
      return h("div", { class: "poll" }, h("strong", {}, p.question), h("small", { class: "muted" }, ` by ${p.author}${p.closed ? " · closed" : ""}`),
        p.options.map((o, i) => h("button", { class: `btn small poll-opt${p.my_vote === i ? " primary" : ""}`, type: "button", disabled: p.my_vote !== null || p.closed,
          onClick: async () => { try { await post(`/api/fun/polls/${p.id}/vote`, { choice: i }); loadPolls(); } catch (e) { toast(e.message, "error"); } } },
          `${o.text} – ${o.votes} (${Math.round((o.votes / total) * 100)}%)`)),
        !p.closed ? h("button", { class: "btn small", type: "button", onClick: async () => { await post(`/api/fun/polls/${p.id}/close`).catch((e) => toast(e.message, "error")); loadPolls(); } }, "Close poll") : null);
    }) : [h("p", { class: "muted" }, "No polls yet.")]));
  }
  await Promise.all([loadOverview(), loadPolls()]);
}
