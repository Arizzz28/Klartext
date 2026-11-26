// Single-player games. They run in YOUR browser; only the final score goes to the server, which rejects impossible values
// (see "limits" in backend/games.py). Each game is a function (area, finish): "area" is the box to draw into,
// finish(score, label) sends the score. To add a game: write the function here, add it to SOLO, and add one entry in backend/games.py.
import { h } from "../ui.js";

// ---------------------------------------------------------------- Reaction (score = milliseconds, lower is better)
function reaction(area, finish) {
  const box = h("button", { class: "react-box wait", type: "button" }, "Click to start");
  let state = "idle", t0 = 0, timer = null;
  const info = h("p", { class: "muted" }, "Wait for green, then click as fast as you can. Clicking too early fails the round.");
  box.addEventListener("pointerdown", () => {
    if (state === "idle") {
      state = "wait"; box.className = "react-box wait"; box.textContent = "Wait for green…";
      timer = setTimeout(() => { state = "go"; t0 = performance.now(); box.className = "react-box go"; box.textContent = "CLICK!"; }, 1000 + Math.random() * 3000);
    } else if (state === "wait") {
      clearTimeout(timer); state = "idle"; box.className = "react-box bad"; box.textContent = "Too early! Click to try again.";
    } else if (state === "go") {
      const ms = Math.round(performance.now() - t0);
      state = "idle"; box.className = "react-box wait"; box.textContent = `${ms} ms – click to play again`;
      finish(ms, `${ms} ms.`);
    }
  });
  area.append(info, box);
}

// ---------------------------------------------------------------- Aim trainer (score = hits in 30 seconds)
function aim(area, finish) {
  const field = h("div", { class: "aim-field" });
  const info = h("p", {}, "Press Start, then hit the targets for 30 seconds.");
  const start = h("button", { class: "btn primary", type: "button" }, "Start");
  let hits = 0, running = false, end = 0, tick = null;
  function spawn() {
    field.replaceChildren();
    if (!running) return;
    const t = h("button", { class: "aim-target", type: "button", "aria-label": "Target" });
    t.style.left = `${5 + Math.random() * 82}%`; t.style.top = `${5 + Math.random() * 80}%`;
    t.addEventListener("pointerdown", (e) => { e.preventDefault(); hits++; spawn(); });
    field.append(t);
  }
  start.addEventListener("click", () => {
    hits = 0; running = true; end = performance.now() + 30000; spawn(); start.disabled = true;
    tick = setInterval(() => {
      const left = Math.max(0, end - performance.now());
      info.textContent = `Hits: ${hits} · ${Math.ceil(left / 1000)} s left`;
      if (left <= 0) { clearInterval(tick); running = false; start.disabled = false; spawn(); info.textContent = `Done! ${hits} hits.`; finish(hits, `${hits} hits.`); }
    }, 100);
  });
  area.append(info, start, field);
}

// ---------------------------------------------------------------- Number guess (score = tries, fewer is better)
function guess(area, finish) {
  let secret = 1 + Math.floor(Math.random() * 100), tries = 0;
  const input = h("input", { class: "input", type: "number", min: "1", max: "100", inputmode: "numeric", "aria-label": "Your guess" });
  const hint = h("p", {}, "I am thinking of a number from 1 to 100.");
  area.append(hint, h("form", { class: "inline-form", onSubmit: (e) => {
    e.preventDefault();
    const n = Number(input.value); if (!n) return;
    tries++; input.value = "";
    if (n === secret) { hint.textContent = `Correct! ${tries} tries.`; finish(tries, `Solved in ${tries} tries.`); secret = 1 + Math.floor(Math.random() * 100); tries = 0; }
    else hint.textContent = n < secret ? `Higher than ${n}. (Tries: ${tries})` : `Lower than ${n}. (Tries: ${tries})`;
  } }, input, h("button", { class: "btn primary", type: "submit" }, "Guess")));
}

