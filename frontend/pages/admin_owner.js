// Admin tabs for ranks, settings, notes, What's New and ads. Used by admin.js.
// The sections only the Owner may change are hidden for everybody else AND refused by the server.
import { del, get, patch, post, put } from "../api.js";
import { TABS } from "../tabs.js";
import { act, confirmDialog, emptyState, field, h, rankTag, toast } from "../ui.js";
import { uploadFile } from "../upload.js";

const check = (v, label, hint = "") => {
  const el = h("input", { type: "checkbox", checked: Boolean(v) });
  return { el, row: h("label", { class: "choice" }, el, h("span", {}, h("strong", {}, label), hint ? h("small", {}, hint) : null)) };
};
const num = (v, min, max) => h("input", { class: "input", type: "number", min, max, value: String(v) });

export function ownerTabs({ state, reload, when }) {
  const can = (p) => state.can(p);

  // ---------- ranks ----------
  async function ranksView() {
    const data = await get("/api/admin/ranks");
    const groups = {};
    for (const p of data.registry) (groups[p.group] ||= []).push(p);

    function editRank(rank) {
      const isNew = !rank;
      const r = rank || { name: "", level: 25, color: "#0e8a96", perms: [], designs: ["classic"] };
      const name = h("input", { class: "input", maxlength: "24", value: r.name, required: true });
      const level = h("input", { class: "input", type: "number", min: "1", max: "99", value: String(r.level), disabled: Boolean(r.is_owner) });
      const color = h("input", { type: "color", value: r.color || "#888888" });
      const offered = h("input", { type: "checkbox", checked: r.offered !== false });
      const perks = h("textarea", { class: "input", rows: "2", maxlength: "400", placeholder: "Extra advantages in your own words (shown in the Plans tab)" }, r.perks_text || "");
      const perms = new Set(r.perms);
      const designs = new Set(r.designs);
      const permBoxes = Object.entries(groups).map(([group, items]) => h("fieldset", { class: "perm-group" }, h("legend", {}, group),
        ...items.map((p) => {
          const cb = h("input", { type: "checkbox", checked: perms.has(p.key) || Boolean(r.is_owner), disabled: Boolean(r.is_owner) });
          cb.addEventListener("change", () => (cb.checked ? perms.add(p.key) : perms.delete(p.key)));
          return h("label", { class: "choice" }, cb, h("span", {}, h("strong", {}, p.label), h("small", {}, p.built ? p.key : `${p.key} · not built yet`)));
        })));
      const designBoxes = Object.entries(data.designs).map(([id, label]) => {
        const cb = h("input", { type: "checkbox", checked: designs.has(id), disabled: Boolean(r.is_owner) });
        cb.addEventListener("change", () => (cb.checked ? designs.add(id) : designs.delete(id)));
        return h("label", { class: "choice" }, cb, h("span", {}, h("strong", {}, label)));
      });
      const body = h("form", { class: "card rank-form", onSubmit: async (e) => {
        e.preventDefault();
        const payload = { name: name.value, level: Number(level.value), color: color.value, perms: [...perms], designs: [...designs], offered: offered.checked, perks_text: perks.value };
        const res = await act(isNew ? post("/api/admin/ranks", payload) : put(`/api/admin/ranks/${r.id}`, payload), reload);
        if (res) toast("Saved.");
      } },
      h("h2", {}, isNew ? "New rank" : `Edit ${r.name}`),
      r.is_owner ? h("p", { class: "muted" }, "The Owner rank always has every permission. You can only rename it or change its colour.") : null,
      h("div", { class: "grid-2" }, field("Name", name), field("Level (1–99, higher = more power)", level), field("Colour", color)),
      h("label", { class: "choice" }, offered, h("span", {}, h("strong", {}, "Show this rank in the Plans tab"), h("small", {}, "Off = hidden from the Plans tab (nothing is deleted, people who have it keep it)"))),
      field("Advantages (text)", perks),
      h("h3", {}, "Design modes"), h("div", { class: "choices" }, ...designBoxes),
      h("h3", {}, "Permissions"), ...permBoxes,
      h("div", { class: "button-row" }, h("button", { class: "btn primary", type: "submit" }, "Save"),
        h("button", { class: "btn", type: "button", onClick: reload }, "Cancel")));
      return body;
    }

    const content = h("div", {});
    const list = () => h("ul", { class: "rows" }, data.ranks.map((r) => h("li", { class: "row" },
      h("div", { class: "item-text" }, h("strong", {}, rankTag(r), ` level ${r.level}`),
        h("span", { class: "item-sub" }, `${r.users} account(s) · ${r.is_owner ? "all permissions" : `${r.perms.length} permissions`} · designs: ${r.designs.join(", ")}`)),
      data.can_edit ? h("button", { class: "btn small", type: "button", onClick: () => content.replaceChildren(editRank(r)) }, "Edit") : null,
      data.can_edit && !r.is_owner ? h("button", { class: "btn small danger-text", type: "button", onClick: async () => {
        if (await confirmDialog("Delete rank", `Delete “${r.name}”? The ${r.users} account(s) with this rank move to the standard rank.`, "Delete", true)) act(del(`/api/admin/ranks/${r.id}`), reload);
      } }, "Delete") : null)));
    content.append(
      data.can_edit ? h("div", { class: "toolbar-row" }, h("button", { class: "btn primary", type: "button", onClick: () => content.replaceChildren(editRank(null)) }, "New rank")) : h("p", { class: "muted" }, "Only the Owner can change ranks."),
      list(),
      data.registry.some((p) => !p.built) ? h("p", { class: "hint" }, "Permissions marked “not built yet” exist so ranks can be prepared, but the feature itself is not part of this version.") : null);
    return content;
  }

  // ---------- notes of a user (logged, the person is told) ----------
  async function notesView() {
    const input = h("input", { class: "input", placeholder: "Username", maxlength: "20", "aria-label": "Username" });
    const out = h("div", {});
    async function open() {
      const name = input.value.trim();
      if (!name) return;
      try {
        const res = await get(`/api/notes/of/${encodeURIComponent(name)}`);
        out.replaceChildren(h("p", { class: "notice" }, "This access was written to the audit log and the person was notified."),
          res.notes.length ? res.notes.map((n) => h("div", { class: "report" }, h("strong", {}, n.title || "(no title)"), h("p", { class: "pre" }, n.body))) : emptyState("This person has no notes"));
      } catch (e) { out.replaceChildren(emptyState("Couldn't open the notes", e.message)); }
    }
    return h("div", {},
      h("p", { class: "muted" }, "Notes are private by default. Looking at them is logged and the person gets a notice. You can only open notes of people whose rank is below yours."),
      h("form", { class: "invite-form", onSubmit: (e) => { e.preventDefault(); open(); } }, input, h("button", { class: "btn primary", type: "submit" }, "Open notes")), out);
  }

  // ---------- What's New ----------
  async function releasesView() {
    const rows = await get("/api/releases");
    const id = h("input", { class: "input", maxlength: "20", placeholder: "3.1.0", required: true });
    const title = h("input", { class: "input", maxlength: "100", required: true });
    const body = h("textarea", { class: "input", rows: "5", maxlength: "4000" });
    return h("div", {},
      h("form", { class: "card", onSubmit: (e) => { e.preventDefault(); act(post("/api/releases", { id: id.value, title: title.value, body: body.value }), reload); } },
        h("h2", {}, "Publish an update note"), h("p", { class: "muted" }, "Everybody sees it as “new” until they open What's New."),
        h("div", { class: "grid-2" }, field("Release ID", id), field("Title", title)), field("Text", body), h("button", { class: "btn primary", type: "submit" }, "Publish")),
      rows.length ? h("ul", { class: "rows" }, rows.map((r) => h("li", { class: "row" },
        h("div", { class: "item-text" }, h("strong", {}, `${r.id} · ${r.title}`), h("span", { class: "item-sub" }, when(r.created))),
        h("button", { class: "btn small danger-text", type: "button", onClick: () => act(del(`/api/releases/${encodeURIComponent(r.id)}`), reload) }, "Delete")))) : emptyState("No entries yet"));
  }

  // ---------- ads / videos ----------
  async function adsView() {
    const rows = await get("/api/ads/manage");
    const kind = h("select", { class: "input" }, h("option", { value: "banner" }, "Banner"), h("option", { value: "video" }, "Video link"));
    const title = h("input", { class: "input", maxlength: "80", required: true });
    const url = h("input", { class: "input", type: "url", placeholder: "https://…", required: true });
    const body = h("input", { class: "input", maxlength: "300" });
    return h("div", {},
      h("p", { class: "muted" }, "Ads are switched on or off by the Owner in Settings. Only https links are accepted; nothing is loaded from other websites automatically."),
      h("form", { class: "card", onSubmit: (e) => { e.preventDefault(); act(post("/api/ads", { kind: kind.value, title: title.value, url: url.value, body: body.value }), reload); } },
        h("div", { class: "grid-2" }, field("Type", kind), field("Title", title)), field("Link", url), field("Text (optional)", body), h("button", { class: "btn primary", type: "submit" }, "Add")),
      rows.length ? h("ul", { class: "rows" }, rows.map((r) => h("li", { class: "row" },
        h("div", { class: "item-text" }, h("strong", {}, `${r.title} (${r.kind})`), h("span", { class: "item-sub" }, r.url)),
        h("button", { class: "btn small", type: "button", onClick: () => act(patch(`/api/ads/${r.id}`, { active: !r.active }), reload) }, r.active ? "Hide" : "Show"),
        h("button", { class: "btn small danger-text", type: "button", onClick: () => act(del(`/api/ads/${r.id}`), reload) }, "Delete")))) : emptyState("No ads yet"));
  }

  // ---------- settings ----------
  async function settingsView() {
    const { settings: s, storage_configured: storageOk, presets, loading_preview: preview, owner_config: isOwnerCfg, stat_keys: statKeys } = await get("/api/admin/settings");
    const ld = s.loading;
    const assets = { image: undefined, music: undefined };
    const mode = h("select", { class: "input" }, [["whitelist", "Whitelist only"], ["open_approval", "Open, admin approves each account"], ["closed", "Closed"]].map(([v, l]) => h("option", { value: v, selected: s.registration_mode === v }, l)));
    const announcement = h("input", { class: "input", maxlength: "300", value: s.announcement, placeholder: "Shown to everybody at the top. Empty = no banner." });
    const startPage = h("select", { class: "input" }, TABS.filter((t) => t.id !== "admin").map((t) => h("option", { value: t.id, selected: s.start_page === t.id }, t.label)));
    const perMinute = num(s.messages_per_minute, 1, 600);
    const uploadsOn = check(s.uploads_enabled, "Uploads allowed", storageOk ? "" : "File storage is not configured on the server.");
    const maxImage = num(s.max_image_mb, 1, 200), maxVideo = num(s.max_video_mb, 1, 200), maxFile = num(s.max_file_mb, 1, 200), quota = num(s.user_quota_mb, 10, 100000);
    const blocked = h("input", { class: "input", value: s.blocked_extensions.join(", ") });
    const title = h("input", { class: "input", maxlength: "40", value: ld.title });
    const volume = h("input", { type: "range", min: "0", max: "1", step: "0.05", value: String(ld.music_volume) });
    const allowImg = check(ld.allow_user_image, "Everybody may set their own loading picture");
    const allowMusic = check(ld.allow_user_music, "Everybody may set their own loading music");
    const allowMute = check(ld.allow_user_mute, "Everybody may turn the music off");
    const maxLoadImg = num(ld.max_image_mb, 1, 20), maxLoadMusic = num(ld.max_music_mb, 1, 50);
    const bgDefault = h("select", { class: "input" }, [h("option", { value: "" }, "None"), ...presets.map((p) => h("option", { value: p, selected: s.background.default === p }, p))]);
    const bgCustom = check(s.background.allow_custom, "Everybody may use their own chat background pictures");
    const imgPreview = h("div", { class: "loading-preview" }, preview.image ? h("img", { src: preview.image, alt: "" }) : h("span", { class: "muted" }, "No picture set."));
    const musicPreview = h("div", {}, preview.music ? h("audio", { controls: true, src: preview.music }) : h("span", { class: "muted" }, "No music set."));
    const status = h("p", { class: "muted" });
    // ---- games (admins decide: on/off, order, points needed to unlock the next game, switched-off games)
    const gl = await get("/api/games").catch(() => ({ games: [] }));
    const gset = s.games || { enabled: true, sequential: true, order: [], unlock: {}, disabled: [] };
    const gamesOn = check(gset.enabled, "Games are allowed");
    const gamesSeq = check(gset.sequential, "Games unlock one after the other (by points)");
    let gOrder = gl.games.map((x) => x.id);
    const gInfo = Object.fromEntries(gl.games.map((x) => [x.id, x]));
    const gPoints = Object.fromEntries(gl.games.map((x) => [x.id, num(gset.unlock?.[x.id] ?? x.unlock_points, 0, 100000)]));
    const gOff = Object.fromEntries(gl.games.map((x) => [x.id, check((gset.disabled || []).includes(x.id), "off")]));
    const gamesList = h("div");
    function drawGames() {
      gamesList.replaceChildren(...gOrder.map((id, i) => h("div", { class: "row" }, h("strong", {}, `${i + 1}. ${gInfo[id].name}`),
        h("button", { class: "btn small", type: "button", disabled: i === 0, onClick: () => { [gOrder[i - 1], gOrder[i]] = [gOrder[i], gOrder[i - 1]]; drawGames(); } }, "↑"),
        h("button", { class: "btn small", type: "button", disabled: i === gOrder.length - 1, onClick: () => { [gOrder[i + 1], gOrder[i]] = [gOrder[i], gOrder[i + 1]]; drawGames(); } }, "↓"),
        field("Points needed in the game before this one", gPoints[id]), gOff[id].row)));
    }
    drawGames();
    const gamesCard = h("section", { class: "card" }, h("h2", {}, "Games"), gamesOn.row, gamesSeq.row,
      h("p", { class: "muted" }, "Order and unlock points only matter when the games unlock one after the other. The first game a person may play is always open. Only games that a rank includes (Owner: Ranks) appear for that rank."), gamesList);
    function collectGames() {
      return { games: { enabled: gamesOn.el.checked, sequential: gamesSeq.el.checked, order: gOrder, disabled: gOrder.filter((id) => gOff[id].el.checked),
        unlock: Object.fromEntries(gOrder.map((id) => [id, Number(gPoints[id].value)])) } };
    }
    function assetButtons(kind, field_, accept, previewEl, render) {
      const pick = h("button", { class: "btn small", type: "button", onClick: () => {
        const input = h("input", { type: "file", accept });
        input.addEventListener("change", async () => {
          if (!input.files[0]) return;
          status.textContent = "Uploading…";
          try { const att = await uploadFile(input.files[0], { kind }).promise; assets[field_] = att.id; previewEl.replaceChildren(render(att.url)); status.textContent = "Uploaded. Press “Save settings” to use it."; }
          catch (e) { status.textContent = ""; toast(e.message, "error"); }
        });
        input.click();
      } }, "Choose file");
      const remove = h("button", { class: "btn small danger-text", type: "button", onClick: () => { assets[field_] = ""; previewEl.replaceChildren(h("span", { class: "muted" }, "Will be removed when you save.")); } }, "Remove");
      return h("div", { class: "button-row" }, pick, remove);
    }

    // ----- Owner-only blocks -----
    let ownerBlock = null, collectOwner = () => ({});
    if (isOwnerCfg) {
      const { ranks } = await get("/api/admin/ranks");
      const lowRanks = ranks.filter((r) => !r.is_owner && r.level < 60);
      const defRank = h("select", { class: "input" }, lowRanks.map((r) => h("option", { value: r.id, selected: s.default_rank === r.id }, r.name)));
      const offersOn = check(s.offers.enabled, "Pro offers are open");
      const offerRules = h("textarea", { class: "input", rows: "3", maxlength: "1000" }, s.offers.rules);
      const statBoxes = Object.entries(statKeys).map(([k, l]) => ({ k, ...check(s.stats.enabled.includes(k), l) }));
      const aiOn = check(s.ai.enabled, "AI tab is switched on", "Needs GEMINI_API_KEY on the server. Read the AI notes in the README first: in the EU/EEA, Switzerland and the UK Google allows only paid access for apps offered to other people, and the free tier lets Google use and read the content.");
      const aiLimit = num(s.ai.daily_limit, 1, 500), aiCtx = num(s.ai.max_context_messages, 0, 100);
      const adsOn = check(s.ads.enabled, "Show ads and videos"), adsEvery = num(s.ads.every_n_visits, 1, 100);
      const visOn = check(s.visitors.enabled, "Record profile visitors"), visDays = num(s.visitors.keep_days, 1, 365);
      const shopOn = check(s.shop.enabled, "Rank shop is open"), shopMax = num(s.shop.max_days, 1, 30), giftMax = num(s.shop.gift_max_days, 1, 365);
      const items = s.shop.items.map((i) => ({ ...i }));
      const itemsBox = h("div", {});
      const drawItems = () => itemsBox.replaceChildren(...items.map((it, idx) => {
        const rank = h("select", { class: "input small-select" }, lowRanks.map((r) => h("option", { value: r.id, selected: it.rank_id === r.id }, r.name)));
        const price = num(it.price, 1, 1000000), days = num(it.days, 1, 30);
        rank.addEventListener("change", () => (it.rank_id = rank.value)); price.addEventListener("input", () => (it.price = Number(price.value))); days.addEventListener("input", () => (it.days = Number(days.value)));
        return h("div", { class: "inline-form" }, rank, price, h("span", {}, "coins for"), days, h("span", {}, "day(s)"),
          h("button", { class: "btn small danger-text", type: "button", onClick: () => { items.splice(idx, 1); drawItems(); } }, "Remove"));
      }));
      drawItems();
      const coinCap = num(s.coins.admin_daily_gift_cap, 0, 1000000), startCoins = num(s.coins.start_coins, 0, 1000000), sendCap = num(s.coins.user_daily_send_cap, 0, 1000000);
      const missionsOn = check(s.missions.enabled, "Missions are switched on");
      const mMode = h("select", { class: "input" }, [["random", "Random: everybody gets their own missions"], ["all", "Everybody sees every mission"]].map(([v, l]) => h("option", { value: v, selected: s.missions.mode === v }, l)));
      const mHour = num(s.missions.slots_hourly, 0, 10), mDay = num(s.missions.slots_daily, 0, 20), mWeek = num(s.missions.slots_weekly, 0, 20);
      const rarityNames = { common: "Common", uncommon: "Uncommon", rare: "Rare", super_rare: "SUPER RARE", impossible: "IMPOSSIBLE" };
      const mWeights = Object.fromEntries(Object.keys(rarityNames).map((k) => [k, num(s.missions[`w_${k}`], 0, 1000)]));
      const pcOn = check(s.pc?.enabled, "Use my PC as an extra server when it is online");
      const pcInfo = h("p", { class: "muted" }, "Loading status…");
      get("/api/pc/status").then((x) => { pcInfo.textContent = !x.configured ? "Not set up: add PC_SECRET on Render (README, section PC server)." : x.online ? `PC is online (${x.url}).` : "PC is offline right now."; }).catch(() => { pcInfo.textContent = ""; });
      const winMax = num(s.windows?.max_open ?? 4, 1, 12);
      const supportOn = check(s.plans.support_enabled, "Show the “support the servers” note in the Plans tab");
      const supportText = h("textarea", { class: "input", rows: "3", maxlength: "500" }, s.plans.support_text);
      const lg = s.legal;
      const lOp = h("input", { class: "input", maxlength: "120", value: lg.operator_name }), lAddr = h("textarea", { class: "input", rows: "2", maxlength: "300" }, lg.operator_address);
      const lMail = h("input", { class: "input", maxlength: "120", value: lg.operator_email }), lPhone = h("input", { class: "input", maxlength: "60", value: lg.operator_phone });
      const lAge = h("input", { class: "input", maxlength: "20", value: lg.min_age, placeholder: "e.g. 16" }), lNote = h("textarea", { class: "input", rows: "3", maxlength: "600" }, lg.note);
      ownerBlock = h("div", {},
        h("section", { class: "card" }, h("h2", {}, "Owner: accounts and offers"), field("Rank of new accounts", defRank), offersOn.row, field("Rules text for Pro offers", offerRules)),
        h("section", { class: "card" }, h("h2", {}, "Owner: statistics admins can see"), h("p", { class: "muted" }, "You always see all of them."), ...statBoxes.map((b) => b.row)),
        h("section", { class: "card" }, h("h2", {}, "Owner: coins, missions and the shop"), missionsOn.row, field("How missions are given out", mMode),
          h("div", { class: "grid-2" }, field("Missions per person: every hour", mHour), field("Missions per person: every day", mDay), field("Missions per person: every week", mWeek)),
          h("h3", {}, "How often each rarity is drawn (a higher number = more often)"),
          h("div", { class: "grid-2" }, ...Object.entries(rarityNames).map(([k, l]) => field(l, mWeights[k]))),
          h("p", { class: "hint" }, "Example: 60 / 25 / 10 / 4 / 1 means about 60 of 100 draws are Common and 1 of 100 is IMPOSSIBLE. Set a number to 0 to never draw that rarity. Each mission gets its rarity and reset time when you create it (Missions tab, Staff tools)."),
          shopOn.row,
          h("div", { class: "grid-2" }, field("Longest rental (days)", shopMax), field("Longest gift by admins (days)", giftMax), field("Coins an admin may gift per day", coinCap), field("Coins for new accounts", startCoins), field("Coins a person may send to friends per day", sendCap)),
          h("h3", {}, "Shop items"), itemsBox, h("button", { class: "btn small", type: "button", onClick: () => { if (lowRanks.length) { items.push({ rank_id: lowRanks[0].id, price: 100, days: 1 }); drawItems(); } } }, "Add item")),
        h("section", { class: "card" }, h("h2", {}, "Owner: PC server and windows"), pcOn.row, pcInfo,
          h("p", { class: "hint" }, "Who may use the PC server is a permission (Ranks → \"Use the PC server\"); each person also switches it on for themselves in Settings. Without the PC (or when it is off) everybody uses the normal server."),
          field("Windows a person may have open at once (desktop mode)", winMax)),
        h("section", { class: "card" }, h("h2", {}, "Owner: Plans tab"), supportOn.row, field("Text of the note", supportText),
          h("p", { class: "hint" }, "Careful: no payment is built in on purpose. If you really take money from people, it changes the legal situation (imprint, taxes, minors). Talk to your parents first.")),
        h("section", { class: "card" }, h("h2", {}, "Owner: AI, ads and visitors"), aiOn.row, h("div", { class: "grid-2" }, field("AI questions per person and day", aiLimit), field("Most chat messages sent as context", aiCtx)),
          adsOn.row, field("Show an ad every … visits", adsEvery), visOn.row, field("Keep visitor entries (days)", visDays)),
        h("section", { class: "card" }, h("h2", {}, "Owner: legal details (shown in the terms and the imprint)"),
          h("p", { class: "hint" }, "Fill in only what is true. Empty fields are shown as “not filled in yet” in the legal pages. Whether you need an imprint is a legal question, please ask someone qualified."),
          field("Operator name", lOp), field("Address", lAddr), field("Email", lMail), field("Phone (optional)", lPhone), field("Minimum age you require", lAge), field("Extra note for the legal pages", lNote)));
      collectOwner = () => ({
        default_rank: defRank.value, offers: { enabled: offersOn.el.checked, rules: offerRules.value },
        stats: { enabled: statBoxes.filter((b) => b.el.checked).map((b) => b.k) },
        ai: { enabled: aiOn.el.checked, daily_limit: Number(aiLimit.value), max_context_messages: Number(aiCtx.value) },
        ads: { enabled: adsOn.el.checked, every_n_visits: Number(adsEvery.value) }, visitors: { enabled: visOn.el.checked, keep_days: Number(visDays.value) },
        shop: { enabled: shopOn.el.checked, max_days: Number(shopMax.value), gift_max_days: Number(giftMax.value), items },
        coins: { admin_daily_gift_cap: Number(coinCap.value), start_coins: Number(startCoins.value), user_daily_send_cap: Number(sendCap.value) },
        pc: { enabled: pcOn.el.checked }, windows: { max_open: Number(winMax.value) },
        plans: { support_enabled: supportOn.el.checked, support_text: supportText.value }, missions: { enabled: missionsOn.el.checked, mode: mMode.value, slots_hourly: Number(mHour.value), slots_daily: Number(mDay.value), slots_weekly: Number(mWeek.value),
          ...Object.fromEntries(Object.entries(mWeights).map(([k, el]) => [`w_${k}`, Number(el.value)])) },
        legal: { operator_name: lOp.value, operator_address: lAddr.value, operator_email: lMail.value, operator_phone: lPhone.value, min_age: lAge.value, note: lNote.value },
      });
    }

    async function save() {
      const loading = { title: title.value, music_volume: Number(volume.value), allow_user_image: allowImg.el.checked, allow_user_music: allowMusic.el.checked,
        allow_user_mute: allowMute.el.checked, max_image_mb: Number(maxLoadImg.value), max_music_mb: Number(maxLoadMusic.value) };
      if (assets.image !== undefined) loading.image_asset = assets.image;
      if (assets.music !== undefined) loading.music_asset = assets.music;
      try {
        await put("/api/admin/settings", {
          registration_mode: mode.value, start_page: startPage.value, announcement: announcement.value, messages_per_minute: Number(perMinute.value),
          uploads_enabled: uploadsOn.el.checked, max_image_mb: Number(maxImage.value), max_video_mb: Number(maxVideo.value),
          max_file_mb: Number(maxFile.value), user_quota_mb: Number(quota.value),
          blocked_extensions: blocked.value.split(",").map((x) => x.trim()).filter(Boolean),
          loading, background: { default: bgDefault.value, allow_custom: bgCustom.el.checked }, ...collectGames(), ...collectOwner(),
        });
        toast("Settings saved.");
        assets.image = assets.music = undefined;
        status.textContent = "";
      } catch (e) { toast(e.message, "error"); }
    }

    return h("form", { class: "settings-form", onSubmit: (e) => { e.preventDefault(); save(); } },
      h("section", { class: "card" }, h("h2", {}, "General"), field("Who can register", mode), field("Announcement banner", announcement), field("Messages per minute and person", perMinute),
        field("Start page after login", startPage, "Used when a person has not chosen their own. If they may not see that page, Chats opens.")),
      h("section", { class: "card" }, h("h2", {}, "Uploads"), uploadsOn.row,
        h("div", { class: "grid-2" }, field("Max picture size (MB)", maxImage), field("Max video size (MB)", maxVideo), field("Max other file size (MB)", maxFile), field("Storage per person (MB)", quota)),
        field("Blocked file endings", blocked, "Separated by commas. Programs and web pages are blocked by default.")),
      h("section", { class: "card" }, h("h2", {}, "Loading screen"), field("Title", title),
        h("div", { class: "field-label" }, "Default picture"), imgPreview, assetButtons("loading_image", "image", "image/*", imgPreview, (url) => h("img", { src: url, alt: "" })),
        h("div", { class: "field-label", style: "margin-top:12px" }, "Default music"), musicPreview, assetButtons("loading_music", "music", "audio/*", musicPreview, (url) => h("audio", { controls: true, src: url })),
        field("Music volume", volume), allowImg.row, allowMusic.row, allowMute.row,
        h("div", { class: "grid-2" }, field("Max picture size (MB)", maxLoadImg), field("Max music size (MB)", maxLoadMusic)), status),
      h("section", { class: "card" }, h("h2", {}, "Chat backgrounds"), field("Default background for everybody", bgDefault), bgCustom.row),
      gamesCard,
      ownerBlock || h("p", { class: "muted" }, "More settings (ranks of new accounts, shop, AI, statistics, legal details) belong to the Owner."),
      h("button", { class: "btn primary", type: "submit" }, "Save settings"));
  }

  return {
    ranks: ranksView, notes: notesView, releases: releasesView, ads: adsView, settings: settingsView,
  };
}
