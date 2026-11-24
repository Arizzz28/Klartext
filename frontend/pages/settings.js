// Settings: theme, password, log out.
import { get, post, put } from "../api.js";
import { logout } from "../auth.js";
import { THEME_KEY, applyTheme, h, toast } from "../ui.js";
import { uploadFile } from "../upload.js";

export const usesList = false;

export async function render({ main }) {
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

  main.append(h("div", { class: "page" },
    h("h1", {}, "Settings"),
    h("section", { class: "card" },
      h("h2", {}, "Appearance"),
      h("fieldset", { class: "choices" }, h("legend", { class: "sr-only" }, "Theme"),
        themeOption("system", "Match my device"), themeOption("light", "Light"), themeOption("dark", "Dark"))),
    loadingCard,
    h("section", { class: "card" }, h("h2", {}, "Password"), form),
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
