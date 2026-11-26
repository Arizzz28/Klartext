// Missions (earn coins), coins between friends, the rank shop and, for admins, gifts, mission management and translation checks.
import { del, get, post, put } from "../api.js";
import { act, emptyState, field, h, longDate, rankTag, toast } from "../ui.js";

export const usesList = false;

const left = (s) => (s >= 86400 ? `${Math.ceil(s / 86400)} d` : s >= 3600 ? `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min` : `${Math.max(1, Math.floor(s / 60))} min`);

export async function render({ main, state }) {
  const page = h("div", { class: "page wide" }, h("h1", {}, "Missions & coins"));
  main.append(page);
  const wallet = h("div", { class: "stat" });
  const missionsBox = h("section", { class: "card" });
  const sendBox = h("section", { class: "card" });
  const shopBox = h("section", { class: "card" });
  const logBox = h("section", { class: "card" });
  page.append(h("div", { class: "stats" }, wallet), missionsBox, state.can("coins.send") ? sendBox : null, state.can("shop.use") ? shopBox : null, logBox);

  async function load() {
    const [coins, missions] = await Promise.all([get("/api/coins"), get("/api/missions")]);
    wallet.replaceChildren(h("strong", {}, String(coins.coins)), h("span", {}, "Coins"), h("small", {}, "Earn them with missions"));
    drawMissions(missions);
    if (state.can("coins.send")) drawSend();
    if (state.can("shop.use")) drawShop(await get("/api/shop"));
    logBox.replaceChildren(h("h2", {}, "Recent coin activity"), coins.log.length
      ? h("ul", { class: "rows" }, coins.log.map((l) => h("li", { class: "row" }, h("span", { class: `coin-delta ${l.delta < 0 ? "neg" : "pos"}` }, (l.delta > 0 ? "+" : "") + l.delta),
        h("div", { class: "item-text" }, h("span", {}, l.reason), h("span", { class: "item-sub" }, longDate(l.ts))))))
      : emptyState("No coins yet", "Finish a mission to get your first coins."));
  }

  function rarityTag(m) {
    const t = h("span", { class: "tag", title: `About ${m.chance}% of all draws` }, m.rarity_label);
    t.style.background = m.rarity_color; t.style.color = "#fff";
    return t;
  }

  function translateBox(m) {
    const inputs = new Map();
    const rows = m.tasks.map((t) => {
      const input = h("input", { class: "input", maxlength: "400", value: t.answer, placeholder: "German translation", disabled: t.status === "approved" || t.status === "submitted" });
      inputs.set(t.id, input);
      const status = { approved: "✓ approved", submitted: "waiting for the check", open: t.note ? `try again: ${t.note}` : "" }[t.status] || "";
      return h("div", { class: "row" }, h("div", { class: "item-text" }, h("strong", {}, `“${t.source}”`), t.hint ? h("span", { class: "item-sub" }, t.hint) : null, input,
        status ? h("span", { class: "item-sub" }, status) : null));
    });
    return h("details", { class: "translate" }, h("summary", {}, "Translate (" + m.tasks.filter((t) => t.status === "approved").length + "/" + m.target + " approved)"), ...rows,
      h("button", { class: "btn small primary", type: "button", onClick: async () => {
        const answers = {}; for (const [id, el] of inputs) if (!el.disabled && el.value.trim()) answers[id] = el.value.trim();
        await act(post(`/api/missions/${m.id}/translate`, { answers }), load);
      } }, "Send for checking"));
  }

  function drawMissions(data) {
    if (!data.enabled) { missionsBox.replaceChildren(h("h2", {}, "Missions"), h("p", { class: "muted" }, "Missions are switched off at the moment.")); return; }
    const hint = data.mode === "random" ? "Your missions are drawn for you. Rare ones are worth more." : "";
    missionsBox.replaceChildren(h("h2", {}, "Missions"), hint ? h("p", { class: "muted" }, hint) : null, data.missions.length ? h("ul", { class: "rows" }, data.missions.map((m) => {
      const pct = Math.round((m.progress / m.target) * 100);
      const free = m.kind === "none";
      return h("li", { class: "row mission" },
        h("div", { class: "item-text" }, h("strong", {}, m.title, " ", rarityTag(m)),
          free ? null : h("progress", { max: String(m.target), value: String(m.progress), "aria-label": `${m.progress} of ${m.target}` }),
          h("span", { class: "item-sub" }, `${free ? "Free" : `${m.progress} / ${m.target} · ${pct}%`} · new in ${left(m.resets_in)}`),
          m.kind === "translate" ? translateBox(m) : null),
        h("span", { class: "tag" }, `+${m.reward}`),
        m.claimed ? h("span", { class: "tag status-active" }, "Collected")
          : h("button", { class: "btn small primary", type: "button", disabled: !m.claimable, onClick: async () => { await act(post(`/api/missions/${m.id}/claim`), load); } }, "Collect"));
    })) : emptyState("No missions right now", "New ones are drawn when the time is up."));
  }

  function drawSend() {
    const who = h("input", { class: "input", placeholder: "username", maxlength: "20" });
    const amount = h("input", { class: "input", type: "number", min: "1", value: "10" });
    sendBox.replaceChildren(h("h2", {}, "Send coins to a friend"), h("p", { class: "muted" }, "You send your own coins. There is a daily limit."),
      h("form", { class: "inline-form", onSubmit: (e) => { e.preventDefault(); act(post("/api/coins/send", { username: who.value.trim(), amount: Number(amount.value) }), load); } },
        who, amount, h("button", { class: "btn primary", type: "submit" }, "Send")));
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
  if (state.can("coins.gift") || state.can("ranks.gift") || state.can("missions.manage") || state.can("translations.review")) page.append(await staffCard());

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
    if (state.can("translations.review")) {
      const box = h("div");
      async function drawReview() {
        const data = await get("/api/translations/review");
        box.replaceChildren(h("h3", {}, `Translations to check (${data.items.length})`), data.items.length ? h("ul", { class: "rows" }, data.items.map((t) => {
          const note = h("input", { class: "input", maxlength: "200", placeholder: "Note for the person (optional)" });
          return h("li", { class: "row" }, h("div", { class: "item-text" }, h("strong", {}, `“${t.source}”`), h("span", {}, `${t.display_name}: ${t.answer}`), note),
            h("button", { class: "btn small primary", type: "button", onClick: () => act(post(`/api/translations/${t.id}/review`, { approve: true, note: note.value }), async () => { await drawReview(); await load(); }) }, "Correct"),
            h("button", { class: "btn small danger-text", type: "button", onClick: () => act(post(`/api/translations/${t.id}/review`, { approve: false, note: note.value }), drawReview) }, "Wrong"));
        })) : h("p", { class: "muted" }, "Nothing to check."));
      }
      await drawReview();
      card.append(box);
    }
    if (state.can("missions.manage")) {
      const box = h("div");
      async function drawMgmt() {
        const data = await get("/api/missions/manage");
        const title = h("input", { class: "input", placeholder: "Write 10 messages today", maxlength: "80" });
        const kind = h("select", { class: "input" }, Object.entries(data.kinds).map(([k, l]) => h("option", { value: k }, l)));
        const target = h("input", { class: "input", type: "number", min: "1", value: "10" });
        const period = h("select", { class: "input" }, Object.entries(data.periods).map(([v, l]) => h("option", { value: v, selected: v === "daily" }, l)));
        const rarity = h("select", { class: "input" }, Object.entries(data.rarities).map(([v, r]) => h("option", { value: v }, `${r.label} (${r.chance}%)`)));
        const reward = h("input", { class: "input", type: "number", min: "1", value: "20" });
        box.replaceChildren(h("h3", {}, "Manage missions"),
          h("p", { class: "hint" }, "“Nothing to do” gives a free reward (goal = 1). “Translate” gives people that many texts; an admin checks them."),
          h("ul", { class: "rows" }, data.missions.map((m) => h("li", { class: "row" },
            h("div", { class: "item-text" }, h("strong", {}, m.title), h("span", { class: "item-sub" }, `${data.kinds[m.kind]} · goal ${m.target} · ${data.periods[m.period]} · ${(data.rarities[m.rarity] || {}).label} · +${m.reward}${m.active ? "" : " · off"}`)),
            h("button", { class: "btn small", type: "button", onClick: async () => { await act(put(`/api/missions/${m.id}`, { ...m, active: !m.active }), drawMgmt); } }, m.active ? "Turn off" : "Turn on"),
            h("button", { class: "btn small danger-text", type: "button", onClick: async () => { await act(del(`/api/missions/${m.id}`), async () => { await drawMgmt(); await load(); }); } }, "Delete")))),
          h("form", { class: "grid-form", onSubmit: async (e) => { e.preventDefault(); await act(post("/api/missions", { title: title.value, kind: kind.value, target: Number(target.value), period: period.value, reward: Number(reward.value), rarity: rarity.value }), async () => { await drawMgmt(); await load(); }); } },
            field("Title", title), field("Counts", kind), field("Goal", target), field("New after", period), field("Rarity", rarity), field("Reward (coins)", reward),
            h("button", { class: "btn primary", type: "submit" }, "Add mission")),
          await itemsBox());
      }
      async function itemsBox() {
        const data = await get("/api/translations/items");
        const text = h("input", { class: "input", maxlength: "300", placeholder: "Text from the website, in English" });
        return h("details", {}, h("summary", {}, `Texts for translation missions (${data.items.filter((i) => i.active).length})`),
          h("ul", { class: "rows" }, data.items.filter((i) => i.active).map((i) => h("li", { class: "row" }, h("span", { class: "item-text" }, i.source),
            h("button", { class: "btn small danger-text", type: "button", onClick: () => act(del(`/api/translations/items/${i.id}`), drawMgmt) }, "Remove")))),
          h("form", { class: "inline-form", onSubmit: (e) => { e.preventDefault(); act(post("/api/translations/items", { source: text.value }), drawMgmt); } }, text, h("button", { class: "btn primary", type: "submit" }, "Add text")));
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
