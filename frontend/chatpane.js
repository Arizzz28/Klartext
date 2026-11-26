// The whole chat window: header, messages (with replies, reactions, attachments), message box,
// background and chat menu. Used by private chats and group chats.
import { del, get, patch, post, put } from "./api.js";
import { openEmojiPicker } from "./emoji.js";
import { uploadFile } from "./upload.js";
import { avatar, confirmDialog, fileToBackground, formatBytes, formatTime, h, icon, lightbox, modal, openMenu, toast } from "./ui.js";

const MB = 1024 * 1024;

// Chat background presets (the names come from the server, the looks live here).
export const PRESETS = {
  ocean: "linear-gradient(160deg, #0f4c5c, #1b7f8a 55%, #5cc8d2)",
  forest: "linear-gradient(160deg, #1d3b2a, #3f7d4e 60%, #a7c957)",
  sunset: "linear-gradient(160deg, #5b2a86, #d1495b 60%, #f2a900)",
  night: "linear-gradient(160deg, #0b1026, #1b2a5a 70%, #3a4a8a)",
  paper: "linear-gradient(#ece6da, #ece6da)",
  graphite: "linear-gradient(#2b2f33, #2b2f33)",
};

export function backgroundCss(value, dim) {
  if (!value) return "";
  const layer = value.startsWith("preset:") ? PRESETS[value.slice(7)] : `url("${value}")`;
  if (!layer) return "";
  const shade = dim ? `linear-gradient(rgba(0,0,0,${dim / 100}), rgba(0,0,0,${dim / 100}))` : "";
  return [shade, layer].filter(Boolean).join(", ");
}

