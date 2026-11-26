// Admin area. Which tabs you see depends on your PERMISSIONS (not on a fixed role).
// The server checks every action again - hiding a tab here is only convenience.
import { i18nView } from "./admin_i18n.js";
import { del, get, patch, post } from "../api.js";
import { act, avatar, confirmDialog, emptyState, field, formatBytes, h, longDate, modal, openMenu, rankTag, toast } from "../ui.js";
import { ownerTabs } from "./admin_owner.js";

export const usesList = false;

export async function render({ main, state }) {
  const can = (p) => state.can(p);
  const TABS = [
    can("admin.stats") && ["overview", "Overview"],
    can("admin.users") && ["users", "Users"],
    can("admin.whitelist") && ["whitelist", "Whitelist"],
    can("admin.groups") && ["groups", "Groups"],
    can("chat.inspect") && ["private", "Private chats"],
    can("mod.reports") && ["reports", "Reports"],
    can("admin.offers") && ["offers", "Pro offers"],
    can("admin.request") && ["requests", can("owner.requests") ? "Permission requests" : "Ask the Owner"],
    can("admin.notes") && ["notes", "Notes"],
    can("admin.releases") && ["releases", "What's New"],
    can("admin.ads") && ["ads", "Ads"],
    can("admin.access") && ["ranks", "Ranks"],
    can("admin.settings") && ["settings", "Settings"],
    can("translations.review") && ["i18n", "Translations"],
    can("admin.audit") && ["audit", "Audit log"],
  ].filter(Boolean);
  if (!TABS.length) { main.append(emptyState("Nothing to manage", "Your rank has no admin tools.")); return; }

  let tab = TABS[0][0];
  const content = h("div", { class: "admin-content" });
  const tabsEl = h("div", { class: "tabs scroll", role: "tablist" });
  const when = longDate;
  const reload = () => load();

  function drawTabs() {
    tabsEl.replaceChildren(...TABS.map(([id, label]) => h("button", {
      class: `tab${tab === id ? " active" : ""}`, type: "button", role: "tab", "aria-selected": String(tab === id),
      onClick: () => { tab = id; drawTabs(); load(); },
    }, label)));
  }

  async function load() {
    content.replaceChildren(h("p", { class: "muted" }, "Loading…"));
    try {
      const views = { overview: overviewView, users: usersView, whitelist: whitelistView, groups: groupsView, private: privateView,
        reports: reportsView, i18n: i18nView, offers: offersView, requests: requestsView, audit: auditView, ...ownerTabs({ state, reload, when }) };
      content.replaceChildren(await views[tab]());
    } catch (e) { content.replaceChildren(emptyState("Couldn't load this tab", e.message)); }
  }

  // ---------- overview (the Owner decides which numbers admins see) ----------
  async function overviewView() {
    const s = await get("/api/admin/stats");
    const cards = Object.entries(s.labels).map(([key, label]) => {
      const v = s.values[key];
      if (v && typeof v === "object") {
        return h("div", { class: "stat wide" }, h("span", {}, label),
          h("ul", { class: "mini-list" }, Object.entries(v).map(([k, n]) => h("li", {}, `${k}: ${n}`))));
      }
      return h("div", { class: "stat" }, h("strong", {}, String(v)), h("span", {}, label));
    });
    return h("div", {},
      !s.storage_configured ? h("p", { class: "notice" }, "File storage is not set up yet, so uploads and the loading screen are off.") : null,
      cards.length ? h("div", { class: "stats" }, ...cards) : emptyState("No statistics are switched on", "The Owner chooses which numbers admins can see."),
      s.all_keys ? h("p", { class: "muted" }, "As Owner you see everything. Choose what admins see under Settings → Statistics.") : null);
  }

  // ---------- users ----------
  function showPassword(title, password) {
    const body = h("div", { class: "dialog-body" },
      h("p", {}, "Give this password to the person. It is shown only once and they have to change it at the first login."),
      h("code", { class: "secret" }, password),
      h("div", { class: "dialog-actions" },
        h("button", { class: "btn", type: "button", onClick: () => navigator.clipboard?.writeText(password).then(() => toast("Copied.")) }, "Copy"),
        h("button", { class: "btn primary", type: "button", onClick: () => box.close() }, "Done")));
    const box = modal(title, body);
  }

  async function rankOptions(selected) {
    const { ranks } = await get("/api/admin/ranks");
    const myLevel = state.me.is_owner ? 1000 : state.me.rank_level;
    return ranks.filter((r) => !r.is_owner && r.level < myLevel)
      .map((r) => h("option", { value: r.id, selected: r.id === selected }, `${r.name} (level ${r.level})`));
  }

  async function createUserDialog() {
    const username = h("input", { class: "input", maxlength: "20", required: true, autocomplete: "off" });
    const email = h("input", { class: "input", type: "email", required: true, autocomplete: "off" });
    const display = h("input", { class: "input", maxlength: "40", placeholder: "Same as username" });
    const password = h("input", { class: "input", type: "text", autocomplete: "off", placeholder: "Leave empty to generate one" });
    const rank = h("select", { class: "input" }, ...(await rankOptions("")));
    const must = h("input", { type: "checkbox", checked: true });
    const msg = h("p", { class: "form-msg", role: "alert" });
    const form = h("form", { class: "dialog-body" }, field("Username", username), field("Email", email), field("Display name", display),
      field("Password", password), field("Rank", rank),
      h("label", { class: "choice" }, must, h("span", {}, h("strong", {}, "Must choose a new password at the first login"))),
      h("p", { class: "hint" }, "The new person has to accept the terms of use at their first login."),
      msg, h("div", { class: "dialog-actions" }, h("button", { class: "btn primary", type: "submit" }, "Create user")));
    const box = modal("Create user", form);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const res = await post("/api/admin/users", { username: username.value.trim(), email: email.value.trim(), display_name: display.value.trim(),
          password: password.value, rank: rank.value || undefined, must_change_password: must.checked });
        box.close(); toast(`${res.user.username} was created.`); load();
        if (res.generated_password) showPassword(`Password for ${res.user.username}`, res.generated_password);
      } catch (err) { msg.textContent = err.message; msg.className = "form-msg error"; }
    });
  }

  async function editUserDialog(u) {
    const display = h("input", { class: "input", maxlength: "40", value: u.display_name });
    const email = h("input", { class: "input", type: "email", value: u.email });
    const canRank = can("admin.manage_ranks") && !u.is_owner;
    const rank = canRank ? h("select", { class: "input" }, ...(await rankOptions(u.base_rank_id))) : null;
    const msg = h("p", { class: "form-msg", role: "alert" });
    const form = h("form", { class: "dialog-body" }, field("Display name", display), field("Email", email),
      rank ? field("Permanent rank", rank) : null,
      u.lease_until > Date.now() / 1000 ? h("p", { class: "muted" }, `Has a temporary rank until ${when(u.lease_until)}.`) : null,
      u.is_owner ? h("p", { class: "muted" }, "This is the Owner account. It always has every permission and can't be changed.") : null,
      msg, h("div", { class: "dialog-actions" }, h("button", { class: "btn primary", type: "submit" }, "Save")));
    const box = modal(`Edit ${u.username}`, form);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const changes = { display_name: display.value, email: email.value };
      if (rank && rank.value !== u.base_rank_id) changes.rank = rank.value;
      try { await patch(`/api/admin/users/${encodeURIComponent(u.username)}`, changes); box.close(); toast("Saved."); load(); }
      catch (err) { msg.textContent = err.message; msg.className = "form-msg error"; }
    });
  }

  async function extraPermsDialog(u) {
    const { registry } = await get("/api/admin/ranks");
    const chosen = new Set(u.extra_perms);
    const boxes = registry.map((p) => {
      const cb = h("input", { type: "checkbox", checked: chosen.has(p.key) });
      cb.addEventListener("change", () => (cb.checked ? chosen.add(p.key) : chosen.delete(p.key)));
      return h("label", { class: "choice" }, cb, h("span", {}, h("strong", {}, p.label), h("small", {}, p.key)));
    });
    const form = h("div", { class: "dialog-body perm-list" }, h("p", { class: "muted" }, "Extra permissions on top of the rank. They stay even if the rank changes."), ...boxes,
      h("div", { class: "dialog-actions" }, h("button", { class: "btn primary", type: "button", onClick: async () => {
        if (await act(post(`/api/admin/users/${encodeURIComponent(u.username)}/extra-perms`, { perms: [...chosen] }))) { box.close(); load(); }
      } }, "Save")));
    const box = modal(`Extra permissions for ${u.username}`, form);
  }

  function deleteUserDialog(u) {
    const confirmInput = h("input", { class: "input", autocomplete: "off", placeholder: u.username });
    const keep = h("input", { type: "checkbox" });
    const msg = h("p", { class: "form-msg", role: "alert" });
    const form = h("form", { class: "dialog-body" },
      h("p", {}, `This deletes ${u.username} completely: the account, all private chats, files and uploads. This can't be undone.`),
      h("label", { class: "choice" }, keep, h("span", {}, h("strong", {}, "Also delete their group messages"), h("small", {}, "Otherwise they stay and show “Deleted user”."))),
      field(`Type “${u.username}” to confirm`, confirmInput),
      msg, h("div", { class: "dialog-actions" }, h("button", { class: "btn danger", type: "submit" }, "Delete user")));
    const box = modal("Delete user", form);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await post(`/api/admin/users/${encodeURIComponent(u.username)}/delete`, { confirm: confirmInput.value, delete_group_messages: keep.checked });
        box.close(); toast(`${u.username} was deleted.`); load();
      } catch (err) { msg.textContent = err.message; msg.className = "form-msg error"; }
    });
  }

  async function usersView() {
    const users = await get("/api/admin/users");
    const pending = users.filter((u) => u.status === "pending").length;
    const path = (u, tail) => `/api/admin/users/${encodeURIComponent(u.username)}${tail}`;
    return h("div", {},
      h("div", { class: "toolbar-row" }, h("button", { class: "btn primary", type: "button", onClick: createUserDialog }, "Create user")),
      pending ? h("p", { class: "notice" }, `${pending} account${pending === 1 ? " is" : "s are"} waiting for approval.`) : null,
      h("ul", { class: "rows" }, users.map((u) => {
        const items = [{ label: "Edit…", onClick: () => editUserDialog(u) }];
        if (u.status !== "active") items.push({ label: u.status === "banned" ? "Restore access" : "Approve and verify", onClick: () => act(post(path(u, "/approve")), reload) });
        if (can("owner.requests") && !u.is_owner) items.push({ label: "Extra permissions…", onClick: () => extraPermsDialog(u) });
        if (can("admin.manage_ranks") && u.lease_until > Date.now() / 1000 && !u.is_owner) {
          items.push({ label: "End temporary rank", onClick: () => act(patch(`/api/admin/users/${encodeURIComponent(u.username)}`, { clear_lease: true }), reload) });
        }
        if (!u.is_owner && u.username !== state.me.username) {
          items.push({ label: "Set a new password…", onClick: async () => {
            if (!(await confirmDialog("New password", `Create a new password for ${u.username}? They are logged out everywhere.`, "Create"))) return;
            const res = await act(post(path(u, "/reset-password")));
            if (res?.generated_password) showPassword(`New password for ${u.username}`, res.generated_password);
          } });
          items.push({ label: "Log out everywhere", onClick: () => act(post(path(u, "/logout-all"))) });
          if (u.status !== "banned") items.push({ label: "Suspend", danger: true, onClick: () => act(post(path(u, "/suspend")), reload) });
          if (can("admin.delete_users")) items.push({ label: "Delete completely…", danger: true, onClick: () => deleteUserDialog(u) });
        }
        const manage = h("button", { class: "btn small", type: "button", onClick: () => openMenu(manage, items) }, "Manage");
        return h("li", { class: "row" }, avatar(u, "sm"),
          h("div", { class: "item-text" },
            h("strong", {}, u.display_name, " ", rankTag(u.rank), u.extra_perms.length ? h("span", { class: "tag" }, `+${u.extra_perms.length} perms`) : null),
            h("span", { class: "item-sub" }, `@${u.username} · ${u.email}${u.consent ? "" : " · terms not accepted yet"}`)),
          h("span", { class: `tag status-${u.status}` }, u.status === "banned" ? "suspended" : u.status),
          u.muted_until > Date.now() / 1000 ? h("span", { class: "tag" }, "muted") : null,
          u.must_change_password ? h("span", { class: "tag" }, "must change password") : null,
          manage);
      })));
  }

  // ---------- whitelist ----------
  async function whitelistView() {
    const names = await get("/api/admin/whitelist");
    const input = h("input", { class: "input", placeholder: "Username to allow", maxlength: "20", "aria-label": "Username to allow" });
    return h("div", {},
      h("form", { class: "invite-form", onSubmit: (e) => { e.preventDefault(); if (input.value.trim()) act(post("/api/admin/whitelist", { username: input.value.trim() }), reload); } },
        input, h("button", { class: "btn primary", type: "submit" }, "Add")),
      names.length
        ? h("ul", { class: "rows" }, names.map((n) => h("li", { class: "row" }, h("strong", { class: "item-text" }, n),
          h("button", { class: "btn small danger-text", type: "button", onClick: () => act(del(`/api/admin/whitelist/${encodeURIComponent(n)}`), reload) }, "Remove"))))
        : emptyState("The whitelist is empty", "In whitelist mode only the Owner can register until you add names."));
  }

  // ---------- read-only viewer ----------
  function viewer(title, fetchPage) {
    const list = h("div", { class: "viewer" });
    const more = h("button", { class: "btn small", type: "button", hidden: true }, "Load older messages");
    let oldest = null;
    async function loadPage() {
      try {
        const page = await fetchPage(oldest);
        const rows = page.messages.map((m) => h("div", { class: `viewer-row${m.system ? " system" : ""}` },
          h("span", { class: "viewer-meta" }, `${when(m.ts)} · ${m.system ? "system" : m.sender_name}`),
          h("span", {}, m.deleted ? "[deleted]" : m.text || ""),
          ...m.attachments.map((a) => h("small", { class: "muted" }, `📎 ${a.name} (${formatBytes(a.size)})`))));
        if (page.messages.length) oldest = page.messages[0].id;
        list.prepend(...rows);
        more.hidden = !page.has_more;
        if (!page.messages.length && !list.children.length) list.append(h("p", { class: "muted" }, "No messages."));
      } catch (e) { toast(e.message, "error"); }
    }
    more.addEventListener("click", loadPage);
    modal(title, h("div", { class: "dialog-body" }, more, list));
    return loadPage();
  }

  // ---------- groups ----------
  async function groupsView() {
    const groups = await get("/api/admin/groups");
    if (!groups.length) return emptyState("No groups yet");
    return h("ul", { class: "rows" }, groups.map((gr) => h("li", { class: "row" },
      h("div", { class: "item-text" }, h("strong", {}, gr.name),
        h("span", { class: "item-sub" }, `${gr.member_count} members · created by @${gr.created_by} · ${gr.join_mode === "open" ? "open" : "invite-only"}`)),
      h("button", { class: "btn small", type: "button", onClick: () => viewer(`Group: ${gr.name}`, (before) => get(`/api/admin/groups/${gr.id}/messages${before ? `?before=${before}` : ""}`)) }, "Read"),
      h("button", { class: "btn small danger-text", type: "button", onClick: async () => {
        if (await confirmDialog("Clear group chat", `Delete all messages and files in “${gr.name}”?`, "Clear chat", true)) act(post(`/api/admin/groups/${gr.id}/clear`), reload);
      } }, "Clear chat"),
      h("button", { class: "btn small danger-text", type: "button", onClick: async () => {
        if (await confirmDialog("Delete group", `Delete “${gr.name}” and everything in it? This can't be undone.`, "Delete group", true)) act(del(`/api/admin/groups/${gr.id}`), reload);
      } }, "Delete"))));
  }

  // ---------- private chats: overview shows only WHO writes with WHOM; reading needs a reason and is logged ----------
  async function privateView() {
    const [users, overview] = await Promise.all([can("admin.users") ? get("/api/admin/users") : Promise.resolve([]), get("/api/admin/chat-overview")]);
    const reason = h("textarea", { class: "input", rows: "3", maxlength: "300", placeholder: "Reason for reading (at least 10 characters)" });
    const a = h("select", { class: "input", "aria-label": "First person" }), b = h("select", { class: "input", "aria-label": "Second person" });
    const fill = (list) => { a.replaceChildren(...list.map((u) => h("option", { value: u.username }, u.display_name))); b.replaceChildren(...list.map((u) => h("option", { value: u.username }, u.display_name))); if (list.length > 1) b.selectedIndex = 1; };
    fill(users);
    const read = (x, y) => {
      if (reason.value.trim().length < 10) return toast("Please write a real reason first (at least 10 characters).", "error");
      viewer(`${x} + ${y}`, (before) => post(`/api/admin/private-chats/access${before ? `?before=${before}` : ""}`, { user_a: x, user_b: y, reason: reason.value }));
    };
    return h("div", {},
      h("div", { class: "notice" },
        h("strong", {}, "Privacy rules"),
        h("p", {}, "Private chats are not readable by default. The list below only shows who talks to whom and how many messages there are, never the text."),
        h("p", {}, "To read one you must write a reason. Both people see a notice in the chat and the access is saved in the audit log. You can only open chats of people whose rank is below yours.")),
      h("label", { class: "field" }, h("span", { class: "field-label" }, "Reason (used for the next reading)"), reason),
      h("h2", {}, "Chat overview"),
      overview.length ? h("ul", { class: "rows" }, overview.map((c) => h("li", { class: "row" },
        h("div", { class: "item-text" }, h("strong", {}, `${c.name_a} + ${c.name_b}`), h("span", { class: "item-sub" }, `${c.messages} messages · last ${when(c.last)}`)),
        h("button", { class: "btn small", type: "button", onClick: () => read(c.user_a, c.user_b) }, "Read (logged)"),
        can("admin.groups") ? h("button", { class: "btn small danger-text", type: "button", onClick: async () => {
          if (await confirmDialog("Clear private chat", "Delete all messages and files of this private chat for both people?", "Clear chat", true)) act(post("/api/admin/private-chats/clear", { user_a: c.user_a, user_b: c.user_b }), reload);
        } }, "Clear") : null)))
        : emptyState("No private chats yet"),
      users.length ? h("details", { class: "card" }, h("summary", {}, "Pick two people yourself"),
        h("div", { class: "grid-2" }, field("First person", a), field("Second person", b)),
        h("button", { class: "btn", type: "button", onClick: () => read(a.value, b.value) }, "Read (logged)")) : null);
  }

  // ---------- reports ----------
  async function reportsView() {
    let status = "open";
    const box = h("div");
    const toggle = h("div", { class: "tabs small" });
    async function draw() {
      toggle.replaceChildren(...[["open", "Open"], ["closed", "Closed"]].map(([id, label]) =>
        h("button", { class: `tab${status === id ? " active" : ""}`, type: "button", onClick: () => { status = id; draw(); } }, label)));
      const reports = await get(`/api/mod/reports?status=${status}`);
      box.replaceChildren(...(reports.length ? reports.map(reportCard) : [emptyState(status === "open" ? "No open reports" : "Nothing here yet")]));
    }
    function reportCard(r) {
      const muteBtn = can("mod.mute") ? h("button", { class: "btn small", type: "button", onClick: () => openMenu(muteBtn, [10, 60, 1440].map((m) => ({
        label: `Mute ${r.sender_name} for ${m === 1440 ? "1 day" : m === 60 ? "1 hour" : "10 minutes"}`,
        onClick: () => act(post(`/api/mod/users/${encodeURIComponent(r.sender)}/mute`, { minutes: m })),
      }))) }, "Mute sender…") : null;
      return h("div", { class: "report" },
        h("div", { class: "report-head" }, h("strong", {}, `Reported by ${r.reporter}`), h("span", { class: "muted" }, ` · ${when(r.created)} · ${r.chat_type === "group" ? "group" : "private chat"}`)),
        r.reason ? h("p", { class: "report-reason" }, `“${r.reason}”`) : null,
        h("div", { class: "viewer" }, r.context.map((m) => h("div", { class: `viewer-row${m.reported ? " reported" : ""}` },
          h("span", { class: "viewer-meta" }, `${when(m.ts)} · ${m.sender_name}`), h("span", {}, m.text || "[no text]")))),
        r.status === "open" ? h("div", { class: "button-row" },
          h("button", { class: "btn small", type: "button", onClick: () => act(post(`/api/mod/reports/${r.id}/resolve`, { action: "dismiss" }), draw) }, "Dismiss"),
          h("button", { class: "btn small danger-text", type: "button", onClick: () => act(post(`/api/mod/reports/${r.id}/resolve`, { action: "delete_message" }), draw) }, "Delete message"),
          muteBtn) : h("p", { class: "muted" }, `Closed by ${r.handled_by || "someone"}.`));
    }
    await draw();
    return h("div", {}, toggle, box);
  }

  // ---------- Pro offers ----------
  async function offersView() {
    const [rows, { ranks }] = await Promise.all([get("/api/admin/offers?status=open"), get("/api/admin/ranks")]);
    const myLevel = state.me.is_owner ? 1000 : state.me.rank_level;
    const options = ranks.filter((r) => !r.is_owner && r.level < myLevel);
    const card = (o) => {
      const answer = h("input", { class: "input", maxlength: "300", placeholder: "Answer (optional)" });
      const rank = h("select", { class: "input small-select", "aria-label": "Reward rank" }, h("option", { value: "" }, "No reward"),
        ...options.map((r) => h("option", { value: r.id }, r.name)));
      const days = h("input", { class: "input small-select", type: "number", min: "1", max: "365", value: "1", "aria-label": "Days" });
      const decide = (accept) => act(post(`/api/admin/offers/${o.id}/decide`, { accept, answer: answer.value,
        ...(accept && rank.value ? { rank_id: rank.value, days: Number(days.value) } : {}) }), reload);
      return h("div", { class: "report" },
        h("strong", {}, `${o.name} (@${o.username})`), h("span", { class: "muted" }, ` · ${when(o.created)}`), h("p", { class: "pre" }, o.text),
        answer, h("div", { class: "inline-form" }, rank, h("span", {}, "for"), days, h("span", {}, "day(s)")),
        h("div", { class: "button-row" }, h("button", { class: "btn small primary", type: "button", onClick: () => decide(true) }, "Accept"),
          h("button", { class: "btn small danger-text", type: "button", onClick: () => decide(false) }, "Decline")));
    };
    return h("div", {}, h("p", { class: "muted" }, "Nobody pays real money. People offer something (help, an idea, a favour) and you may reward them with a temporary rank. The Owner sets the rules in Settings."),
      rows.length ? rows.map(card) : emptyState("No open offers"));
  }

  // ---------- permission requests (admin -> Owner) ----------
  async function requestsView() {
    const [rows, reg] = await Promise.all([get("/api/admin/requests"), get("/api/admin/ranks")]);
    const isOwner = can("owner.requests");
    const labelOf = Object.fromEntries(reg.registry.map((p) => [p.key, p.label]));
    const mine = new Set(state.me.perms);
    const perm = h("select", { class: "input" }, reg.registry.filter((p) => !mine.has(p.key)).map((p) => h("option", { value: p.key }, `${p.label} (${p.key})`)));
    const text = h("textarea", { class: "input", rows: "3", maxlength: "400", placeholder: "Why do you need it?" });
    const form = !isOwner ? h("form", { class: "card", onSubmit: (e) => { e.preventDefault(); act(post("/api/admin/requests", { perm: perm.value, text: text.value }), reload); } },
      h("h2", {}, "Ask the Owner for a permission"), field("Permission", perm), field("Reason", text), h("button", { class: "btn primary", type: "submit" }, "Send request")) : null;
    const item = (r) => {
      const answer = h("input", { class: "input", maxlength: "300", placeholder: "Answer (optional)" });
      return h("div", { class: "report" },
        h("strong", {}, `${r.from_user} → ${labelOf[r.perm] || r.perm}`), h("span", { class: "muted" }, ` · ${when(r.created)} · ${r.status}`),
        r.text ? h("p", { class: "pre" }, r.text) : null, r.answer ? h("p", { class: "muted" }, `Answer: ${r.answer}`) : null,
        isOwner && r.status === "open" ? h("div", {}, answer, h("div", { class: "button-row" },
          h("button", { class: "btn small primary", type: "button", onClick: () => act(post(`/api/admin/requests/${r.id}/decide`, { approve: true, answer: answer.value }), reload) }, "Approve"),
          h("button", { class: "btn small danger-text", type: "button", onClick: () => act(post(`/api/admin/requests/${r.id}/decide`, { approve: false, answer: answer.value }), reload) }, "Deny"))) : null);
    };
    return h("div", {}, form, rows.length ? rows.map(item) : emptyState(isOwner ? "No requests" : "You haven't asked for anything yet"));
  }

  // ---------- audit log ----------
  async function auditView() {
    const list = h("ul", { class: "rows audit" });
    const more = h("button", { class: "btn small", type: "button", hidden: true }, "Load more");
    let last = null;
    async function loadMore() {
      const rows = await get(`/api/admin/audit${last ? `?before=${last}` : ""}`);
      rows.forEach((r) => list.append(h("li", { class: "row" },
        h("span", { class: "muted audit-time" }, when(r.ts)),
        h("div", { class: "item-text" }, h("strong", {}, `${r.actor} · ${r.action.replace(/_/g, " ")}`), h("span", { class: "item-sub" }, [r.target, r.details].filter(Boolean).join(" — "))))));
      if (rows.length) last = rows[rows.length - 1].id;
      more.hidden = rows.length < 100;
    }
    more.addEventListener("click", loadMore);
    await loadMore();
    return h("div", {}, list, more);
  }

  drawTabs();
  main.append(h("div", { class: "page wide" }, h("h1", {}, can("admin.users") ? "Administration" : "Moderation"), tabsEl, content));
  load();
}
