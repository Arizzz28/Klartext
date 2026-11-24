// Emoji list and the small picker pop-up (used for reactions and in the message box).
import { h, icon } from "./ui.js";

export const QUICK = ["👍", "❤️", "😂", "😮", "😢", "🙏"];

const GROUPS = [
  ["😀", "Smileys", "😀 😃 😄 😁 😆 😅 😂 🤣 😊 😇 🙂 🙃 😉 😌 😍 🥰 😘 😋 😛 😜 🤪 😎 🤩 🥳 😏 😒 😞 😔 😟 😕 🙁 😣 😖 😫 😩 🥺 😢 😭 😤 😠 😡 🤯 😳 🥵 🥶 😱 😨 😰 😥 😓 🤗 🤔 🤭 🤫 😶 😐 😑 😬 🙄 😯 😦 😮 😲 🥱 😴 🤤 😪 😵 🤐 🥴 🤢 🤮 🤧 😷 🤒 🤕"],
  ["👍", "Hands", "👍 👎 👌 ✌️ 🤞 🤟 🤘 🤙 👈 👉 👆 👇 ☝️ ✋ 🤚 🖐️ 🖖 👋 🤝 👏 🙌 👐 🤲 🙏 ✍️ 💪 🫶"],
  ["❤️", "Hearts & symbols", "❤️ 🧡 💛 💚 💙 💜 🖤 🤍 💔 ❣️ 💕 💞 💓 💗 💖 💘 💝 ✨ ⭐ 🌟 💫 🔥 💥 💯 ✅ ❌ ❓ ❗ 💤 🎉 🎊 🎁 🏆 🥇"],
  ["🐶", "Animals", "🐶 🐱 🐭 🐹 🐰 🦊 🐻 🐼 🐨 🐯 🦁 🐮 🐷 🐸 🐵 🙈 🙉 🙊 🐔 🐧 🐦 🦄 🐝 🦋 🐢 🐙 🐬 🐳"],
  ["🍕", "Food", "🍎 🍌 🍉 🍓 🍒 🍑 🥑 🍅 🌽 🥕 🍞 🧀 🍳 🥓 🍔 🍟 🍕 🌭 🌮 🍣 🍜 🍩 🍪 🎂 🍫 🍿 ☕ 🍵 🥤 🍺"],
  ["⚽", "Activities", "⚽ 🏀 🏈 🎾 🏐 🎱 🏓 🥊 🎮 🎲 🎯 🎸 🎹 🎧 🎤 🎬 📚 ✏️ 💻 📱 🚗 ✈️ 🚀 🌍 🌈 ☀️ 🌙 ⛄ 🌊"],
];

export function openEmojiPicker(anchor, onPick, { quick = true } = {}) {
  document.querySelector(".emoji-picker")?.remove();
  const close = () => { box.remove(); document.removeEventListener("pointerdown", outside, true); document.removeEventListener("keydown", onKey); };
  const outside = (e) => { if (!box.contains(e.target) && e.target !== anchor) close(); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  const pick = (emoji) => { close(); onPick(emoji); };

  const grid = h("div", { class: "emoji-grid" });
  const tabs = h("div", { class: "emoji-tabs" });
  function show(index) {
    grid.replaceChildren(...GROUPS[index][2].split(" ").map((e) =>
      h("button", { class: "emoji-btn", type: "button", "aria-label": e, onClick: () => pick(e) }, e)));
    [...tabs.children].forEach((t, i) => t.classList.toggle("active", i === index));
  }
  GROUPS.forEach(([symbol, name], i) => tabs.append(
    h("button", { class: "emoji-tab", type: "button", title: name, "aria-label": name, onClick: () => show(i) }, symbol)));

  const box = h("div", { class: "emoji-picker", role: "dialog", "aria-label": "Choose an emoji" },
    quick ? h("div", { class: "emoji-quick" }, QUICK.map((e) => h("button", { class: "emoji-btn big", type: "button", "aria-label": e, onClick: () => pick(e) }, e))) : null,
    tabs, grid);
  document.body.append(box);
  show(0);
  const r = anchor.getBoundingClientRect();
  const left = Math.min(Math.max(8, r.left), window.innerWidth - box.offsetWidth - 8);
  const top = r.top - box.offsetHeight - 8 > 8 ? r.top - box.offsetHeight - 8 : Math.min(r.bottom + 8, window.innerHeight - box.offsetHeight - 8);
  box.style.left = left + "px";
  box.style.top = Math.max(8, top) + "px";
  setTimeout(() => { document.addEventListener("pointerdown", outside, true); document.addEventListener("keydown", onKey); });
  return close;
}
