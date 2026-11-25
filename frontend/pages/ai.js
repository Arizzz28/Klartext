// AI tab (Google Gemini). Read the notice: your question and the chats you tick are sent to Google.
import { del, get, post } from "../api.js";
import { emptyState, h, toast } from "../ui.js";

export const usesList = false;

export async function render({ main }) {
  const page = h("div", { class: "page" }, h("h1", {}, "AI helper"));
  main.append(page);
  const status = await get("/api/ai/status");
  if (!status.available) {
    page.append(h("p", { class: "notice" }, !status.switched_on ? "The AI helper is switched off by the Owner." : "The AI helper is switched on, but the server has no Gemini key yet."));
    return;
  }
  page.append(h("p", { class: "notice" }, status.notice));
  if (!status.consented) {
    const adult = h("input", { type: "checkbox" }), understood = h("input", { type: "checkbox" });
    const go = h("button", { class: "btn primary", type: "button", onClick: async () => {
      try { await post("/api/ai/consent", { adult: adult.checked, understood: understood.checked }); location.reload(); } catch (e) { toast(e.message, "error"); }
    } }, "Continue");
    page.append(h("section", { class: "card" },
      h("label", { class: "choice" }, adult, h("span", {}, h("strong", {}, "I am 18 years old or older."))),
      h("label", { class: "choice" }, understood, h("span", {}, h("strong", {}, "I understand that my questions go to Google and that I should not send secrets or other people's private data."))), go));
    return;
  }
  const log = h("div", { class: "ai-log", "aria-live": "polite" });
  const input = h("textarea", { class: "input", rows: "3", maxlength: "4000", placeholder: "Ask something…" });
  const counter = h("span", { class: "muted" }, `${status.used_today} / ${status.daily_limit} questions used today`);
  const picks = h("div", { class: "ai-picks" });
  const privateOk = h("input", { type: "checkbox" });
  const history = [];
  let chats = [];
  if (status.max_context_messages > 0) {
    const [groups, convos] = await Promise.all([get("/api/groups").catch(() => []), get("/api/messages/conversations").catch(() => [])]);
    chats = [...groups.map((g) => ({ type: "group", key: g.id, label: `Group: ${g.name}` })), ...convos.map((c) => ({ type: "dm", key: c.user.username, label: `Private: ${c.user.display_name}` }))];
    picks.append(h("details", {}, h("summary", {}, "Add chats as context (optional)"),
      h("p", { class: "muted" }, `The last ${status.max_context_messages} messages of each chosen chat (max. 3) are sent to Google with your question. Nothing is sent unless you tick it here.`),
      ...chats.map((c, i) => h("label", { class: "choice" }, h("input", { type: "checkbox", "data-i": String(i) }), h("span", {}, c.label))),
      h("label", { class: "choice" }, privateOk, h("span", {}, h("strong", {}, "I confirm: private chats may be sent, including what the other person wrote."), h("small", {}, "Only do this if the other person is fine with it.")))));
  }
  async function ask() {
    const prompt = input.value.trim();
    if (!prompt) return;
    const selected = [...picks.querySelectorAll("input[data-i]:checked")].map((el) => chats[Number(el.dataset.i)]).map(({ type, key }) => ({ type, key }));
    log.append(h("div", { class: "ai-msg me" }, prompt));
    input.value = "";
    const wait = h("div", { class: "ai-msg bot muted" }, "…");
    log.append(wait);
    try {
      const r = await post("/api/ai/ask", { prompt, history: history.slice(-8), context_chats: selected, private_ok: privateOk.checked });
      wait.textContent = r.answer; wait.classList.remove("muted");
      history.push({ role: "user", text: prompt }, { role: "model", text: r.answer });
      counter.textContent = `${r.used_today} / ${r.daily_limit} questions used today`;
    } catch (e) { wait.textContent = e.message; wait.classList.add("late"); }
    log.scrollTop = log.scrollHeight;
  }
  page.append(log, picks, input, h("div", { class: "button-row" }, h("button", { class: "btn primary", type: "button", onClick: ask }, "Ask"), counter,
    h("button", { class: "btn small", type: "button", onClick: async () => { await del("/api/ai/consent"); location.reload(); } }, "Withdraw my consent")));
  void emptyState;
}
