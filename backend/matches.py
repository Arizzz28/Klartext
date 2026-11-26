"""Multiplayer matches: invitations, moves, the computer opponent, Elo and unlock points.

The RULES live in gamelogic.py (pure functions). This file only stores the state, checks who may do what, and
hands out points. Opponent "bot" = the computer (with a level), "solo" = alone (Memory, Word race, Typing).
"""
import json
import random
import time

from flask import Blueprint, g, jsonify

import db
import games
import gamelogic
import notify
import perms
import storage
from security import ApiError, find_user, json_body, perm_required

bp = Blueprint("matches", __name__, url_prefix="/api/matches")
BOT_GUESS_CHANCE = {"easy": 0.03, "medium": 0.12, "hard": 0.25, "impossible": 0.55}   # Word race: how likely the bot finds the word per try
SOLO_OK = {"memory", "wordle", "typing"}
K = 32


def _row(mid):
    rows = db.query("SELECT * FROM matches WHERE id = ?", (mid,))
    if not rows:
        raise ApiError("Match not found.", 404)
    return rows[0]


def _mine(row, user):
    if user["username"] not in (row["p0"], row["p1"]):
        raise ApiError("This is not your match.", 403)


def _players(row):
    return [row["p0"]] if row["p1"] == "solo" else [row["p0"], row["p1"]]


def _public(row, user):
    state = json.loads(row["state"])
    me = user["username"]
    view = gamelogic.GAMES[row["game"]]["view"](state, me)
    names = storage.read("users")
    def disp(n):
        u = names.get(n.lower())
        return u["display_name"] if u else ("Computer" if n == "bot" else n)
    return {"id": row["id"], "game": row["game"], "level": row["level"], "status": row["status"], "rev": row["rev"],
            "p0": row["p0"], "p1": row["p1"], "names": [disp(n) for n in _players(row)], "winner": row["winner"],
            "you": _players(row).index(me) if me in _players(row) else -1, "state": view, "updated": row["updated"]}


def _save(tx, row, state, status, winner=""):
    tx.execute("UPDATE matches SET state = ?, status = ?, winner = ?, rev = rev + 1, updated = ? WHERE id = ?",
               (json.dumps(state), status, winner, time.time(), row["id"]))


def _elo_update(tx, game, a, b, score_a):
    def get(n):
        r = tx.query("SELECT rating, games FROM elo WHERE game = ? AND username = ?", (game, n))
        return (r[0]["rating"], r[0]["games"]) if r else (1000, 0)
    ra, ga = get(a)
    rb, gb = get(b)
    ea = 1 / (1 + 10 ** ((rb - ra) / 400))
    na = round(ra + K * (score_a - ea))
    nb = round(rb + K * ((1 - score_a) - (1 - ea)))
    for n, r, gm in ((a, na, ga + 1), (b, nb, gb + 1)):
        tx.execute("INSERT INTO elo (game, username, rating, games) VALUES (?, ?, ?, ?) "
                   "ON CONFLICT (game, username) DO UPDATE SET rating = ?, games = ?", (game, n, r, gm, r, gm))


def _finish(tx, row, state):
    """Called once, when a game ends: winner name, Elo (human vs human only) and unlock points."""
    players = state["players"]
    w = state["winner"]
    winner = players[w] if isinstance(w, int) else ""
    game = row["game"]
    humans = [p for p in players if p != "bot"]
    if len(players) == 2 and "bot" not in players:
        _elo_update(tx, game, players[0], players[1], 1.0 if w == 0 else 0.0 if w == 1 else 0.5)
    for p in humans:
        pts = games.PLAY_POINTS
        if w == "draw":
            pts += games.HUMAN_DRAW if len(players) == 2 else 0
        elif winner == p:
            pts += games.WIN_POINTS.get(row["level"], 1) if "bot" in players else games.HUMAN_WIN if len(players) == 2 else 2
        tx.execute("INSERT INTO game_points (username, game, points) VALUES (?, ?, ?) "
                   "ON CONFLICT (username, game) DO UPDATE SET points = game_points.points + ?", (p, game, pts, pts))
    return winner