// ---------------------------------------------------------------- A small 3D engine ("raycasting", like the first 3D shooters)
// How it works: for every column of the screen we shoot a ray from the player into the map, see which wall it hits and how far away,
// and draw a vertical bar - the farther the wall, the shorter and darker the bar. No 3D library needed.
function engine(area, map, start, { onFrame, onKey, hud, buttons }) {
  const W = 480, H = 300;
  const canvas = h("canvas", { class: "ray-canvas", width: W, height: H, tabindex: "0", "aria-label": "3D view" });
  const ctx = canvas.getContext("2d");
  const p = { x: start.x, y: start.y, a: start.a || 0 };
  const keys = {};
  const down = (e) => { keys[e.key.toLowerCase()] = true; if ([" ", "arrowup", "arrowdown", "arrowleft", "arrowright"].includes(e.key.toLowerCase())) e.preventDefault(); onKey?.(e.key.toLowerCase()); };
  const up = (e) => { keys[e.key.toLowerCase()] = false; };
  window.addEventListener("keydown", down); window.addEventListener("keyup", up);
  const solid = (x, y) => { const v = map[Math.floor(y)]?.[Math.floor(x)]; return v === undefined || v === 1; };
  const zbuf = new Array(W).fill(0);
  let last = performance.now(), alive = true;
  function frame(now) {
    if (!alive || !canvas.isConnected) { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); return; }
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    const turn = (keys["arrowleft"] || keys["a"] || keys.tl ? -1 : 0) + (keys["arrowright"] || keys["d"] || keys.tr ? 1 : 0);
    const move = (keys["arrowup"] || keys["w"] || keys.fw ? 1 : 0) - (keys["arrowdown"] || keys["s"] || keys.bw ? 1 : 0);
    p.a += turn * 2.4 * dt;
    const nx = p.x + Math.cos(p.a) * move * 2.6 * dt, ny = p.y + Math.sin(p.a) * move * 2.6 * dt;
    if (!solid(nx, p.y)) p.x = nx;
    if (!solid(p.x, ny)) p.y = ny;
    ctx.fillStyle = "#2a2f3f"; ctx.fillRect(0, 0, W, H / 2);
    ctx.fillStyle = "#3b3b3b"; ctx.fillRect(0, H / 2, W, H / 2);
    const fov = Math.PI / 3;
    for (let x = 0; x < W; x++) {
      const ra = p.a - fov / 2 + (x / W) * fov, dx = Math.cos(ra), dy = Math.sin(ra);
      let d = 0;
      while (d < 20) { d += 0.04; if (solid(p.x + dx * d, p.y + dy * d)) break; }
      zbuf[x] = d;
      const dist = d * Math.cos(ra - p.a), hgt = Math.min(H, H / Math.max(dist, 0.1));
      const shade = Math.max(40, 230 - dist * 22) | 0;
      ctx.fillStyle = `rgb(${shade},${(shade * 0.7) | 0},${(shade * 0.5) | 0})`;
      ctx.fillRect(x, (H - hgt) / 2, 1, hgt);
    }
    onFrame?.(ctx, p, zbuf, dt, { W, H, fov });
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  const pad = h("div", { class: "pad" }, buttons.map(([label, key]) => {
    const b = h("button", { class: "btn", type: "button" }, label);
    const on = (e) => { e.preventDefault(); keys[key] = true; if (key === "fire") onKey?.(" "); }, off = () => { keys[key] = false; };
    b.addEventListener("pointerdown", on); b.addEventListener("pointerup", off); b.addEventListener("pointerleave", off); b.addEventListener("pointercancel", off);
    return b;
  }));
  area.append(hud, canvas, pad);
  return { p, stop: () => { alive = false; }, canvas };
}

// ---------------------------------------------------------------- 3D maze (score = seconds to the exit, fewer is better)
function maze3d(area, finish) {
  const N = 9, size = N * 2 + 1;                         // N x N rooms; walls are cells in a (2N+1) grid
  const map = Array.from({ length: size }, () => Array(size).fill(1));
  const stack = [[1, 1]]; map[1][1] = 0;
  while (stack.length) {                                  // "depth-first search" digs a maze with exactly one way between any two rooms
    const [x, y] = stack[stack.length - 1];
    const opts = [[2, 0], [-2, 0], [0, 2], [0, -2]].filter(([dx, dy]) => map[y + dy]?.[x + dx] === 1 && y + dy > 0 && x + dx > 0 && y + dy < size - 1 && x + dx < size - 1);
    if (!opts.length) { stack.pop(); continue; }
    const [dx, dy] = opts[Math.floor(Math.random() * opts.length)];
    map[y + dy / 2][x + dx / 2] = 0; map[y + dy][x + dx] = 0; stack.push([x + dx, y + dy]);
  }
  const exit = { x: size - 2 + 0.5, y: size - 2 + 0.5 };
  const hud = h("p", {}, "Find the glowing exit (bottom right). Arrow keys / WASD, or the buttons."), t0 = performance.now();
  let done = false;
  const g = engine(area, map, { x: 1.5, y: 1.5, a: 0 }, {
    hud, buttons: [["⟲", "tl"], ["▲", "fw"], ["▼", "bw"], ["⟳", "tr"]],
    onFrame(ctx, p, z, dt, { W, H }) {
      const secs = Math.round((performance.now() - t0) / 1000);
      if (!done) hud.textContent = `Time: ${secs} s · find the glowing exit (bottom right).`;
      const dx = exit.x - p.x, dy = exit.y - p.y, dist = Math.hypot(dx, dy);
      let rel = Math.atan2(dy, dx) - p.a; rel = Math.atan2(Math.sin(rel), Math.cos(rel));
      if (Math.abs(rel) < Math.PI / 3 / 2 + 0.2) {
        const sx = W / 2 + (rel / (Math.PI / 3)) * W, s = Math.min(H, H / dist) * 0.6;
        const col = Math.max(0, Math.min(W - 1, sx | 0));
        if (z[col] > dist - 0.2) { ctx.fillStyle = "rgba(80,255,160,0.85)"; ctx.fillRect(sx - s / 4, H / 2 - s / 2, s / 2, s); }
      }
      if (!done && dist < 0.6) { done = true; g.stop(); hud.textContent = `You made it in ${secs} s!`; finish(Math.max(secs, 5), `${secs} s.`); }
    },
  });
}

