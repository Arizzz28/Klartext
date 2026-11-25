// Settings: theme, password, log out.
import { get, post, put } from "../api.js";
import { downloadMyData, openDeleteDialog } from "../account.js";
import { logout } from "../auth.js";
import { disablePush, enablePush, pushState } from "../push.js";
import { openTabEditor } from "../tabeditor.js";
import { availableTabs } from "../tabs.js";
import { THEME_KEY, applyTheme, h, toast } from "../ui.js";
import { uploadFile } from "../upload.js";

const DESIGN_TEXT = { classic: "Classic", glass: "Glass (translucent)", paper: "Paper (calm, light)", midnight: "Midnight (dark blue)", neon: "Neon (bright accents)" };
const PUSH_TEXT = {
  on: "Push messages are on for this device.", off: "Push messages are off on this device.",
  denied: "Notifications are blocked in your device settings.", unsupported: "This browser can't receive push messages.",
  "needs-home-screen": "On an iPad or iPhone this only works after you add Chatisfying to the Home Screen (Share button → “Add to Home Screen”) and open it from there.",
};

// Saves a preference and redraws the app (design, tabs, bubble, layout).
async function savePrefs(state, changes) {
  try { state.me = await put("/api/me/prefs", changes); state.onMeChanged?.(); return true; }
  catch (e) { toast(e.message, "error"); return false; }
}

function designCard(state) {
  if (!state.can("design.change")) return null;
  const current = state.me.design;
  return h("section", { class: "card" }, h("h2", {}, "Design mode"),
    h("p", { class: "muted" }, "Which designs you can use depends on your rank."),
    h("fieldset", { class: "choices" }, h("legend", { class: "sr-only" }, "Design"),
      ...state.me.allowed_designs.map((d) => h("label", { class: "choice" },
        h("input", { type: "radio", name: "design", value: d, checked: current === d, onChange: () => savePrefs(state, { design: d }) }),
        h("span", {}, h("strong", {}, DESIGN_TEXT[d] || d))))));
}

function layoutCard(state) {
  const canMove = state.can("layout.move"), canTabs = state.can("tabs.editor"), canBubble = state.can("tabs.bubble");
  if (!canMove && !canTabs && !canBubble) return null;
  const lay = { side: "left", list_side: "inner", list_width: 330, rail: true, ...(state.me.prefs?.layout || {}) };
  const row = [];
  if (canMove) {
    const sel = (label, key, options) => h("label", { class: "field" }, h("span", { class: "field-label" }, label),
      h("select", { class: "input", onChange: (e) => savePrefs(state, { layout: { ...lay, [key]: e.target.value === "true" ? true : e.target.value === "false" ? false : e.target.value } }) },
        options.map(([v, l]) => h("option", { value: String(v), selected: lay[key] === v }, l))));
    row.push(sel("Navigation bar", "side", [["left", "Left"], ["right", "Right"]]),
      sel("Chat list", "list_side", [["inner", "Next to the navigation"], ["outer", "On the other side of the chat"]]),
      sel("Navigation style", "rail", [[true, "Icons only (more room)"], [false, "Icons with names"]]),
      h("p", { class: "hint" }, "You can also drag the edge of the chat list to change its width."));
  }
  if (canTabs) row.push(h("button", { class: "btn", type: "button", onClick: () => openTabEditor(state) }, "Choose and sort my tabs…"));
  if (canBubble) {
    const on = state.me.prefs?.bubble?.on !== false;
    const box = h("input", { type: "checkbox", checked: on, onChange: () => savePrefs(state, { bubble: { on: box.checked, pos: state.me.prefs?.bubble?.pos || { x: 0.9, y: 0.8 } } }) });
    row.push(h("label", { class: "choice" }, box, h("span", {}, h("strong", {}, "Floating tab bubble"), h("small", {}, "A movable round button that opens all your tabs."))));
  }
  return h("section", { class: "card" }, h("h2", {}, "Layout and tabs"), ...row);
}