def _bot_turn(state, row):
    """Lets the computer act after a human move (only while the game goes on)."""
    game = row["game"]
    if state["status"] != "playing" or "bot" not in state["players"]:
        return
    if game == "wordle":
        i = state["players"].index("bot")
        if len(state["guesses"][i]) < 6:
            if random.random() < BOT_GUESS_CHANCE.get(row["level"], 0.1):
                word = state["secret"]
            else:
                word = random.choice([x for x in gamelogic.WORDS if x != state["secret"]])
            gamelogic.wd_move(state, "bot", {"word": word})
        return
    if game == "typing":
        return                                             # the computer's result was set when the match started
    guard = 0
    while state["status"] == "playing" and state["players"][state["turn"]] == "bot" and guard < 50:   # memory: a bot may go on after a match
        mv = gamelogic.GAMES[game]["bot"](state, row["level"])
        if mv is None:
            break
        gamelogic.GAMES[game]["move"](state, "bot", mv)
        guard += 1


def _check_user(name, game):
    u = find_user(storage.read("users"), name)
    if not u or u["status"] != "active":
        raise ApiError("User not found.", 404)
    if not perms.has_perm(u, f"games.{game}"):
        raise ApiError(f"{u['display_name']}'s rank does not include this game.", 403)
    return u


@bp.post("")
@perm_required("tabs.games")
def create():
    data = json_body()
    game = data.get("game")
    opp = str(data.get("opponent") or "")
    level = data.get("level") or "easy"
    if game not in gamelogic.GAMES:
        raise ApiError("This game has no matches.")
    if level not in gamelogic.LEVELS:
        raise ApiError("Unknown level.")
    games.check_play(g.user, game)
    me = g.user["username"]
    now = time.time()
    if opp == "solo":
        if game not in SOLO_OK:
            raise ApiError("This game needs an opponent.")
        players, p1, status = [me], "solo", "playing"
    elif opp == "bot":
        players, p1, status = [me, "bot"], "bot", "playing"
    else:
        other = _check_user(opp, game)
        if other["username"] == me:
            raise ApiError("You can not play against yourself. Try the computer.")
        ok, _ = games.unlock_state(other, game)
        if not ok:
            raise ApiError(f"{other['display_name']} has not unlocked this game yet.", 403)
        players, p1, status = [me, other["username"]], other["username"], "invited"
    state = gamelogic.GAMES[game]["new"](players, level)
    if game == "typing" and "bot" in players:
        state["results"][1] = gamelogic._bot_typing(state, level)
    with db.transaction() as tx:
        if status == "invited":
            if tx.query("SELECT COUNT(*) AS c FROM matches WHERE p0 = ? AND status = 'invited'", (me,))[0]["c"] >= 10:
                raise ApiError("You have too many open invitations.", 429)
        else:
            tx.execute("UPDATE matches SET status = 'done', winner = '' WHERE p0 = ? AND p1 IN ('bot','solo') AND game = ? AND status = 'playing'",
                       (me, game))                          # a new game against the computer replaces the old unfinished one
        tx.execute("INSERT INTO matches (game, p0, p1, level, status, state, rev, created, updated) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
                   (game, me, p1, level, status, json.dumps(state), now, now))
        mid = tx.query("SELECT MAX(id) AS i FROM matches WHERE p0 = ? AND created = ?", (me, now))[0]["i"]
    if status == "invited":
        notify.notify(p1, "game", f"{g.user['display_name']} challenges you to {games.BY_ID[game]['name']}.", "#/games")
    return jsonify(_public(_row(mid), g.user)), 201


