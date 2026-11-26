// Prank tab. Pranks only reach people who switched "Allow pranks" on for themselves (default: off), and every prank has a Close button.
// The jumpscare face is drawn here with simple shapes - an ORIGINAL design, not a character from a game or film.
import { get, post, put } from "../api.js";
import { h, toast } from "../ui.js";

export const usesList = false;

// ---- shown on the receiver's screen (also started from app.js when the inbox has something)
export function showPrank(kind, from) {
  const layer = h("div", { class: "prank-layer", role: "dialog", "aria-label": "Prank" });
  const close = h("button", { class: "btn prank-close", type: "button", onClick: () => layer.remove() }, "Close ✕");
  const note = h("p", { class: "prank-from" }, `A prank from ${from}`);
  if (kind === "jumpscare") {
    const c = h("canvas", { width: 360, height: 360, class: "prank-face" });
    const x = c.getContext("2d");
    x.fillStyle = "#120a0a"; x.fillRect(0, 0, 360, 360);
    x.fillStyle = "#5b3b2a"; x.beginPath(); x.ellipse(180, 190, 130, 150, 0, 0, 7); x.fill();           // head
    x.fillStyle = "#e6e6c8"; [[130, 150], [230, 150]].forEach(([cx, cy]) => { x.beginPath(); x.arc(cx, cy, 38, 0, 7); x.fill(); });   // eyes
    x.fillStyle = "#000"; [[130, 150], [230, 150]].forEach(([cx, cy]) => { x.beginPath(); x.arc(cx, cy, 12, 0, 7); x.fill(); });
    x.fillStyle = "#000"; x.beginPath(); x.ellipse(180, 270, 70, 50, 0, 0, 7); x.fill();                 // open mouth
    x.fillStyle = "#fff"; for (let i = 0; i < 7; i++) { x.beginPath(); x.moveTo(125 + i * 18, 240); x.lineTo(134 + i * 18, 262); x.lineTo(143 + i * 18, 240); x.fill(); }
    layer.append(note, c, close);
    layer.classList.add("scare");
    try { const a = new AudioContext(), o = a.createOscillator(), gn = a.createGain(); o.type = "sawtooth"; o.frequency.value = 110; gn.gain.value = 0.15; o.connect(gn); gn.connect(a.destination); o.start(); o.stop(a.currentTime + 0.6); } catch { /* no sound is fine */ }
    setTimeout(() => layer.remove(), 4000);
  } else if (kind === "message") {
    layer.append(note, h("div", { class: "prank-big" }, "🎉 YOU HAVE BEEN PRANKED 🎉"), close);
    setTimeout(() => layer.remove(), 6000);
  } else if (kind === "confetti") {
    layer.classList.add("confetti");
    for (let i = 0; i < 60; i++) { const p = h("span", { class: "conf" }); p.style.left = `${Math.random() * 100}%`; p.style.background = `hsl(${Math.random() * 360},80%,60%)`; p.style.animationDelay = `${Math.random() * 1.5}s`; layer.append(p); }
    layer.append(note, close);
    setTimeout(() => layer.remove(), 5000);
  } else {
    document.body.classList.add("prank-shake");
    setTimeout(() => document.body.classList.remove("prank-shake"), 1800);
    layer.classList.add("transparent"); layer.append(note, close);
    setTimeout(() => layer.remove(), 2500);
  }
  document.body.append(layer);
}

// ---- the tab
export async function render({ main, state }) {
  const info = await get("/api/prank");
  const page = h("div", { class: "page" }, h("h1", {}, "Pranks"));
  const on = h("input", { type: "checkbox", checked: info.enabled, id: "prank-on" });
  on.addEventListener("change", async () => { try { await put("/api/prank/optin", { enabled: on.checked }); toast(on.checked ? "Pranks allowed." : "Pranks switched off."); } catch (e) { toast(e.message, "error"); on.checked = !on.checked; } });
  page.append(h("section", { class: "card" }, h("h2", {}, "Your setting"),
    h("label", { class: "check", for: "prank-on" }, on, " Allow friends with the Prank permission to send me pranks"),
    h("p", { class: "muted" }, "Off by default. Pranks are short and always have a Close button. Warning: the jumpscare shows a sudden face and a short loud sound – not for everybody. Switch it off any time.")));
  if (info.can_send) {
    const targets = await get("/api/prank/targets");
    const who = h("select", { class: "input", "aria-label": "Who" }, targets.map((t) => h("option", { value: t.username }, t.display_name)));
    const kind = h("select", { class: "input", "aria-label": "Which prank" }, Object.entries(info.kinds).map(([k, v]) => h("option", { value: k }, v)));
    page.append(h("section", { class: "card" }, h("h2", {}, "Send a prank"),
      targets.length ? h("div", { class: "grow" }, who, kind, h("button", { class: "btn primary", type: "button", onClick: async () => { try { const r = await post("/api/prank/send", { to: who.value, kind: kind.value }); toast(r.message); } catch (e) { toast(e.message, "error"); } } }, "Send"),
        h("button", { class: "btn", type: "button", onClick: () => showPrank(kind.value, "yourself (test)") }, "Test on myself"))
        : h("p", { class: "muted" }, "Nobody has allowed pranks yet. Only people who switched it on appear here."),
      h("p", { class: "muted" }, "Limits: one prank per person every 5 minutes, ten per hour. Admins can see who sent what.")));
  }
  main.append(page);
}
