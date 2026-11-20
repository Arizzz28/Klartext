// Settings: theme, password, log out.
import { post } from "../api.js";
import { logout } from "../auth.js";
import { THEME_KEY, applyTheme, h, toast } from "../ui.js";

export const usesList = false;

export async function render({ main }) {
  const current = localStorage.getItem(THEME_KEY) || "system";
  const themeOption = (value, label) => h("label", { class: "choice" },
    h("input", {
      type: "radio", name: "theme", value, checked: current === value,
      onChange: () => { localStorage.setItem(THEME_KEY, value); applyTheme(value); },
    }),
    h("span", {}, h("strong", {}, label)));

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
    h("section", { class: "card" }, h("h2", {}, "Password"), form),
    h("section", { class: "card" }, h("h2", {}, "Session"),
      h("button", { class: "btn", type: "button", onClick: logout }, "Log out"))));
}