@bp.get("")
@perm_required("tabs.games")
def mine():
    me = g.user["username"]
    rows = db.query("SELECT * FROM matches WHERE (p0 = ? OR p1 = ?) AND (status IN ('invited','playing') OR updated > ?) "
                    "ORDER BY updated DESC LIMIT 40", (me, me, time.time() - 86400))
    out = []
    for r in rows:
        p = _public(r, g.user)
        p["state"] = None                       # the list is light; open a match to get its board
        out.append(p)
    return jsonify({"matches": out})


@bp.get("/<int:mid>")
@perm_required("tabs.games")
def get_match(mid):
    row = _row(mid)
    _mine(row, g.user)
    return jsonify(_public(row, g.user))


@bp.post("/<int:mid>/accept")
@perm_required("tabs.games")
def accept(mid):
    row = _row(mid)
    _mine(row, g.user)
    if row["status"] != "invited" or row["p1"] != g.user["username"]:
        raise ApiError("There is nothing to accept.")
    games.check_play(g.user, row["game"])
    with db.transaction() as tx:
        tx.execute("UPDATE matches SET status = 'playing', rev = rev + 1, updated = ? WHERE id = ?", (time.time(), mid))
    notify.notify(row["p0"], "game", f"{g.user['display_name']} accepted your challenge.", "#/games")
    return jsonify(_public(_row(mid), g.user))


@bp.post("/<int:mid>/decline")
@perm_required("tabs.games")
def decline(mid):
    row = _row(mid)
    _mine(row, g.user)
    if row["status"] != "invited":
        raise ApiError("There is nothing to decline.")
    with db.transaction() as tx:
        tx.execute("UPDATE matches SET status = 'declined', rev = rev + 1, updated = ? WHERE id = ?", (time.time(), mid))
    other = row["p0"] if row["p1"] == g.user["username"] else row["p1"]
    notify.notify(other, "game", f"{g.user['display_name']} declined the game.", "#/games")
    return jsonify({"ok": True})


@bp.post("/<int:mid>/move")
@perm_required("tabs.games")
def move(mid):
    data = json_body()
    me = g.user["username"]
    with db.transaction() as tx:
        rows = tx.query("SELECT * FROM matches WHERE id = ?", (mid,))
        if not rows:
            raise ApiError("Match not found.", 404)
        row = rows[0]
        _mine(row, g.user)
        if row["status"] != "playing":
            raise ApiError("This match is not running.")
        state = json.loads(row["state"])
        if data.get("rev") is not None and data.get("rev") != row["rev"]:
            raise ApiError("The board changed. Reloading.", 409)
        try:
            gamelogic.GAMES[row["game"]]["move"](state, me, data.get("move"))
            _bot_turn(state, row)
        except gamelogic.GameError as e:
            raise ApiError(str(e), 400)
        status, winner = "playing", ""
        if state["status"] == "done":
            status, winner = "done", _finish(tx, row, state)
        _save(tx, row, state, status, winner)
    other = row["p1"] if row["p0"] == me else row["p0"]
    if other not in ("bot", "solo") and status == "playing":
        notify.notify(other, "game", f"It is your turn in {games.BY_ID[row['game']]['name']}.", "#/games")
    return jsonify(_public(_row(mid), g.user))


@bp.post("/<int:mid>/resign")
@perm_required("tabs.games")
def resign(mid):
    me = g.user["username"]
    with db.transaction() as tx:
        rows = tx.query("SELECT * FROM matches WHERE id = ?", (mid,))
        if not rows:
            raise ApiError("Match not found.", 404)
        row = rows[0]
        _mine(row, g.user)
        if row["status"] != "playing":
            raise ApiError("This match is not running.")
        state = json.loads(row["state"])
        players = state["players"]
        state["status"] = "done"
        state["winner"] = (1 - players.index(me)) if len(players) == 2 else "draw"
        winner = _finish(tx, row, state)
        _save(tx, row, state, "done", winner)
    return jsonify(_public(_row(mid), g.user))