// ---------------------------------------------------------------- Shooter (score = enemies hit before you are caught)
function shooter(area, finish) {
  const size = 14;
  const map = Array.from({ length: size }, (_, y) => Array.from({ length: size }, (_, x) => (x === 0 || y === 0 || x === size - 1 || y === size - 1 ? 1 : 0)));
  [[4, 4], [9, 4], [4, 9], [9, 9], [6, 6], [7, 7]].forEach(([x, y]) => { map[y][x] = 1; });
  let kills = 0, hp = 100, over = false, cooldown = 0, flash = 0, spawnT = 0;
  const enemies = [];
  const hud = h("p", {}, "Shoot the red enemies before they reach you! Space / the ● button fires.");
  const free = () => { for (let k = 0; k < 40; k++) { const x = 1 + Math.random() * (size - 2), y = 1 + Math.random() * (size - 2); if (map[y | 0][x | 0] === 0) return { x, y }; } return { x: 1.5, y: 1.5 }; };
  const g = engine(area, map, { x: 2, y: 2, a: 0.8 }, {
    hud, buttons: [["⟲", "tl"], ["▲", "fw"], ["▼", "bw"], ["⟳", "tr"], ["●", "fire"]],
    onKey(k) { if (k === " " && !over) fire(); },
    onFrame(ctx, p, z, dt, { W, H, fov }) {
      if (over) return;
      cooldown -= dt; flash -= dt; spawnT -= dt;
      if (spawnT <= 0 && enemies.length < 4 + Math.min(4, kills >> 2)) { const e = free(); if (Math.hypot(e.x - p.x, e.y - p.y) > 4) enemies.push(e); spawnT = Math.max(0.7, 2 - kills * 0.05); }
      for (const e of enemies) {                          // enemies walk straight towards you
        const dx = p.x - e.x, dy = p.y - e.y, d = Math.hypot(dx, dy) || 1, sp = (0.7 + Math.min(kills, 20) * 0.03) * dt;
        const nx = e.x + (dx / d) * sp, ny = e.y + (dy / d) * sp;
        if (map[e.y | 0][nx | 0] === 0) e.x = nx;
        if (map[ny | 0][e.x | 0] === 0) e.y = ny;
        if (d < 0.7) { hp -= 25 * dt * 4; }
      }
      enemies.sort((a, b) => Math.hypot(b.x - p.x, b.y - p.y) - Math.hypot(a.x - p.x, a.y - p.y));
      for (const e of enemies) {                          // draw far to near, hidden by walls
        const dx = e.x - p.x, dy = e.y - p.y, dist = Math.hypot(dx, dy);
        let rel = Math.atan2(dy, dx) - p.a; rel = Math.atan2(Math.sin(rel), Math.cos(rel));
        if (Math.abs(rel) > fov / 2 + 0.3) continue;
        const sx = W / 2 + (rel / fov) * W, s = Math.min(H, H / dist) * 0.8, col = Math.max(0, Math.min(W - 1, sx | 0));
        if (z[col] < dist) continue;
        ctx.fillStyle = "#e23b3b"; ctx.fillRect(sx - s / 4, H / 2 - s / 2, s / 2, s);
        ctx.fillStyle = "#fff"; ctx.fillRect(sx - s / 8, H / 2 - s / 3, s / 12, s / 12); ctx.fillRect(sx + s / 16, H / 2 - s / 3, s / 12, s / 12);
      }
      ctx.strokeStyle = "#fff"; ctx.beginPath(); ctx.moveTo(W / 2 - 8, H / 2); ctx.lineTo(W / 2 + 8, H / 2); ctx.moveTo(W / 2, H / 2 - 8); ctx.lineTo(W / 2, H / 2 + 8); ctx.stroke();
      if (flash > 0) { ctx.fillStyle = "rgba(255,255,200,0.25)"; ctx.fillRect(0, 0, W, H); }
      hud.textContent = `Hits: ${kills} · Health: ${Math.max(0, Math.round(hp))}`;
      if (hp <= 0) { over = true; g.stop(); hud.textContent = `Game over – ${kills} hits.`; finish(Math.min(kills, 400), `${kills} hits.`); }
    },
  });
  function fire() {
    if (cooldown > 0) return;
    cooldown = 0.25; flash = 0.06;
    const p = g.p; let best = -1, bd = 99;
    enemies.forEach((e, i) => {                          // the shot hits the nearest enemy that is roughly in the middle of the view
      const dx = e.x - p.x, dy = e.y - p.y, dist = Math.hypot(dx, dy);
      let rel = Math.atan2(dy, dx) - p.a; rel = Math.atan2(Math.sin(rel), Math.cos(rel));
      if (Math.abs(rel) < Math.atan(0.35 / dist) + 0.03 && dist < bd) { bd = dist; best = i; }
    });
    if (best >= 0) { enemies.splice(best, 1); kills++; }
  }
}

export const SOLO = { reaction, aim, guess, maze3d, shooter };
