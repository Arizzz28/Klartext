// The message list + input box, shared by private chats and group chats.
import { h, icon, formatTime, toast } from "./ui.js";

export function createChatPane({ me, header, load, send, getUser = null, onSent = () => {} }) {
  const messagesEl = h("div", { class: "messages", role: "log", "aria-live": "polite" });
  const empty = h("p", { class: "chat-empty" }, "No messages yet. Say hello!");
  const input = h("textarea", { class: "composer-input", rows: "1", maxlength: "2000", placeholder: "Write a message", "aria-label": "Message" });
  const sendBtn = h("button", { class: "btn primary send", type: "button", "aria-label": "Send message", onClick: submit }, icon("send"));
  const root = h("section", { class: "chat" }, header, messagesEl, h("div", { class: "composer" }, input, sendBtn));

  messagesEl.append(empty);
  let lastId = 0;
  let first = true;
  let busy = false;

  function bubble(m) {
    const mine = m.from === me.username;
    const author = !mine && getUser ? getUser(m.from) : null;
    return h("div", { class: `msg ${mine ? "mine" : "theirs"}` },
      author ? h("span", { class: "msg-author" }, author.display_name) : null,
      h("div", { class: "bubble" },
        h("span", { class: "msg-text" }, m.text),
        h("time", { class: "msg-time" }, formatTime(m.ts))));
  }

  function addMessages(msgs) {
    const nearBottom = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 90;
    empty.remove();
    for (const m of msgs) {
      messagesEl.append(bubble(m));
      lastId = Math.max(lastId, m.id);
    }
    if (first || nearBottom) messagesEl.scrollTop = messagesEl.scrollHeight;
    first = false;
  }

  async function poll() {
    if (busy) return;
    busy = true;
    try {
      const msgs = await load(lastId);
      if (msgs.length) addMessages(msgs);
    } catch { /* a short network problem: the next poll tries again */ }
    busy = false;
  }

  async function submit() {
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    input.style.height = "auto";
    try {
      await send(text);
      await poll();
      onSent();
    } catch (e) {
      input.value = text;
      toast(e.message, "error");
    }
  }

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  });
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 140) + "px";
  });

  poll();
  const timer = setInterval(poll, 3000);       // "automatic updates": ask the server every 3 seconds
  return { root, destroy: () => clearInterval(timer), focus: () => input.focus() };
}