// "After logging in, open …": everybody can choose; an empty choice means the default of the operator.
function startCard(state) {
  const options = availableTabs(state.me);
  const current = state.me.prefs?.start_page || "";
  const sel = h("select", { class: "input", onChange: () => savePrefs(state, { start_page: sel.value }) },
    h("option", { value: "", selected: current === "" }, "Default"),
    options.map((t) => h("option", { value: t.id, selected: current === t.id }, t.label)));
  return h("section", { class: "card" }, h("h2", {}, "Start page"),
    h("label", { class: "field" }, h("span", { class: "field-label" }, "Open this page after logging in"), sel),
    h("p", { class: "hint" }, "Links you tap (for example from a notification) still open the page they point to."));
}

async function pushCard(state) {
  if (!state.can("push.use")) return null;
  const text = h("p", { class: "muted" });
  const btn = h("button", { class: "btn", type: "button" });
  const preview = h("input", { type: "checkbox", checked: Boolean(state.me.prefs?.push_preview), onChange: () => savePrefs(state, { push_preview: preview.checked }) });
  async function draw() {
    const st = await pushState();
    text.textContent = PUSH_TEXT[st] || "";
    btn.hidden = !["on", "off"].includes(st);
    btn.textContent = st === "on" ? "Turn push messages off" : "Turn push messages on";
    btn.onclick = async () => {
      try { if (st === "on") await disablePush(); else await enablePush(); } catch (e) { toast(e.message, "error"); }
      draw();
    };
  }
  await draw();
  return h("section", { class: "card" }, h("h2", {}, "Push notifications"), text, btn,
    h("label", { class: "choice" }, preview, h("span", {}, h("strong", {}, "Show the message text in the push message"),
      h("small", {}, "Off by default: the push message then only says who wrote. Text passes through the push service of your browser/device maker when this is on."))));
}

function legalCard() {
  const link = (href, label) => h("li", {}, h("a", { href, target: "_blank", rel: "noopener" }, label));
  return h("section", { class: "card" }, h("h2", {}, "Rechtliches"),
    h("ul", { class: "plain-list" }, link("terms.html", "Nutzungsbedingungen"), link("privacy.html", "Datenschutzerklärung"), link("imprint.html", "Impressum / Anbieterangaben")));
}

export const usesList = false;

export async function render({ main, state }) {
  const current = localStorage.getItem(THEME_KEY) || "system";
  const themeOption = (value, label) => h("label", { class: "choice" },
    h("input", {
      type: "radio", name: "theme", value, checked: current === value,
      onChange: () => { localStorage.setItem(THEME_KEY, value); applyTheme(value); },
    }),
    h("span", {}, h("strong", {}, label)));


  // ---------- loading screen (picture + music) ----------
  let loading = null;
  try { loading = await get("/api/loading"); } catch { /* card stays hidden */ }
  const loadingCard = loading && (loading.allow_user_image || loading.allow_user_music || loading.can_mute)
    ? buildLoadingCard(loading) : null;

  const cur = h("input", { class: "input", type: "password", autocomplete: "current-password", required: true });
  const next = h("input", { class: "input", type: "password", autocomplete: "new-password", required: true, minlength: "8" });
  const again = h("input", { class: "input", type: "password", autocomplete: "new-password", required: true, minlength: "8" });
  const msg = h("p", { class: "form-msg", role: "alert" });
  const submit = h("button", { class: "btn primary", type: "submit" }, "Change password");

  const form = h("form", {
    onSubmit: async (e) => {
      e.preventDefault();
      msg.textContent = "";
      if (next.value !== again.value) { msg.textContent = "The new passwords don't match."; msg.className = "form-msg error"; return; }
      submit.disabled = true;
      try {
        await post("/api/me/password", { current: cur.value, new: next.value });
        toast("Password changed. Please log in again.");
        setTimeout(logout, 1200);
      } catch (err) { msg.textContent = err.message; msg.className = "form-msg error"; submit.disabled = false; }
    },
  },
    h("label", { class: "field" }, h("span", { class: "field-label" }, "Current password"), cur),
    h("label", { class: "field" }, h("span", { class: "field-label" }, "New password (min. 8 characters)"), next),
    h("label", { class: "field" }, h("span", { class: "field-label" }, "Repeat new password"), again),
    msg, submit);

  const [layoutC, designC, pushC] = [layoutCard(state), designCard(state), await pushCard(state)];
  main.append(h("div", { class: "page" },
    h("h1", {}, "Settings"),
    designC,
    h("section", { class: "card" },
      h("h2", {}, "Appearance"),
      h("fieldset", { class: "choices" }, h("legend", { class: "sr-only" }, "Theme"),
        themeOption("system", "Match my device"), themeOption("light", "Light"), themeOption("dark", "Dark"))),
    startCard(state), layoutC, pushC,
    loadingCard,
    h("section", { class: "card" }, h("h2", {}, "Password"), form),
    legalCard(),
    h("section", { class: "card" }, h("h2", {}, "Your data"),
      h("p", { class: "muted" }, "You can download a copy of what is stored about you, or delete your account and your data."),
      h("div", { class: "row-actions" },
        h("button", { class: "btn", type: "button", onClick: downloadMyData }, "Download my data"),
        h("button", { class: "btn danger-text", type: "button", onClick: () => openDeleteDialog(state) }, "Delete my account…"))),
    h("section", { class: "card" }, h("h2", {}, "Session"),
      h("button", { class: "btn", type: "button", onClick: logout }, "Log out"))));
}


