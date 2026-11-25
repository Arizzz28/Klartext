// Games. Each game is its own permission; the Owner decides which rank gets which game.
// The games run in your browser; only your best score is sent to the server (leaderboard).
import { get, post } from "../api.js";
import { emptyState, h, toast } from "../ui.js";

export const usesList = false;

export async function render({ main }) {
  const page = h("div", { class: "page wide" }, h("h1", {}, "Games"));
  const stage = h("section", { class: "card", hidden: true });
  const grid = h("div", { class: "stats" });
  page.append(grid, stage);
  main.append(page);
  let games = [];

  async function load() {
    games = await get("/api/games");
    grid.replaceChildren(...games.map((g) => h("div", { class: "stat" }, h("strong", {}, g.name), h("span", {}, g.text),
      h("small", {}, g.allowed ? (g.my_plays ? `Your best: ${g.my_best} · played ${g.my_plays}×` : "Not played yet") : "Not included in your rank"),
      h("button", { class: "btn small primary", type: "button", disabled: !g.allowed, onClick: () => play(g) }, g.allowed ? "Play" : "Locked"))));
  }

  async function finish(game, score, label) {
    try { const r = await post(`/api/games/${game.id}/score`, { score }); toast(`${label} Best: ${r.best}`); await load(); } catch (e) { toast(e.message, "error"); }
  }

  async function board(game) {
    const lb = await get(`/api/games/${game.id}/leaderboard`).catch(() => ({ rows: [] }));
    return h("div", {}, h("h3", {}, "Top 10"), lb.rows.length ? h("ol", {}, lb.rows.map((r) => h("li", {}, `${r.username} – ${r.best}`))) : h("p", { class: "muted" }, "No scores yet."));
  }

  async function play(game) {
    stage.hidden = false;
    const area = h("div");
    stage.replaceChildren(h("h2", {}, game.name), area, await board(game));
    ({ tictactoe, guess, memory })[game.id](area, game);
    stage.scrollIntoView?.({ behavior: "smooth" });
  }

  // ---- Tic-Tac-Toe against the computer (score = number of wins)
  function tictactoe(area, game) {
    const lines = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [0, 3, 6], [1, 4, 7], [2, 5, 8], [0, 4, 8], [2, 4, 6]];
    const winner = (b) => { for (const [a, c, d] of lines) if (b[a] && b[a] === b[c] && b[a] === b[d]) return b[a]; return b.every(Boolean) ? "draw" : null; };
    function minimax(b, turn) {
      const w = winner(b);
      if (w === "O") return { s: 1 }; if (w === "X") return { s: -1 }; if (w === "draw") return { s: 0 };
      let best = { s: turn === "O" ? -2 : 2 };
      b.forEach((cell, i) => { if (cell) return; b[i] = turn; const r = minimax(b, turn === "O" ? "X" : "O"); b[i] = null; if (turn === "O" ? r.s > best.s : r.s < best.s) best = { s: r.s, i }; });
      return best;
    }
    let b = Array(9).fill(null), over = false;
    const status = h("p", { class: "muted" }, "You are X. Your move.");
    const cells = b.map((_, i) => h("button", { class: "ttt-cell", type: "button", "aria-label": `Cell ${i + 1}`, onClick: () => click(i) }));
    const reset = () => { b = Array(9).fill(null); over = false; cells.forEach((c) => { c.textContent = ""; c.disabled = false; }); status.textContent = "You are X. Your move."; };
    function show() { b.forEach((v, i) => { cells[i].textContent = v || ""; cells[i].disabled = Boolean(v) || over; }); }
    function end(w) {
      over = true; show();
      status.textContent = w === "X" ? "You win! 🎉" : w === "O" ? "The computer wins." : "A draw.";
      if (w === "X") finish(game, 1 + (games.find((g) => g.id === "tictactoe")?.my_best || 0), "You won!");
    }
    function click(i) {
      if (b[i] || over) return;
      b[i] = "X"; let w = winner(b); if (w) return end(w);
      // The computer plays perfectly, except one move in four is random - otherwise nobody could ever win.
      const free = b.map((v, k) => (v ? -1 : k)).filter((k) => k >= 0);
      const m = Math.random() < 0.25 ? { i: free[Math.floor(Math.random() * free.length)] } : minimax(b, "O");
      if (m.i !== undefined) b[m.i] = "O";
      w = winner(b); if (w) return end(w); show();
    }
    area.append(status, h("div", { class: "ttt" }, cells), h("button", { class: "btn small", type: "button", onClick: reset }, "New round"),
      h("p", { class: "muted" }, "Each win adds 1 to your score."));
  }

  // ---- Number guess (score = tries, fewer is better)
  function guess(area, game) {
    let secret = 1 + Math.floor(Math.random() * 100), tries = 0;
    const input = h("input", { class: "input", type: "number", min: "1", max: "100", inputmode: "numeric", "aria-label": "Your guess" });
    const hint = h("p", {}, "I am thinking of a number from 1 to 100.");
    area.append(hint, h("form", { class: "inline-form", onSubmit: (e) => {
      e.preventDefault();
      const n = Number(input.value); if (!n) return;
      tries++; input.value = "";
      if (n === secret) { hint.textContent = `Correct! ${tries} tries.`; finish(game, tries, `Solved in ${tries} tries.`); secret = 1 + Math.floor(Math.random() * 100); tries = 0; }
      else hint.textContent = n < secret ? `Higher than ${n}. (Tries: ${tries})` : `Lower than ${n}. (Tries: ${tries})`;
    } }, input, h("button", { class: "btn primary", type: "submit" }, "Guess")));
  }

  // ---- Memory (score = moves, fewer is better)
  function memory(area, game) {
    const symbols = ["🍎", "🚀", "🎸", "🐙", "🌵", "🍕", "⚽", "🎲"];
    const deck = [...symbols, ...symbols].sort(() => Math.random() - 0.5);
    let open = [], moves = 0, found = 0, lock = false;
    const info = h("p", {}, "Moves: 0");
    const cards = deck.map((s, i) => h("button", { class: "mem-card", type: "button", "aria-label": `Card ${i + 1}`, onClick: () => flip(i) }, "?"));
    function flip(i) {
      if (lock || open.includes(i) || cards[i].classList.contains("found")) return;
      cards[i].textContent = deck[i]; open.push(i);
      if (open.length < 2) return;
      moves++; info.textContent = `Moves: ${moves}`;
      const [a, b] = open; open = [];
      if (deck[a] === deck[b]) { cards[a].classList.add("found"); cards[b].classList.add("found"); found++; if (found === symbols.length) finish(game, moves, `Finished in ${moves} moves.`); }
      else { lock = true; setTimeout(() => { cards[a].textContent = "?"; cards[b].textContent = "?"; lock = false; }, 700); }
    }
    area.append(info, h("div", { class: "mem" }, cards));
  }
  await load();
}
