// Games: lobby, unlock order, challenges, boards. The RULES run on the server (backend/gamelogic.py);
// this file only draws the boards and sends your moves. Solo games (reaction, aim, 3D) are in games_solo.js.
// HOW TO CHANGE THINGS (without asking anybody): see README.md -> "Changing games yourself".
import { get, post } from "../api.js";
import { emptyState, h, toast } from "../ui.js";
import { SOLO } from "./games_solo.js";

export const usesList = false;
const LEVELS = [["easy", "Easy (random)"], ["medium", "Medium"], ["hard", "Hard"], ["impossible", "Impossible"]];
const PIECES = { K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘", P: "♙", k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };

export async function render({ main, state }) {
  const page = h("div", { class: "page wide" }, h("h1", {}, "Games"));
  const lobby = h("div"), stage = h("section", { class: "card", hidden: true });
  page.append(lobby, stage);
  main.append(page);
  let timer = null;
  const stopPolling = () => { clearInterval(timer); timer = null; };
  window.addEventListener("hashchange", stopPolling, { once: true });

  async function loadLobby() {
    stopPolling();
    stage.hidden = true;
    lobby.hidden = false;
    const [info, mine] = await Promise.all([get("/api/games"), get("/api/matches").catch(() => ({ matches: [] }))]);
    const parts = [];
    if (!info.enabled) parts.push(h("p", { class: "banner" }, "Games are switched off by the admins right now."));
    const open = mine.matches.filter((m) => m.status === "invited" || m.status === "playing");
    if (open.length) {
      parts.push(h("h2", {}, "Your games"), h("div", { class: "stats" }, open.map((m) => {
        const mineInvite = m.status === "invited" && m.p1 === state.me.username;
        return h("div", { class: "stat" }, h("strong", {}, nameOf(info, m.game)), h("span", {}, m.names.join(" vs ")),
          h("small", {}, m.status === "invited" ? (mineInvite ? "Invited you" : "Waiting for an answer") : "Running"),
          mineInvite
            ? h("div", { class: "grow" }, h("button", { class: "btn small primary", type: "button", onClick: async () => { await post(`/api/matches/${m.id}/accept`).catch((e) => toast(e.message, "error")); openMatch(m.id, info); } }, "Accept"),
              h("button", { class: "btn small", type: "button", onClick: async () => { await post(`/api/matches/${m.id}/decline`); loadLobby(); } }, "Decline"))
            : h("button", { class: "btn small primary", type: "button", disabled: m.status === "invited", onClick: () => openMatch(m.id, info) }, "Open"));
      })));
    }
    parts.push(h("h2", {}, "All games"),
      info.sequential ? h("p", { class: "muted" }, "Games unlock one after the other: collect points in a game to open the next one. Winning, and especially good runs, give points.") : null,
      h("div", { class: "stats" }, info.games.map((g) => h("div", { class: "stat" }, h("strong", {}, `${g.unlocked ? "" : "🔒 "}${g.name}`), h("span", {}, g.text),
        h("small", {}, !g.allowed ? g.locked_reason : !g.unlocked ? g.locked_reason : `Points: ${g.points}${g.elo ? ` · Elo ${g.elo}` : ""}${g.my_plays ? ` · best ${g.my_best}` : ""}`),
        h("button", { class: "btn small primary", type: "button", disabled: !g.unlocked || !info.enabled, onClick: () => openGame(g, info) }, g.unlocked ? "Play" : "Locked")))));
    lobby.replaceChildren(...parts.filter(Boolean));
  }
  const nameOf = (info, id) => info.games.find((g) => g.id === id)?.name || id;

  async function leaderboard(g) {
    const lb = await get(`/api/games/${g.id}/leaderboard`).catch(() => ({ rows: [], elo: [] }));
    return h("div", {}, h("h3", {}, "Top 10"),
      lb.rows.length ? h("ol", {}, lb.rows.map((r) => h("li", {}, `${r.username} – ${r.best}`))) : g.kind === "solo" ? h("p", { class: "muted" }, "No scores yet.") : null,
      lb.elo.length ? h("div", {}, h("h4", {}, "Elo (games between people)"), h("ol", {}, lb.elo.map((r) => h("li", {}, `${r.username} – ${r.rating} (${r.games} games)`)))) : null);
  }

  async function openGame(g, info) {
    stopPolling();
    lobby.hidden = true; stage.hidden = false;
    const area = h("div");
    const back = h("button", { class: "btn small", type: "button", onClick: loadLobby }, "← Back to games");
    stage.replaceChildren(back, h("h2", {}, g.name), area);
    if (g.kind === "solo") {
      const finish = async (score, label) => { try { const r = await post(`/api/games/${g.id}/score`, { score }); toast(`${label} Best: ${r.best} (+${r.points_earned} points)`); } catch (e) { toast(e.message, "error"); } };
      SOLO[g.id](area, finish);
    } else await launcher(area, g, info);
    stage.append(await leaderboard(g));
  }

  async function launcher(area, g, info) {
    const level = h("select", { class: "input", "aria-label": "Level" }, LEVELS.map(([v, t]) => h("option", { value: v }, t)));
    const users = await get("/api/users").catch(() => []);
    const friend = h("select", { class: "input", "aria-label": "Friend" }, users.map((u) => h("option", { value: u.username }, u.display_name)));
    const start = async (opponent) => {
      try { const m = await post("/api/matches", { game: g.id, opponent, level: level.value }); openMatch(m.id, info); } catch (e) { toast(e.message, "error"); }
    };
    area.append(h("p", { class: "muted" }, g.text),
      h("h3", {}, "Play against the computer"), h("div", { class: "grow" }, level, h("button", { class: "btn primary", type: "button", onClick: () => start("bot") }, "Start")),
      ["memory", "wordle", "typing"].includes(g.id) ? h("div", {}, h("h3", {}, "Play alone"), h("button", { class: "btn", type: "button", onClick: () => start("solo") }, "Start alone")) : null,
      h("h3", {}, "Challenge a person"),
      users.length ? h("div", { class: "grow" }, friend, h("button", { class: "btn", type: "button", onClick: () => start(friend.value) }, "Send challenge")) : h("p", { class: "muted" }, "Nobody else to challenge yet."),
      h("p", { class: "muted" }, "Games between two people change your Elo number (a skill rating: it goes up when you beat someone, more so if they are better than you)."));
  }

  async function openMatch(id, info) {
    stopPolling();
    lobby.hidden = true; stage.hidden = false;
    const head = h("div", { class: "grow" }, h("button", { class: "btn small", type: "button", onClick: loadLobby }, "← Back to games"));
    const body = h("div");
    stage.replaceChildren(head, body);
    let rev = -1, busy = false;
    async function refresh(force) {
      if (busy) return;
      let m;
      try { m = await get(`/api/matches/${id}`); } catch (e) { toast(e.message, "error"); return stopPolling(); }
      if (m.rev === rev && !force) return;
      rev = m.rev;
      draw(m);
      if (m.status !== "playing" && m.status !== "invited") stopPolling();
    }
    async function send(move, m) {
      busy = true;
      try { const r = await post(`/api/matches/${id}/move`, { move, rev }); rev = r.rev; draw(r); if (r.status === "done") stopPolling(); }
      catch (e) { toast(e.message, e.status === 409 ? "info" : "error"); }
      busy = false;
      if (!timer) timer = setInterval(() => refresh(false), 3000);
    }
    function draw(m) {
      const st = m.state, mineTurn = st.turn === m.you || st.turn === null;
      const who = m.you >= 0 && m.names.length > 1 ? m.names[1 - m.you] : "";
      const result = m.status === "done" ? (st.winner === "draw" ? "A draw." : st.winner === m.you ? "You won! 🎉" : m.winner ? `${m.names[st.winner]} won.` : "Game over.") : m.status === "declined" ? "The challenge was declined." : "";
      const status = h("p", { class: result ? "banner" : "muted" }, result || (m.status === "invited" ? "Waiting for the answer to your challenge…" : st.turn === null ? "Everybody plays at the same time." : mineTurn ? "Your turn." : `${m.names[st.turn]} is thinking…`));
      const board = BOARDS[m.game](m, send);
      const tools = h("div", { class: "grow" },
        m.status === "playing" ? h("button", { class: "btn small", type: "button", onClick: async () => { try { draw(await post(`/api/matches/${id}/resign`)); stopPolling(); } catch (e) { toast(e.message, "error"); } } }, "Give up") : null,
        m.status === "done" ? h("button", { class: "btn small primary", type: "button", onClick: () => { loadLobby(); } }, "Back to games") : null);
      body.replaceChildren(h("h2", {}, `${nameOf(info, m.game)}${who ? ` – you vs ${who}` : ""}${m.p1 === "bot" ? ` (${m.level})` : ""}`), status, board, tools);
    }
    await refresh(true);
    timer = setInterval(() => refresh(false), 3000);
  }

  // ---------------------------------------------------------------- boards (they only draw what the server says)
  const BOARDS = {
    tictactoe(m, send) {
      const mark = ["X", "O"];
      return h("div", { class: "ttt" }, m.state.board.map((v, i) => h("button", { class: "ttt-cell", type: "button", "aria-label": `Cell ${i + 1}`,
        disabled: v !== null || m.status !== "playing" || m.state.turn !== m.you, onClick: () => send({ cell: i }, m) }, v === null ? "" : mark[v])));
    },
    checkers(m, send) {
      const st = m.state, flip = m.you === 1;
      let sel = null;
      const wrap = h("div", { class: "board" });
      const legal = st.legal || [];
      function paint() {
        const tos = sel === null ? [] : legal.filter((l) => l[0] === sel).map((l) => l[1]);
        const froms = new Set(legal.map((l) => l[0]));
        const cells = [];
        for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
          const idx = flip ? (7 - r) * 8 + (7 - c) : r * 8 + c, v = st.board[idx];
          const piece = v ? h("span", { class: `ck-piece p${v % 2 === 1 ? 0 : 1}`, "aria-hidden": "true" }, v > 2 ? "♛" : "●") : null;
          cells.push(h("button", { type: "button", class: `bcell ${(r + c) % 2 ? "dark" : "light"}${sel === idx ? " sel" : ""}${tos.includes(idx) ? " hint" : ""}`, "aria-label": `Field ${idx}`,
            onClick: () => {
              if (m.status !== "playing" || st.turn !== m.you) return;
              if (tos.includes(idx)) return send({ from: sel, to: idx }, m);
              sel = froms.has(idx) ? idx : null; paint();
            } }, piece));
        }
        wrap.replaceChildren(...cells);
      }
      paint();
      return wrap;
    },
    chess(m, send) {
      const st = m.state, flip = m.you === 1, legal = st.legal || [];
      const rows = st.fen.split(" ")[0].split("/").map((row) => [...row].flatMap((ch) => (/\d/.test(ch) ? Array(Number(ch)).fill("") : [ch])));
      let sel = null;
      const wrap = h("div", { class: "board" });
      const sq = (r, c) => "abcdefgh"[c] + (8 - r);
      function paint() {
        const tos = sel === null ? [] : legal.filter((u) => u.startsWith(sel)).map((u) => u.slice(2, 4));
        const froms = new Set(legal.map((u) => u.slice(0, 2)));
        const cells = [];
        for (let rr = 0; rr < 8; rr++) for (let cc = 0; cc < 8; cc++) {
          const r = flip ? 7 - rr : rr, c = flip ? 7 - cc : cc, name = sq(r, c), p = rows[r][c];
          cells.push(h("button", { type: "button", class: `bcell ${(r + c) % 2 ? "dark" : "light"}${sel === name ? " sel" : ""}${tos.includes(name) ? " hint" : ""}`, "aria-label": name,
            onClick: () => {
              if (m.status !== "playing" || st.turn !== m.you) return;
              if (tos.includes(name)) return send({ uci: sel + name }, m);
              sel = froms.has(name) ? name : null; paint();
            } }, p ? h("span", { class: "chess-piece" }, PIECES[p]) : null));
        }
        wrap.replaceChildren(...cells);
      }
      paint();
      return h("div", {}, st.check ? h("p", { class: "banner" }, "Check!") : null, wrap);
    },
    memory(m, send) {
      const st = m.state;
      return h("div", {}, h("p", {}, m.names.length > 1 ? m.names.map((n, i) => `${n}: ${st.scores[i]}`).join("  ·  ") : `Pairs found: ${st.scores[0]}`),
        h("div", { class: "mem" }, Array.from({ length: st.size }, (_, i) => {
          const face = st.faces[String(i)];
          return h("button", { type: "button", class: `mem-card${st.matched[i] ? " found" : ""}`, "aria-label": `Card ${i + 1}`, disabled: m.status !== "playing" || st.turn !== m.you || st.matched[i],
            onClick: () => send({ card: i }, m) }, face || "?");
        })));
    },
    wordle(m, send) {
      const st = m.state, mine = st.guesses[m.you >= 0 ? m.you : 0], other = st.guesses[1 - (m.you >= 0 ? m.you : 0)];
      const colors = { g: "wd-g", y: "wd-y", x: "wd-x" };
      const row = (g) => h("div", { class: "wd-row" }, [...(g ? g.word : "     ")].map((ch, i) => h("span", { class: `wd-cell ${g ? colors[g.result[i]] : ""}` }, ch.toUpperCase())));
      const input = h("input", { class: "input", maxlength: "5", autocapitalize: "none", autocomplete: "off", "aria-label": "Your word", placeholder: "5 letters" });
      const form = h("form", { class: "inline-form", onSubmit: (e) => { e.preventDefault(); if (input.value.length === 5) { send({ word: input.value }, m); input.value = ""; } } },
        input, h("button", { class: "btn primary", type: "submit" }, "Guess"));
      return h("div", {}, h("div", { class: "wd" }, Array.from({ length: 6 }, (_, i) => row(mine[i]))),
        m.status === "playing" ? form : h("p", {}, `The word was: ${(st.secret || "").toUpperCase()}`),
        m.names.length > 1 ? h("p", { class: "muted" }, `${m.names[1 - m.you]} has used ${other.length} of 6 tries.`) : null);
    },
    typing(m, send) {
      const st = m.state, myRes = st.results[m.you >= 0 ? m.you : 0];
      const box = h("textarea", { class: "input", rows: "3", autocomplete: "off", autocapitalize: "none", spellcheck: "false", "aria-label": "Type the sentence here", disabled: Boolean(myRes) || m.status !== "playing" });
      const out = [];
      if (myRes) out.push(h("p", {}, `You: ${myRes.wpm} words per minute, ${myRes.accuracy}% correct${myRes.ok ? "" : " (not exact)"}.`));
      st.results.slice(0, m.names.length).forEach((r, i) => { if (r && i !== m.you) out.push(h("p", { class: "muted" }, `${m.names[i]}: ${r.wpm} words per minute${r.ok ? "" : " (not exact)"}.`)); });
      return h("div", {}, h("p", { class: "typing-text" }, st.text), box,
        h("button", { class: "btn primary", type: "button", disabled: Boolean(myRes) || m.status !== "playing", onClick: () => send({ text: box.value }, m) }, "Done"), ...out);
    },
  };

  await loadLobby();
}
