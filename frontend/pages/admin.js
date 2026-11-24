// Admin area (admins) and moderation area (moderators): users, roles, groups, reports, settings, log.
import { del, get, patch, post, put } from "../api.js";
import { avatar, confirmDialog, emptyState, formatBytes, formatTime, h, modal, openMenu, toast } from "../ui.js";
import { uploadFile } from "../upload.js";

export const usesList = false;

const ROLE_LABEL = { user: "User", moderator: "Moderator", admin: "Admin" };
const when = (ts) => new Date(ts * 1000).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export async function render({ main, state }) {
  const isAdmin = state.me.role === "admin";
  const TABS = isAdmin
    ? [["overview", "Overview"], ["users", "Users"], ["whitelist", "Whitelist"], ["groups", "Groups"], ["private", "Private chats"],
       ["reports", "Reports"], ["settings", "Settings"], ["audit", "Audit log"]]
    : [["reports", "Reports"]];
  let tab = TABS[0][0];
  const content = h("div", { class: "admin-content" });
  const tabsEl = h("div", { class: "tabs scroll", role: "tablist" });

  function drawTabs() {
    tabsEl.replaceChildren(...TABS.map(([id, label]) => h("button", {
      class: `tab${tab === id ? " active" : ""}`, type: "button", role: "tab", "aria-selected": String(tab === id),
      onClick: () => { tab = id; drawTabs(); load(); },
    }, label)));
  }

  async function act(promise, after = load) {
    try { const res = await promise; if (res?.message) toast(res.message); await after(res); return res; }
    catch (e) { toast(e.message, "error"); }
  }

  async function load() {
    content.replaceChildren(h("p", { class: "muted" }, "Loading…"));
    try {
      const views = { overview: overviewView, users: usersView, whitelist: whitelistView, groups: groupsView,
        private: privateView, reports: reportsView, settings: settingsView, audit: auditView };
      content.replaceChildren(await views[tab]());
    } catch (e) { content.replaceChildren(emptyState("Couldn't load this tab", e.message)); }
  }

  // ---------- overview ----------
  async function overviewView() {
    const s = await get("/api/admin/stats");
    const card = (label, value, hint = "") => h("div", { class: "stat" }, h("strong", {}, value), h("span", {}, label), hint ? h("small", {}, hint) : null);
    return h("div", {},
      s.users.pending ? h("p", { class: "notice" }, `${s.users.pending} account${s.users.pending === 1 ? " is" : "s are"} waiting for approval (see Users).`) : null,
      s.open_reports ? h("p", { class: "notice" }, `${s.open_reports} open report${s.open_reports === 1 ? "" : "s"} (see Reports).`) : null,
      !s.storage_configured ? h("p", { class: "notice" }, "File storage is not configured, so uploads and the loading screen are switched off.") : null,
      h("div", { class: "stats" },
        card("Users", s.users.total, `${s.users.active} active · ${s.users.suspended} suspended`),
        card("Moderators / admins", `${s.roles.moderator} / ${s.roles.admin}`),
        card("Groups", s.groups),
        card("Messages", s.messages, `${s.messages_24h} in the last 24 h`),
        card("Files", s.files, `${s.storage_mb} MB stored`)));
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

  function createUserDialog() {
    const f = (label, el) => h("label", { class: "field" }, h("span", { class: "field-label" }, label), el);
    const username = h("input", { class: "input", maxlength: "20", required: true, autocomplete: "off" });
    const email = h("input", { class: "input", type: "email", required: true, autocomplete: "off" });
    const display = h("input", { class: "input", maxlength: "40", placeholder: "Same as username" });
    const password = h("input", { class: "input", type: "text", autocomplete: "off", placeholder: "Leave empty to generate one" });
    const role = h("select", { class: "input" }, Object.entries(ROLE_LABEL).map(([v, l]) => h("option", { value: v }, l)));
    const must = h("input", { type: "checkbox", checked: true });
    const msg = h("p", { class: "form-msg", role: "alert" });
    const form = h("form", { class: "dialog-body" }, f("Username", username), f("Email", email), f("Display name", display),
      f("Password", password), f("Role", role),
      h("label", { class: "choice" }, must, h("span", {}, h("strong", {}, "Must choose a new password at the first login"))),
      msg, h("div", { class: "dialog-actions" }, h("button", { class: "btn primary", type: "submit" }, "Create user")));
    const box = modal("Create user", form);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const res = await post("/api/admin/users", { username: username.value.trim(), email: email.value.trim(), display_name: display.value.trim(),
          password: password.value, role: role.value, must_change_password: must.checked });
        box.close(); toast(`${res.user.username} was created.`); load();
        if (res.generated_password) showPassword(`Password for ${res.user.username}`, res.generated_password);
      } catch (err) { msg.textContent = err.message; msg.className = "form-msg error"; }
    });
  }

  function editUserDialog(u) {
    const f = (label, el) => h("label", { class: "field" }, h("span", { class: "field-label" }, label), el);
    const display = h("input", { class: "input", maxlength: "40", value: u.display_name });
    const email = h("input", { class: "input", type: "email", value: u.email });
    const role = h("select", { class: "input", disabled: u.is_super_admin }, Object.entries(ROLE_LABEL).map(([v, l]) => h("option", { value: v, selected: u.role === v }, l)));
    const msg = h("p", { class: "form-msg", role: "alert" });
    const form = h("form", { class: "dialog-body" }, f("Display name", display), f("Email", email), f("Role", role),
      u.is_super_admin ? h("p", { class: "muted" }, "This is the main admin account. Its role can't be changed.") : null,
      msg, h("div", { class: "dialog-actions" }, h("button", { class: "btn primary", type: "submit" }, "Save")));
    const box = modal(`Edit ${u.username}`, form);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const changes = { display_name: display.value, email: email.value };
      if (!u.is_super_admin) changes.role = role.value;
      try { await patch(`/api/admin/users/${encodeURIComponent(u.username)}`, changes); box.close(); toast("Saved."); load(); }
      catch (err) { msg.textContent = err.message; msg.className = "form-msg error"; }
    });
  }

  function deleteUserDialog(u) {
    const confirmInput = h("input", { class: "input", autocomplete: "off", placeholder: u.username });
    const keep = h("input", { type: "checkbox" });
    const msg = h("p", { class: "form-msg", role: "alert" });
    const form = h("form", { class: "dialog-body" },
      h("p", {}, `This deletes ${u.username} completely: the account, all private chats, files and uploads. This can't be undone.`),
      h("label", { class: "choice" }, keep, h("span", {}, h("strong", {}, "Also delete their group messages"), h("small", {}, "Otherwise they stay and show “Deleted user”."))),
      h("label", { class: "field" }, h("span", { class: "field-label" }, `Type “${u.username}” to confirm`), confirmInput),
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
        if (u.status !== "active") items.push({ label: u.status === "banned" ? "Restore access" : "Approve and verify", onClick: () => act(post(path(u, "/approve"))) });
        if (!u.is_super_admin) {
          items.push({ label: "Set a new password…", onClick: async () => {
            if (!(await confirmDialog("New password", `Create a new password for ${u.username}? They are logged out everywhere.`, "Create"))) return;
            const res = await act(post(path(u, "/reset-password")));
            if (res?.generated_password) showPassword(`New password for ${u.username}`, res.generated_password);
          } });
          items.push({ label: "Log out everywhere", onClick: () => act(post(path(u, "/logout-all"))) });
          if (u.status !== "banned") items.push({ label: "Suspend", danger: true, onClick: () => act(post(path(u, "/suspend"))) });
          items.push({ label: "Delete completely…", danger: true, onClick: () => deleteUserDialog(u) });
        }
        const manage = h("button", { class: "btn small", type: "button", onClick: () => openMenu(manage, items) }, "Manage");
        return h("li", { class: "row" }, avatar(u, "sm"),
          h("div", { class: "item-text" },
            h("strong", {}, u.display_name, " ", h("span", { class: `tag role-${u.role}` }, ROLE_LABEL[u.role]),
              u.is_super_admin ? h("span", { class: "tag" }, "main admin") : null),
            h("span", { class: "item-sub" }, `@${u.username} · ${u.email}`)),
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
      h("form", { class: "invite-form", onSubmit: (e) => { e.preventDefault(); if (input.value.trim()) act(post("/api/admin/whitelist", { username: input.value.trim() })); } },
        input, h("button", { class: "btn primary", type: "submit" }, "Add")),
      names.length
        ? h("ul", { class: "rows" }, names.map((n) => h("li", { class: "row" }, h("strong", { class: "item-text" }, n),
          h("button", { class: "btn small danger-text", type: "button", onClick: () => act(del(`/api/admin/whitelist/${encodeURIComponent(n)}`)) }, "Remove"))))
        : emptyState("The whitelist is empty", "In whitelist mode only the main admin can register until you add names."));
  }

  // ---------- reading chats (read-only viewer) ----------
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
        if (await confirmDialog("Clear group chat", `Delete all messages and files in “${gr.name}”?`, "Clear chat", true)) act(post(`/api/admin/groups/${gr.id}/clear`));
      } }, "Clear chat"),
      h("button", { class: "btn small danger-text", type: "button", onClick: async () => {
        if (await confirmDialog("Delete group", `Delete “${gr.name}” and everything in it? This can't be undone.`, "Delete group", true)) act(del(`/api/admin/groups/${gr.id}`));
      } }, "Delete"))));
  }

  // ---------- private chats (three-stage privacy rules) ----------
  async function privateView() {
    const users = await get("/api/admin/users");
    const options = () => users.map((u) => h("option", { value: u.username }, u.display_name));
    const a = h("select", { class: "input", "aria-label": "First person" }, options());
    const b = h("select", { class: "input", "aria-label": "Second person" }, options());
    if (users.length > 1) b.selectedIndex = 1;
    const reason = h("textarea", { class: "input", rows: "3", maxlength: "300", placeholder: "Reason for reading (at least 10 characters)" });
    return h("div", {},
      h("div", { class: "notice" },
        h("strong", {}, "Privacy rules"),
        h("p", {}, "Private chats are not readable by default. You can clear a chat without reading it. Reading it needs a written reason: both people see a notice in the chat and the access is saved in the audit log."),
        h("p", {}, "Reported messages (with a few messages around them) are in the Reports tab.")),
      h("div", { class: "grid-2" }, h("label", { class: "field" }, h("span", { class: "field-label" }, "First person"), a),
        h("label", { class: "field" }, h("span", { class: "field-label" }, "Second person"), b)),
      h("label", { class: "field" }, h("span", { class: "field-label" }, "Reason"), reason),
      h("div", { class: "button-row" },
        h("button", { class: "btn", type: "button", onClick: () => {
          if (reason.value.trim().length < 10) return toast("Please write a real reason first (at least 10 characters).", "error");
          viewer(`${a.value} + ${b.value}`, (before) => post(`/api/admin/private-chats/access${before ? `?before=${before}` : ""}`,
            { user_a: a.value, user_b: b.value, reason: reason.value }));
        } }, "Emergency access: read"),
        h("button", { class: "btn danger", type: "button", onClick: async () => {
          if (await confirmDialog("Clear private chat", "Delete all messages and files of this private chat for both people?", "Clear chat", true)) {
            act(post("/api/admin/private-chats/clear", { user_a: a.value, user_b: b.value }), () => {});
          }
        } }, "Clear chat (without reading)")));
  }

  // ---------- reports (moderators + admins) ----------
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
      const muteBtn = h("button", { class: "btn small", type: "button", onClick: () => openMenu(muteBtn, [10, 60, 1440].map((m) => ({
        label: `Mute ${r.sender_name} for ${m === 1440 ? "1 day" : m === 60 ? "1 hour" : "10 minutes"}`,
        onClick: () => act(post(`/api/mod/users/${encodeURIComponent(r.sender)}/mute`, { minutes: m }), () => {}),
      }))) }, "Mute sender…");
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

  // ---------- settings ----------
  async function settingsView() {
    const { settings: s, storage_configured: storageOk, presets, loading_preview: preview } = await get("/api/admin/settings");
    const ld = s.loading;
    const assets = { image: undefined, music: undefined };      // undefined = unchanged, "" = removed, id = new
    const f = (label, el, hint = "") => h("label", { class: "field" }, h("span", { class: "field-label" }, label), el, hint ? h("small", { class: "muted" }, hint) : null);
    const num = (v, min, max) => h("input", { class: "input", type: "number", min, max, value: String(v) });
    const check = (v, label, hint = "") => { const el = h("input", { type: "checkbox", checked: Boolean(v) }); return { el, row: h("label", { class: "choice" }, el, h("span", {}, h("strong", {}, label), hint ? h("small", {}, hint) : null)) }; };

    const mode = h("select", { class: "input" }, [["whitelist", "Whitelist only"], ["open_approval", "Open, admin approves each account"], ["closed", "Closed"]].map(([v, l]) => h("option", { value: v, selected: s.registration_mode === v }, l)));
    const announcement = h("input", { class: "input", maxlength: "300", value: s.announcement, placeholder: "Shown to everybody at the top. Empty = no banner." });
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
    function assetButtons(kind, field, accept, previewEl, render) {
      const pick = h("button", { class: "btn small", type: "button", onClick: () => {
        const input = h("input", { type: "file", accept });
        input.addEventListener("change", async () => {
          if (!input.files[0]) return;
          status.textContent = "Uploading…";
          try { const att = await uploadFile(input.files[0], { kind }).promise; assets[field] = att.id; previewEl.replaceChildren(render(att.url)); status.textContent = "Uploaded. Press “Save settings” to use it."; }
          catch (e) { status.textContent = ""; toast(e.message, "error"); }
        });
        input.click();
      } }, "Choose file");
      const remove = h("button", { class: "btn small danger-text", type: "button", onClick: () => { assets[field] = ""; previewEl.replaceChildren(h("span", { class: "muted" }, "Will be removed when you save.")); } }, "Remove");
      return h("div", { class: "button-row" }, pick, remove);
    }

    async function save() {
      const loading = { title: title.value, music_volume: Number(volume.value), allow_user_image: allowImg.el.checked, allow_user_music: allowMusic.el.checked,
        allow_user_mute: allowMute.el.checked, max_image_mb: Number(maxLoadImg.value), max_music_mb: Number(maxLoadMusic.value) };
      if (assets.image !== undefined) loading.image_asset = assets.image;
      if (assets.music !== undefined) loading.music_asset = assets.music;
      try {
        await put("/api/admin/settings", {
          registration_mode: mode.value, announcement: announcement.value, messages_per_minute: Number(perMinute.value),
          uploads_enabled: uploadsOn.el.checked, max_image_mb: Number(maxImage.value), max_video_mb: Number(maxVideo.value),
          max_file_mb: Number(maxFile.value), user_quota_mb: Number(quota.value),
          blocked_extensions: blocked.value.split(",").map((x) => x.trim()).filter(Boolean),
          loading, background: { default: bgDefault.value, allow_custom: bgCustom.el.checked },
        });
        toast("Settings saved.");
        assets.image = assets.music = undefined;
        status.textContent = "";
      } catch (e) { toast(e.message, "error"); }
    }

    return h("form", { class: "settings-form", onSubmit: (e) => { e.preventDefault(); save(); } },
      h("section", { class: "card" }, h("h2", {}, "General"), f("Who can register", mode), f("Announcement banner", announcement), f("Messages per minute and person", perMinute)),
      h("section", { class: "card" }, h("h2", {}, "Uploads"), uploadsOn.row,
        h("div", { class: "grid-2" }, f("Max picture size (MB)", maxImage), f("Max video size (MB)", maxVideo), f("Max other file size (MB)", maxFile), f("Storage per person (MB)", quota)),
        f("Blocked file endings", blocked, "Separated by commas. Programs and web pages are blocked by default.")),
      h("section", { class: "card" }, h("h2", {}, "Loading screen"), f("Title", title),
        h("div", { class: "field-label" }, "Default picture"), imgPreview, assetButtons("loading_image", "image", "image/*", imgPreview, (url) => h("img", { src: url, alt: "" })),
        h("div", { class: "field-label", style: "margin-top:12px" }, "Default music"), musicPreview, assetButtons("loading_music", "music", "audio/*", musicPreview, (url) => h("audio", { controls: true, src: url })),
        f("Music volume", volume), allowImg.row, allowMusic.row, allowMute.row,
        h("div", { class: "grid-2" }, f("Max picture size (MB)", maxLoadImg), f("Max music size (MB)", maxLoadMusic)), status),
      h("section", { class: "card" }, h("h2", {}, "Chat backgrounds"), f("Default background for everybody", bgDefault), bgCustom.row),
      h("button", { class: "btn primary", type: "submit" }, "Save settings"));
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
  main.append(h("div", { class: "page wide" }, h("h1", {}, isAdmin ? "Administration" : "Moderation"), tabsEl, content));
  load();
}
