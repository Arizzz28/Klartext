// The Terms of Service / Privacy Policy dialog. Shown to everybody who has not accepted the CURRENT version yet
// (new texts => everybody has to accept again). The server enforces this too: without it nothing else works.
import { post } from "./api.js";
import { fillLegal } from "./legal.js";
import { h, modal } from "./ui.js";

async function loadText(url) {
  // The texts are our own static pages; we show what is inside their <main> element.
  try {
    const res = await fetch(url, { cache: "no-cache" });
    const doc = new DOMParser().parseFromString(await res.text(), "text/html");
    const main = doc.querySelector("main");
    if (!main) throw new Error("no text");
    return [...main.children].map((el) => document.importNode(el, true));
  } catch {
    return [h("p", {}, "The text could not be loaded here. Please open it with the link above.")];
  }
}

export async function showConsent(state, onDone) {
  const box = (title, href) => {
    const body = h("div", { class: "legal-scroll", tabindex: "0", "aria-label": title }, h("p", { class: "muted" }, "Loading…"));
    loadText(href).then((nodes) => { body.replaceChildren(...nodes); fillLegal(body); });
    return h("section", {}, h("h3", {}, h("a", { href, target: "_blank", rel: "noopener" }, title)), body);
  };
  const check = h("input", { type: "checkbox", id: "consent-check" });
  const button = h("button", { class: "btn primary", type: "submit", disabled: true }, "Weiter");
  const msg = h("p", { class: "form-msg", role: "alert" });
  check.addEventListener("change", () => { button.disabled = !check.checked; });
  const form = h("form", { class: "dialog-body consent" },
    h("p", {}, "Bevor du Chatisfying nutzt, lies bitte die folgenden Texte. Wichtig: Nachrichten und Passwörter sind hier nicht garantiert sicher, und Daten können verloren gehen. Details stehen in den Nutzungsbedingungen."),
    box("Nutzungsbedingungen", "terms.html"),
    box("Datenschutzerklärung", "privacy.html"),
    h("label", { class: "choice" }, check,
      h("span", {}, h("strong", {}, "Ich akzeptiere die Nutzungsbedingungen"),
        h("small", {}, "und habe die Datenschutzerklärung zur Kenntnis genommen."))),
    msg, h("div", { class: "dialog-actions" }, h("button", { class: "btn", type: "button", onClick: () => state.logout() }, "Abmelden"), button));
  const dialog = modal("Nutzungsbedingungen & Datenschutz", form, null, false);
  dialog.root?.classList?.add("wide");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!check.checked) return;
    button.disabled = true;
    try {
      state.me = await post("/api/me/consent", { terms: true, privacy: true, terms_version: state.me.terms_version, privacy_version: state.me.privacy_version });
      dialog.close();
      onDone?.();
    } catch (err) {
      msg.textContent = err.message; msg.className = "form-msg error"; button.disabled = false;
    }
  });
}