function buildLoadingCard(loading) {
  const status = h("p", { class: "muted" });
  const preview = h("div", { class: "loading-preview" });
  const drawPreview = (cfg) => {
    preview.replaceChildren(cfg.image ? h("img", { src: cfg.image, alt: "Your loading picture" }) : h("span", { class: "muted" }, "No picture set (the Chatisfying logo is shown)."));
  };
  drawPreview(loading);

  async function chooseFile(kind, field, accept) {
    const input = h("input", { type: "file", accept });
    input.addEventListener("change", async () => {
      const file = input.files[0];
      if (!file) return;
      status.textContent = "Uploading…";
      try {
        const { promise } = uploadFile(file, { kind });
        const att = await promise;
        await put("/api/me/loading", { [field]: att.id });
        loading = await get("/api/loading");
        drawPreview(loading);
        status.textContent = "Saved. You will see it the next time the app loads.";
      } catch (e) { status.textContent = ""; toast(e.message, "error"); }
    });
    input.click();
  }

  async function reset(field, text) {
    try { await put("/api/me/loading", { [field]: "" }); loading = await get("/api/loading"); drawPreview(loading); status.textContent = text; }
    catch (e) { toast(e.message, "error"); }
  }

  const rows = [];
  if (loading.allow_user_image) {
    rows.push(h("div", { class: "button-row" },
      h("button", { class: "btn small", type: "button", onClick: () => chooseFile("loading_image", "image_asset", "image/*") }, "Choose my picture"),
      h("button", { class: "btn small", type: "button", onClick: () => reset("image_asset", "Back to the default picture.") }, "Use the default picture")));
  }
  if (loading.allow_user_music) {
    rows.push(h("div", { class: "button-row" },
      h("button", { class: "btn small", type: "button", onClick: () => chooseFile("loading_music", "music_asset", "audio/*") }, "Choose my music"),
      h("button", { class: "btn small", type: "button", onClick: () => reset("music_asset", "Back to the default music.") }, "Use the default music")));
  }
  if (loading.can_mute) {
    const box = h("input", { type: "checkbox", checked: Boolean(loading.music), onChange: async () => {
      try { await put("/api/me/loading", { music_off: !box.checked }); status.textContent = "Saved."; }
      catch (e) { toast(e.message, "error"); box.checked = !box.checked; }
    } });
    rows.push(h("label", { class: "choice" }, box, h("span", {}, h("strong", {}, "Play music while loading"))));
  }
  return h("section", { class: "card" }, h("h2", {}, "Loading screen"), preview, ...rows, status);
}
