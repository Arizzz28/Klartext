// "Download my data" and "Delete my account". Both talk to the server (accounts.py); the server checks the password.
import { get, post } from "./api.js";
import { h, modal, toast } from "./ui.js";

export async function downloadMyData() {
  try {
    const data = await get("/api/me/export");
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 1)], { type: "application/json" }));
    const link = h("a", { href: url, download: "chatisfying-my-data.json" });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (e) { toast(e.message, "error"); }
}

export function openDeleteDialog(state) {
  const password = h("input", { class: "input", type: "password", autocomplete: "current-password", required: true });
  const confirm = h("input", { class: "input", autocomplete: "off", required: true, placeholder: state.me.username });
  const groupBox = h("input", { type: "checkbox", checked: true });
  const msg = h("p", { class: "form-msg", role: "alert" });
  const submit = h("button", { class: "btn danger", type: "submit" }, "Delete my account for good");
  const form = h("form", { class: "dialog-body" },
    h("p", {}, "This cannot be undone. Your account, your notes, calendar, tasks, files, coins and settings are deleted."),
    h("p", {}, h("strong", {}, "Your private chats are deleted for both sides"), ", so the other person loses those messages too."),
    h("label", { class: "choice" }, groupBox, h("span", {}, h("strong", {}, "Also delete my messages in groups"),
      h("small", {}, "If you leave this off, they stay and show “Deleted user”."))),
    h("label", { class: "field" }, h("span", { class: "field-label" }, "Your password"), password),
    h("label", { class: "field" }, h("span", { class: "field-label" }, `Type your username (${state.me.username}) to confirm`), confirm),
    msg, h("div", { class: "dialog-actions" }, submit));
  const box = modal("Delete my account", form);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    submit.disabled = true;
    try {
      await post("/api/me/delete", { password: password.value, confirm: confirm.value, delete_group_messages: groupBox.checked });
      box.close();
      localStorage.removeItem("chatisfying_token");
      location.href = "login.html";
    } catch (err) { msg.textContent = err.message; msg.className = "form-msg error"; submit.disabled = false; }
  });
}
