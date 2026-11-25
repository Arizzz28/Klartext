// Missions (earn coins), the rank shop (rent a rank for a few days) and, for admins, gifts and mission management.
import { del, get, post, put } from "../api.js";
import { act, emptyState, field, h, longDate, rankTag, toast } from "../ui.js";

export const usesList = false;

export async function render({ main, state }) {
  const page = h("div", { class: "page wide" }, h("h1", {}, "Missions & coins"));
  main.append(page);
  const wallet = h("div", { class: "stat" });
  const missionsBox = h("section", { class: "card" });
  const shopBox = h("section", { class: "card" });
  const logBox = h("section", { class: "card" });
  page.append(h("div", { class: "stats" }, wallet), missionsBox, state.can("shop.use") ? shopBox : null, logBox);

  async function load() {
    const [coins, missions] = await Promise.all([get("/api/coins"), get("/api/missions")]);
    wallet.replaceChildren(h("strong", {}, String(coins.coins)), h("span", {}, "Coins"), h("small", {}, "Earn them with missions"));
    drawMissions(missions);
    if (state.can("shop.use")) drawShop(await get("/api/shop"));
    logBox.replaceChildren(h("h2", {}, "Recent coin activity"), coins.log.length
      ? h("ul", { class: "rows" }, coins.log.map((l) => h("li", { class: "row" }, h("span", { class: `coin-delta ${l.delta < 0 ? "neg" : "pos"}` }, (l.delta > 0 ? "+" : "") + l.delta),
        h("div", { class: "item-text" }, h("span", {}, l.reason), h("span", { class: "item-sub" }, longDate(l.ts))))))
      : emptyState("No coins yet", "Finish a mission to get your first coins."));
  }

  function drawMissions(data) {
    if (!data.enabled) { missionsBox.replaceChildren(h("h2", {}, "Missions"), h("p", { class: "muted" }, "Missions are switched off at the moment.")); return; }
    missionsBox.replaceChildren(h("h2", {}, "Missions"), data.missions.length ? h("ul", { class: "rows" }, data.missions.map((m) => {
      const pct = Math.round((m.progress / m.target) * 100);
      return h("li", { class: "row mission" },
        h("div", { class: "item-text" }, h("strong", {}, m.title),
          h("progress", { max: String(m.target), value: String(m.progress), "aria-label": `${m.progress} of ${m.target}` }),
          h("span", { class: "item-sub" }, `${m.progress} / ${m.target} · ${m.period === "daily" ? "resets every day" : "resets every week"} · ${pct}%`)),
        h("span", { class: "tag" }, `+${m.reward}`),
        m.claimed ? h("span", { class: "tag status-active" }, "Collected")
          : h("button", { class: "btn small primary", type: "button", disabled: !m.claimable, onClick: async () => { await act(post(`/api/missions/${m.id}/claim`), load); } }, "Collect"));
    })) : emptyState("No missions right now"));
  }

  function drawShop(shop) {
    if (!shop.enabled) { shopBox.replaceChildren(h("h2", {}, "Rank shop"), h("p", { class: "muted" }, "The shop is closed at the moment.")); return; }
    shopBox.replaceChildren(h("h2", {}, "Rent a rank"),
      h("p", { class: "muted" }, `Rent a rank with coins. It is temporary (at most ${shop.max_days} days in a row) and your own rank stays as it is.`),
      shop.lease ? h("p", { class: "notice" }, `You have ${shop.lease.rank.name} until ${longDate(shop.lease.until)}.`) : null,
      shop.items.length ? h("ul", { class: "rows" }, shop.items.map((i) => h("li", { class: "row" },
        h("div", { class: "item-text" }, h("strong", {}, i.rank.name, " ", rankTag(i.rank)), h("span", { class: "item-sub" }, `${i.days} day${i.days === 1 ? "" : "s"} · ${i.perm_count} features${i.designs.length > 1 ? ` · ${i.designs.length} designs` : ""}`)),
        h("span", { class: "tag" }, `${i.price} coins`),
        h("button", { class: "btn small primary", type: "button", disabled: shop.coins < i.price, onClick: async () => { await act(post("/api/shop/rent", { rank_id: i.rank_id }), async () => { await state.reloadMe(); await load(); }); } }, "Rent"))))
        : emptyState("Nothing for rent yet"));
  }

  // ---------- staff tools ----------
  if (state.can("coins.gift") || state.can("ranks.gift") || state.can("missions.manage")) page.append(await staffCard());

  async function staffCard() {
    const card = h("section", { class: "card" }, h("h2", {}, "Staff tools"));
    if (state.can("coins.gift")) {
      const who = h("input", { class: "input", placeholder: "username", maxlength: "20" });
      const amount = h("input", { class: "input", type: "number", min: "1", value: "50" });
      card.append(h("h3", {}, "Gift coins"), h("form", { class: "inline-form", onSubmit: (e) => { e.preventDefault(); act(post("/api/coins/gift", { username: who.value.trim(), amount: Number(amount.value) }), load); } },
        who, amount, h("button", { class: "btn primary", type: "submit" }, "Send")));
    }
    if (state.can("ranks.gift")) {
      const ranks = (await get("/api/admin/ranks")).ranks.filter((r) => !r.is_owner && (state.me.is_owner || r.level < state.me.rank_level));
      const who = h("input", { class: "input", placeholder: "username", maxlength: "20" });
      const rank = h("select", { class: "input" }, ranks.map((r) => h("option", { value: r.id }, r.name)));
      const days = h("input", { class: "input", type: "number", min: "1", max: "365", value: "3" });
      card.append(h("h3", {}, "Gift a rank for some days"), h("form", { class: "inline-form", onSubmit: (e) => { e.preventDefault(); act(post("/api/ranks/gift", { username: who.value.trim(), rank_id: rank.value, days: Number(days.value) })); } },
        who, rank, days, h("button", { class: "btn primary", type: "submit" }, "Gift")));
    }
    if (state.can("missions.manage")) {
      const box = h("div");
      async function drawMgmt() {
        const data = await get("/api/missions/manage");
        const title = h("input", { class: "input", placeholder: "Write 10 messages today", maxlength: "80" });
        const kind = h("select", { class: "input" }, Object.entries(data.kinds).map(([k, l]) => h("option", { value: k }, l)));
        const target = h("input", { class: "input", type: "number", min: "1", value: "10" });
        const period = h("select", { class: "input" }, [["daily", "per day"], ["weekly", "per week"]].map(([v, l]) => h("option", { value: v }, l)));
        const reward = h("input", { class: "input", type: "number", min: "1", value: "20" });
        box.replaceChildren(h("h3", {}, "Manage missions"),
          h("ul", { class: "rows" }, data.missions.map((m) => h("li", { class: "row" },
            h("div", { class: "item-text" }, h("strong", {}, m.title), h("span", { class: "item-sub" }, `${data.kinds[m.kind]} · ${m.target} · ${m.period} · +${m.reward}${m.active ? "" : " · off"}`)),
            h("button", { class: "btn small", type: "button", onClick: async () => { await act(put(`/api/missions/${m.id}`, { ...m, active: !m.active }), drawMgmt); } }, m.active ? "Turn off" : "Turn on"),
            h("button", { class: "btn small danger-text", type: "button", onClick: async () => { await act(del(`/api/missions/${m.id}`), async () => { await drawMgmt(); await load(); }); } }, "Delete")))),
          h("form", { class: "grid-form", onSubmit: async (e) => { e.preventDefault(); await act(post("/api/missions", { title: title.value, kind: kind.value, target: Number(target.value), period: period.value, reward: Number(reward.value) }), async () => { await drawMgmt(); await load(); }); } },
            field("Title", title), field("Counts", kind), field("Goal", target), field("Resets", period), field("Reward (coins)", reward),
            h("button", { class: "btn primary", type: "submit" }, "Add mission")));
      }
      await drawMgmt();
      card.append(box);
    }
    return card;
  }

  try { await load(); } catch (e) { page.append(emptyState("Couldn't load", e.message)); }
  const timer = setInterval(() => load().catch(() => {}), 30000);
  return () => clearInterval(timer);
}