export function createChatPane({ me, chat, title, subtitle = "", avatarEntity, backHref, extraButtons = [], config = {}, onActivity = () => {} }) {
  const base = `/api/chats/${chat.type}/${encodeURIComponent(chat.key)}`;
  const nodes = new Map();          // message id -> element on screen
  const sigs = new Map();           // message id -> what it looked like (to redraw only when something changed)
  const data = new Map();           // message id -> message data
  let canModerate = false;
  let windowFull = false;
  let olderDone = false;
  let replyTo = null;
  let editing = null;
  let pending = [];                 // files being uploaded
  let busy = false;
  let first = true;
  let bg = { background: "", dim: 30, default: "", allow_custom: true };

  // ---------- header ----------
  const avatarSlot = h("div");
  const titleEl = h("strong");
  const subEl = h("span", { class: "muted" });
  const menuBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Chat options", onClick: () => openMenu(menuBtn, chatMenu()) }, icon("more"));
  const header = h("header", { class: "chat-head" },
    backHref ? h("a", { class: "icon-btn back", href: backHref, "aria-label": "Back" }, icon("back")) : null,
    avatarSlot, h("div", { class: "chat-title" }, titleEl, subEl), ...extraButtons, menuBtn);

  function updateHeader({ title: t, subtitle: s, avatarEntity: a }) {
    if (t !== undefined) titleEl.textContent = t;
    if (s !== undefined) subEl.textContent = s;
    if (a) avatarSlot.replaceChildren(avatar(a));
  }
  updateHeader({ title, subtitle, avatarEntity });

  // ---------- message list ----------
  const olderBtn = h("button", { class: "btn small older", type: "button", hidden: true, onClick: loadOlder }, "Load older messages");
  const empty = h("p", { class: "chat-empty" }, "No messages yet. Say hello!");
  const messagesEl = h("div", { class: "messages", role: "log", "aria-live": "polite" }, olderBtn, empty);

  const nearBottom = () => messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 120;
  const scrollBottom = () => { messagesEl.scrollTop = messagesEl.scrollHeight; };

  const signature = (m) => JSON.stringify([m.text, m.edited, m.deleted, m.sender_name, canModerate,
    m.reactions.map((r) => [r.emoji, r.count, r.mine]), m.attachments.map((a) => a.id), m.reply && [m.reply.text, m.reply.deleted]]);

  function place(el, id) {                      // keep the messages in order
    let node = messagesEl.lastElementChild;
    while (node && (!node.dataset.id || Number(node.dataset.id) > id)) node = node.previousElementSibling;
    if (node && node.dataset.id) node.after(el); else olderBtn.after(el);
  }

  function upsert(m) {
    data.set(m.id, m);
    const s = signature(m);
    const existing = nodes.get(m.id);
    if (!existing) {
      const el = renderMessage(m);
      nodes.set(m.id, el); sigs.set(m.id, s); place(el, m.id);
    } else if (sigs.get(m.id) !== s) {
      const el = renderMessage(m);
      existing.replaceWith(el); nodes.set(m.id, el); sigs.set(m.id, s);
    }
  }

  function forget(id) {
    nodes.get(id)?.remove(); nodes.delete(id); sigs.delete(id); data.delete(id);
  }

  function applyWindow(list) {
    const stick = first || nearBottom();
    const ids = new Set(list.map((m) => m.id));
    list.forEach(upsert);
    if (list.length === 0) [...nodes.keys()].forEach(forget);                  // chat was cleared
    else for (const id of [...nodes.keys()]) if (id >= list[0].id && !ids.has(id)) forget(id);
    empty.hidden = nodes.size > 0;
    if (stick) scrollBottom();
    first = false;
  }

  // Tell the server what you have seen, so the unread counters are right on every device.
  let lastReadId = 0;
  function markRead(list) {
    const newest = list.length ? Math.max(...list.map((m) => m.id)) : 0;
    if (!newest || newest <= lastReadId || document.hidden) return;
    lastReadId = newest;
    post(`${base}/read`).then(() => window.dispatchEvent(new CustomEvent("chatisfying:read"))).catch(() => { lastReadId = 0; });
  }

  let quiet = 0, lastSig = "", stopped = false, timer = null;
  async function poll() {
    if (busy || document.hidden) return;
    busy = true;
    try {
      const res = await get(`${base}/messages?limit=100`);
      canModerate = res.can_moderate;
      windowFull = res.has_more;
      applyWindow(res.messages);
      olderBtn.hidden = !(windowFull && !olderDone);
      markRead(res.messages);
      const sig = JSON.stringify(res.messages);          // nothing new -> ask less often (less load, less lag)
      quiet = sig === lastSig ? quiet + 1 : 0;
      lastSig = sig;
    } catch { /* a short network problem: the next poll tries again */ }
    busy = false;
  }

  async function loadOlder() {
    const oldest = Math.min(...nodes.keys());
    if (!Number.isFinite(oldest)) return;
    try {
      const res = await get(`${base}/messages?limit=100&before=${oldest}`);
      const before = messagesEl.scrollHeight;
      res.messages.forEach(upsert);
      messagesEl.scrollTop += messagesEl.scrollHeight - before;
      if (!res.has_more) { olderDone = true; olderBtn.hidden = true; }
    } catch (e) { toast(e.message, "error"); }
  }

  // ---------- one message ----------
  function renderAttachment(a) {
    const retry = (el) => {
      let tried = false;
      el.addEventListener("error", async () => {
        if (tried) return;
        tried = true;
        try { el.src = (await get(`/api/uploads/${a.id}/url`)).url; } catch { /* give up */ }
      });
      return el;
    };
    if (a.kind === "image") {
      const img = h("img", { class: "att-img", src: a.url, alt: a.name, loading: "lazy" });
      img.addEventListener("click", () => lightbox(img.src));
      return retry(img);
    }
    if (a.kind === "video") return retry(h("video", { class: "att-video", controls: true, preload: "metadata", src: a.url }));
    if (a.kind === "audio") return retry(h("audio", { class: "att-audio", controls: true, preload: "none", src: a.url }));
    return h("a", {
      class: "att-file", href: a.url, rel: "noopener", download: a.name,
      onClick: async (e) => {
        e.preventDefault();
        try {
          const link = document.createElement("a");
          link.href = (await get(`/api/uploads/${a.id}/url`)).url;
          link.click();
        } catch (err) { toast(err.message, "error"); }
      },
    }, icon("file"), h("span", { class: "att-meta" }, h("strong", {}, a.name), h("small", {}, formatBytes(a.size))));
  }

  function toolbar(m, mine) {
    if (m.deleted) return null;
    const tool = (name, label, fn, danger = false) =>
      h("button", { class: `tool${danger ? " danger-text" : ""}`, type: "button", title: label, "aria-label": label, onClick: (e) => { e.stopPropagation(); fn(e.currentTarget); } }, icon(name));
    return h("div", { class: "toolbar" },
      tool("smile", "Add reaction", (btn) => openEmojiPicker(btn, (emoji) => toggleReaction(m, emoji, true))),
      tool("reply", "Reply", () => startReply(m)),
      mine ? tool("edit", "Edit", () => startEdit(m)) : null,
      !mine ? tool("flag", "Report", () => reportDialog(m)) : null,
      (mine || canModerate) ? tool("trash", "Delete", () => deleteMessage(m), true) : null);
  }

  function renderMessage(m) {
    if (m.system) return h("div", { class: "msg system", "data-id": m.id }, h("span", { class: "sys-note" }, m.text));
    const mine = m.sender === me.username;
    const bubble = h("div", { class: "bubble" });
    if (m.reply) {
      bubble.append(h("button", { class: "quote", type: "button", onClick: () => jumpTo(m.reply.id) },
        h("strong", {}, m.reply.sender_name), h("span", {}, m.reply.deleted ? "Message deleted" : (m.reply.text || "Attachment"))));
    }
    if (m.deleted) {
      bubble.append(h("em", { class: "msg-deleted" }, "Message deleted"));
    } else {
      m.attachments.forEach((a) => bubble.append(renderAttachment(a)));
      if (m.text) bubble.append(h("span", { class: "msg-text" }, m.text));
    }
    bubble.append(h("time", { class: "msg-time" }, formatTime(m.ts) + (m.edited ? " · edited" : "")));
    const el = h("div", { class: `msg ${mine ? "mine" : "theirs"}${m.deleted ? " is-deleted" : ""}`, "data-id": m.id },
      !mine && chat.type === "group" ? h("span", { class: "msg-author" }, m.sender_name) : null,
      h("div", { class: "bubble-row" }, bubble, toolbar(m, mine)),
      m.reactions.length ? h("div", { class: "reactions" }, m.reactions.map((r) =>
        h("button", { class: `chip${r.mine ? " mine" : ""}`, type: "button", title: r.users.join(", "),
          "aria-label": `${r.emoji} ${r.count}`, onClick: () => toggleReaction(m, r.emoji, !r.mine) },
          r.emoji, h("span", {}, r.count)))) : null);
    bubble.addEventListener("click", (e) => {            // on touch screens a tap shows the tools
      if (e.target.closest("a, button, img, video, audio")) return;
      document.querySelectorAll(".msg.show-tools").forEach((n) => { if (n !== el) n.classList.remove("show-tools"); });
      el.classList.toggle("show-tools");
    });
    return el;
  }

  function jumpTo(id) {
    const el = nodes.get(id);
    if (!el) return toast("That message is not loaded.");
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    el.classList.add("flash");
    setTimeout(() => el.classList.remove("flash"), 1400);
  }

  // ---------- actions on messages ----------
  async function toggleReaction(m, emoji, add) {
    try { upsert(await (add ? put : del)(`/api/messages/${m.id}/reactions/${encodeURIComponent(emoji)}`)); }
    catch (e) { toast(e.message, "error"); }
  }

  async function deleteMessage(m) {
    if (!(await confirmDialog("Delete message", "This message will be deleted for everybody.", "Delete", true))) return;
    try { await del(`/api/messages/${m.id}`); await poll(); onActivity(); }
    catch (e) { toast(e.message, "error"); }
  }

  function reportDialog(m) {
    const reason = h("textarea", { class: "input", rows: "3", maxlength: "300", placeholder: "What is wrong with this message? (optional)" });
    const msg = h("p", { class: "form-msg", role: "alert" });
    const form = h("form", { class: "dialog-body" },
      h("p", { class: "muted" }, "The moderators will see this message and a few messages around it."),
      reason, msg, h("div", { class: "dialog-actions" }, h("button", { class: "btn primary", type: "submit" }, "Send report")));
    const box = modal("Report message", form);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try { await post(`/api/messages/${m.id}/report`, { reason: reason.value }); box.close(); toast("Report sent. Thank you."); }
      catch (err) { msg.textContent = err.message; msg.className = "form-msg error"; }
    });
  }

  // ---------- message box ----------
  const input = h("textarea", { class: "composer-input", rows: "1", maxlength: "2000", placeholder: "Write a message", "aria-label": "Message" });
  const sendBtn = h("button", { class: "btn primary send", type: "button", "aria-label": "Send message", onClick: submit }, icon("send"));
  const fileInput = h("input", { type: "file", multiple: true, hidden: true });
  const clipBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Attach files", onClick: () => fileInput.click() }, icon("clip"));
  const emojiBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Insert emoji", onClick: () => openEmojiPicker(emojiBtn, insertText, { quick: false }) }, icon("smile"));
  const bars = h("div", { class: "composer-bars" });
  if (config.uploads && !config.uploads.enabled) clipBtn.hidden = true;

  function insertText(text) {
    const s = input.selectionStart ?? input.value.length;
    const e = input.selectionEnd ?? s;
    input.value = input.value.slice(0, s) + text + input.value.slice(e);
    input.selectionStart = input.selectionEnd = s + text.length;
    input.focus();
  }

  function drawBars() {
    const items = [];
    if (replyTo) {
      items.push(h("div", { class: "bar" }, icon("reply"),
        h("span", { class: "bar-text" }, h("strong", {}, `Replying to ${replyTo.sender_name}`), " ", (replyTo.text || "Attachment").slice(0, 80)),
        h("button", { class: "icon-btn small", type: "button", "aria-label": "Cancel reply", onClick: () => { replyTo = null; drawBars(); } }, icon("close"))));
    }
    if (editing) {
      items.push(h("div", { class: "bar" }, icon("edit"),
        h("span", { class: "bar-text" }, h("strong", {}, "Editing message")),
        h("button", { class: "icon-btn small", type: "button", "aria-label": "Cancel editing", onClick: cancelEdit }, icon("close"))));
    }
    for (const p of pending) {
      items.push(h("div", { class: `bar upload ${p.state}` }, icon("file"),
        h("span", { class: "bar-text" }, h("strong", {}, p.file.name), " ",
          p.state === "uploading" ? `${Math.round(p.progress * 100)}%` : p.state === "error" ? p.error : formatBytes(p.file.size)),
        p.state === "uploading" ? h("progress", { max: "1", value: String(p.progress) }) : null,
        h("button", { class: "icon-btn small", type: "button", "aria-label": "Remove file", onClick: () => removePending(p) }, icon("close"))));
    }
    bars.replaceChildren(...items);
  }

  function startReply(m) { editing = null; replyTo = m; drawBars(); input.focus(); }
  function startEdit(m) { replyTo = null; editing = m; input.value = m.text; drawBars(); input.focus(); }
  function cancelEdit() { editing = null; input.value = ""; drawBars(); }

  function removePending(p) {
    if (p.state === "uploading") p.handle.cancel();
    else if (p.state === "ready") p.handle.cancel();           // also removes the unused file
    pending = pending.filter((x) => x !== p);
    drawBars();
  }

  function limitFor(file) {
    const u = config.uploads || {};
    const type = file.type || "";
    return (type.startsWith("image/") ? u.max_image_mb : type.startsWith("video/") ? u.max_video_mb : u.max_file_mb) || 10;
  }

  function addFiles(files) {
    if (config.uploads && !config.uploads.enabled) return toast("Uploads are not available right now.", "error");
    for (const file of files) {
      if (pending.length >= 10) { toast("At most 10 files per message."); break; }
      if (file.size > limitFor(file) * MB) { toast(`“${file.name}” is bigger than ${limitFor(file)} MB.`, "error"); continue; }
      const item = { file, state: "uploading", progress: 0, attachment: null, error: "" };
      item.handle = uploadFile(file, { kind: "attachment", chatType: chat.type, chatKey: chat.key,
        onProgress: (p) => { item.progress = p; drawBars(); } });
      item.handle.promise
        .then((att) => { item.state = "ready"; item.attachment = att; drawBars(); })
        .catch((err) => {
          if (err.message === "Cancelled") return;
          item.state = "error"; item.error = err.message; drawBars(); toast(err.message, "error");
        });
      pending.push(item);
    }
    drawBars();
  }

  async function submit() {
    if (pending.some((p) => p.state === "uploading")) return toast("Please wait until the upload is finished.");
    const text = input.value.trim();
    sendBtn.disabled = true;
    try {
      if (editing) {
        if (!text) return;
        upsert(await patch(`/api/messages/${editing.id}`, { text }));
        cancelEdit();
        return;
      }
      const ready = pending.filter((p) => p.state === "ready");
      if (!text && !ready.length) return;
      const msg = await post(`${base}/messages`, { text, reply_to: replyTo ? replyTo.id : null, attachment_ids: ready.map((p) => p.attachment.id) });
      input.value = ""; input.style.height = "auto";
      pending = pending.filter((p) => p.state === "error");
      replyTo = null; drawBars();
      empty.hidden = true;
      upsert(msg); scrollBottom(); onActivity();
    } catch (e) { toast(e.message, "error"); }
    finally { sendBtn.disabled = false; }
  }

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
    if (e.key === "Escape") { if (editing) cancelEdit(); else if (replyTo) { replyTo = null; drawBars(); } }
  });
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px"; });
  input.addEventListener("paste", (e) => {
    const files = [...(e.clipboardData?.files || [])];
    if (files.length) { e.preventDefault(); addFiles(files); }
  });
  fileInput.addEventListener("change", () => { addFiles([...fileInput.files]); fileInput.value = ""; });

  const root = h("section", { class: "chat" }, header, messagesEl,
    h("div", { class: "composer-wrap" }, bars, h("div", { class: "composer" }, clipBtn, emojiBtn, input, sendBtn), fileInput));
  root.addEventListener("dragover", (e) => { if (e.dataTransfer?.types.includes("Files")) { e.preventDefault(); root.classList.add("dragging"); } });
  root.addEventListener("dragleave", (e) => { if (e.target === root) root.classList.remove("dragging"); });
  root.addEventListener("drop", (e) => {
    root.classList.remove("dragging");
    if (e.dataTransfer?.files?.length) { e.preventDefault(); addFiles([...e.dataTransfer.files]); }
  });

  // ---------- chat menu: background and clearing ----------
  function chatMenu() {
    const items = [
      { label: "Chat background…", onClick: backgroundDialog },
      { label: "Clear chat for me", onClick: () => clearChat("me") },
    ];
    if (canModerate) items.push({ label: "Clear chat for everyone", danger: true, onClick: () => clearChat("all") });
    return items;
  }

  async function clearChat(scope) {
    const everyone = scope === "all";
    const ok = await confirmDialog(everyone ? "Clear chat for everyone" : "Clear chat for me",
      everyone ? "All messages and files in this chat will be deleted for everybody. This can't be undone."
        : "The messages disappear for you only. The others keep them.",
      "Clear chat", true);
    if (!ok) return;
    try {
      await post(`${base}/clear`, { scope });
      [...nodes.keys()].forEach(forget);
      olderDone = false;
      await poll();
      onActivity();
    } catch (e) { toast(e.message, "error"); }
  }

  function applyBackground(value = bg.background || (bg.default ? `preset:${bg.default}` : ""), dim = bg.dim) {
    const css = backgroundCss(value, dim);
    messagesEl.style.backgroundImage = css;
    messagesEl.style.backgroundSize = css ? "cover" : "";
    messagesEl.style.backgroundPosition = "center";
    messagesEl.classList.toggle("has-bg", Boolean(css));
  }

  function backgroundDialog() {
    let value = bg.background;
    let dim = bg.dim;
    const names = config.presets || Object.keys(PRESETS);
    const swatch = (val, label, css) => {
      const b = h("button", { class: "swatch", type: "button", title: label, "aria-label": label, "aria-pressed": String(value === val),
        onClick: () => { value = val; refresh(); } }, css ? "" : "None");
      if (css) b.style.background = css;
      b.dataset.value = val;
      return b;
    };
    const grid = h("div", { class: "swatches" });
    const fileIn = h("input", { type: "file", accept: "image/*", hidden: true });
    const range = h("input", { type: "range", min: "0", max: "80", value: String(dim), "aria-label": "Dimming", onInput: () => { dim = Number(range.value); applyBackground(valueOrDefault(), dim); } });
    const msg = h("p", { class: "form-msg", role: "alert" });
    const valueOrDefault = () => value || (bg.default ? `preset:${bg.default}` : "");
    function refresh() {
      grid.replaceChildren(swatch("", "No background", ""), ...names.map((n) => swatch(`preset:${n}`, n, PRESETS[n])));
      [...grid.children].forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.value === value)));
      applyBackground(valueOrDefault(), dim);
    }
    fileIn.addEventListener("change", async () => {
      try { value = await fileToBackground(fileIn.files[0]); refresh(); }
      catch (e) { msg.textContent = e.message; msg.className = "form-msg error"; }
    });
    const form = h("form", { class: "dialog-body" },
      h("div", { class: "field-label" }, "Background (only you can see it)"), grid,
      bg.allow_custom ? h("button", { class: "btn small", type: "button", onClick: () => fileIn.click() }, icon("image"), "Use my own picture") : h("p", { class: "muted" }, "Own pictures are switched off by the admins."),
      fileIn,
      h("label", { class: "field", style: "margin-top:14px" }, h("span", { class: "field-label" }, "Dim the picture"), range),
      msg, h("div", { class: "dialog-actions" }, h("button", { class: "btn primary", type: "submit" }, "Save")));
    const box = modal("Chat background", form, () => applyBackground());      // closing without saving restores the old look
    refresh();
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const saved = await put(`${base}/settings`, { background: value, dim });
        bg = { ...bg, ...saved };
        box.close();
        applyBackground();
      } catch (err) { msg.textContent = err.message; msg.className = "form-msg error"; }
    });
  }

  async function loadSettings() {
    try { bg = await get(`${base}/settings`); applyBackground(); } catch { /* no background */ }
  }

  // ---------- start ----------
  const onVisible = () => { if (!document.hidden) { quiet = 0; poll(); } };
  document.addEventListener("visibilitychange", onVisible);
  loadSettings();
  poll();
  // "Live" updates: every 3 seconds while something happens, slower (6 s, then 10 s) while the chat is quiet.
  const next = () => { timer = setTimeout(async () => { await poll(); if (!stopped) next(); }, quiet > 20 ? 10000 : quiet > 8 ? 6000 : 3000); };
  next();
  input.addEventListener("input", () => { quiet = 0; });

  return {
    root, updateHeader,
    focus: () => input.focus(),
    destroy() {
      stopped = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
      pending.forEach((p) => { if (p.state !== "error") p.handle.cancel(); });
    },
  };
}
