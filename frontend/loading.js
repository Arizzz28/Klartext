// Loading screen: picture and music set by the admins (or by yourself, if allowed).
// Shown while the app starts, and while a sleeping server wakes up (that can take about a minute).
import { API_URL } from "./config.js";
import { getToken } from "./api.js";
import { h } from "./ui.js";

const MUTE_KEY = "chatisfying_muted";

export function startLoading() {
  const startedAt = Date.now();
  const picture = h("img", { class: "loader-picture", alt: "", hidden: true });
  const title = h("div", { class: "loader-title" }, "Chatisfying");
  const wake = h("p", { class: "loader-wake", hidden: true }, "The server is waking up. This can take up to a minute.");
  const startBtn = h("button", { class: "btn primary loader-start", type: "button", hidden: true }, "Tap to start with sound");
  const muteBtn = h("button", { class: "icon-btn loader-mute", type: "button", hidden: true, "aria-label": "Mute music" }, "🔊");
  const overlay = h("div", { class: "loader", role: "status", "aria-live": "polite" },
    picture,
    h("div", { class: "loader-brand" },
      h("img", { class: "loader-mark", src: "assets/images/logo.svg", alt: "" }),
      title, h("div", { class: "loader-sub" }, "klartext")),
    h("div", { class: "loader-bar" }, h("span")),
    wake, startBtn, muteBtn);
  document.body.append(overlay);

  let audio = null;
  let finished = false;
  const wakeTimer = setTimeout(() => { wake.hidden = false; }, 6000);

  async function loadConfig() {
    try {
      const headers = getToken() ? { Authorization: `Bearer ${getToken()}` } : {};
      const res = await fetch(`${API_URL}/api/loading`, { headers });
      if (!res.ok) return;
      const cfg = await res.json();
      if (finished) return;
      title.textContent = cfg.title || "Chatisfying";
      if (cfg.image) {
        picture.onload = () => { picture.hidden = false; overlay.classList.add("has-picture"); };
        picture.src = cfg.image;
      }
      if (cfg.music) setupMusic(cfg);
    } catch { /* the default look is fine */ }
  }

  function setupMusic(cfg) {
    audio = new Audio(cfg.music);
    audio.loop = true;
    audio.volume = Math.min(1, Math.max(0, cfg.volume ?? 0.5));
    if (cfg.can_mute) {
      muteBtn.hidden = false;
      audio.muted = localStorage.getItem(MUTE_KEY) === "1";
      muteBtn.textContent = audio.muted ? "🔇" : "🔊";
      muteBtn.onclick = () => {
        audio.muted = !audio.muted;
        localStorage.setItem(MUTE_KEY, audio.muted ? "1" : "0");
        muteBtn.textContent = audio.muted ? "🔇" : "🔊";
        muteBtn.setAttribute("aria-label", audio.muted ? "Unmute music" : "Mute music");
      };
    }
    // Browsers only allow sound after the person has clicked something. If playing is refused, ask for a tap.
    audio.play().catch(() => {
      startBtn.hidden = false;
      startBtn.onclick = () => { audio.play().catch(() => {}); startBtn.hidden = true; };
    });
  }

  loadConfig();

  return {
    // Call when the app is ready. The screen stays at least a moment so it doesn't just flash.
    done() {
      const wait = Math.max(0, 700 - (Date.now() - startedAt));
      setTimeout(() => {
        finished = true;
        clearTimeout(wakeTimer);
        overlay.classList.add("hide");
        if (audio) {                                       // fade the music out
          const fade = setInterval(() => {
            audio.volume = Math.max(0, audio.volume - 0.08);
            if (audio.volume <= 0.01) { clearInterval(fade); audio.pause(); audio = null; }
          }, 60);
        }
        setTimeout(() => overlay.remove(), 700);
      }, wait);
    },
  };
}
