"""Games: the list, the unlock order, scores and leaderboards. The multiplayer matches are in matches.py, the rules in gamelogic.py.

Each game is its own permission (games.<id>) so the Owner decides which rank gets which game. On top of that, games are
UNLOCKED one after the other (order and points needed are set by admins in Admin -> Settings -> Games).
Single-player games (reaction, aim, maze, shooter, number guess) run in the browser and send only their score; the server
rejects scores that are impossible (a reaction time of 5 ms, 9000 targets in 30 seconds, ...).
"""
import time

from flask import Blueprint, g, jsonify

import appsettings
import db
import perms
from security import ApiError, json_body, need, perm_required

# kind: "match" = rules run on the server (see gamelogic.py), "solo" = runs in the browser, only the score is sent.
# better: which direction is better for the score. good: a "good run" (gives extra unlock points). limits: plausible range.
GAMES = [
    {"id": "tictactoe", "name": "Tic-Tac-Toe", "kind": "match", "text": "Against a friend or the computer: easy, medium, hard or impossible.", "better": "high"},
    {"id": "reaction", "name": "Reaction", "kind": "solo", "text": "Click as soon as the screen turns green. Your best time in milliseconds counts.",
     "better": "low", "good": 350, "limits": (80, 5000)},
    {"id": "aim", "name": "Aim trainer", "kind": "solo", "text": "Hit as many targets as you can in 30 seconds.", "better": "high", "good": 20, "limits": (0, 150)},
    {"id": "memory", "name": "Memory", "kind": "match", "text": "Find the pairs. Alone, against a friend or the computer.", "better": "low", "limits": (1, 500)},
    {"id": "guess", "name": "Number guess", "kind": "solo", "text": "Find the secret number from 1 to 100 in as few tries as possible.", "better": "low", "good": 8, "limits": (1, 100)},
    {"id": "wordle", "name": "Word race", "kind": "match", "text": "Guess the 5-letter word in 6 tries. Race a friend or the computer.", "better": "high"},
    {"id": "checkers", "name": "Checkers", "kind": "match", "text": "Classic draughts. Jumping is mandatory.", "better": "high"},
    {"id": "typing", "name": "Typing duel", "kind": "match", "text": "Type the sentence faster than your opponent.", "better": "high"},
    {"id": "chess", "name": "Chess", "kind": "match", "text": "Full chess rules. Against a friend or the computer.", "better": "high"},
    {"id": "maze3d", "name": "3D maze", "kind": "solo", "text": "Find the exit of a 3D maze as fast as you can.", "better": "low", "good": 90, "limits": (5, 3600)},
    {"id": "shooter", "name": "Shooter", "kind": "solo", "text": "Survive and shoot as many enemies as you can in a 3D hall.", "better": "high", "good": 10, "limits": (0, 400)},
]
BY_ID = {x["id"]: x for x in GAMES}
DEFAULT_ORDER = [x["id"] for x in GAMES]
DEFAULT_UNLOCK = {"tictactoe": 0, "reaction": 3, "aim": 3, "memory": 4, "guess": 4, "wordle": 6, "checkers": 8, "typing": 8,
                  "chess": 10, "maze3d": 12, "shooter": 14}
WIN_POINTS = {"easy": 1, "medium": 2, "hard": 4, "impossible": 10}       # points for beating the computer on that level
HUMAN_WIN, HUMAN_DRAW, PLAY_POINTS = 5, 2, 1

bp = Blueprint("games", __name__, url_prefix="/api/games")


def cfg():
    c = appsettings.get()["games"]
    order = [i for i in c["order"] if i in BY_ID] + [i for i in DEFAULT_ORDER if i not in c["order"]]
    return {**c, "order": order, "unlock": {**DEFAULT_UNLOCK, **c.get("unlock", {})}}


def points_of(username):
    return {r["game"]: r["points"] for r in db.query("SELECT game, points FROM game_points WHERE username = ?", (username,))}


def add_points(username, game, n):
    if n <= 0 or username == "bot":
        return
    db.execute("INSERT INTO game_points (username, game, points) VALUES (?, ?, ?) "
               "ON CONFLICT (username, game) DO UPDATE SET points = game_points.points + ?", (username, game, n, n))


def unlock_state(user, game_id, c=None, pts=None):
    """(unlocked?, reason). A game is open when the sequence is off, or when the PREVIOUS game the person may play has
    enough points. The first game is always open."""
    c = c or cfg()
    if game_id in c["disabled"]:
        return False, "Switched off by the admins."
    if not c["sequential"] or perms.is_owner(user):
        return True, ""
    pts = pts if pts is not None else points_of(user["username"])
    chain = [i for i in c["order"] if i not in c["disabled"] and perms.has_perm(user, f"games.{i}")]
    if game_id not in chain or chain.index(game_id) == 0:
        return True, ""
    prev = chain[chain.index(game_id) - 1]
    need_pts = c["unlock"].get(game_id, 0)
    have = pts.get(prev, 0)
    return (True, "") if have >= need_pts else (False, f"Earn {need_pts - have} more point(s) in {BY_ID[prev]['name']} to unlock this.")


def check_play(user, game_id):
    """Raises unless this person may play the game right now (games on, rank, unlocked)."""
    if game_id not in BY_ID:
        raise ApiError("Unknown game.", 404)
    c = cfg()
    if not c["enabled"]:
        raise ApiError("Games are switched off at the moment.", 403)
    need(user, "tabs.games")
    need(user, f"games.{game_id}")
    ok, why = unlock_state(user, game_id, c)
    if not ok:
        raise ApiError(why, 403)


@bp.get("")
@perm_required("tabs.games")
def list_games():
    c = cfg()
    pts = points_of(g.user["username"])
    scores = {r["game"]: r for r in db.query("SELECT game, best, plays FROM game_scores WHERE username = ?", (g.user["username"],))}
    elo = {r["game"]: r["rating"] for r in db.query("SELECT game, rating FROM elo WHERE username = ?", (g.user["username"],))}
    out = []
    for gid in c["order"]:
        game = BY_ID[gid]
        allowed = perms.has_perm(g.user, f"games.{gid}")
        unlocked, why = unlock_state(g.user, gid, c, pts) if allowed else (False, "")
        mine = scores.get(gid)
        out.append({"id": gid, "name": game["name"], "text": game["text"], "kind": game["kind"], "better": game["better"],
                    "allowed": allowed, "unlocked": unlocked, "locked_reason": why if allowed else "Not included in your rank.",
                    "points": pts.get(gid, 0), "my_best": mine["best"] if mine else 0, "my_plays": mine["plays"] if mine else 0,
                    "elo": elo.get(gid), "unlock_points": c["unlock"].get(gid, 0)})
    return jsonify({"enabled": c["enabled"], "sequential": c["sequential"], "games": out})


@bp.get("/<game_id>/leaderboard")
@perm_required("tabs.games")
def leaderboard(game_id):
    if game_id not in BY_ID:
        raise ApiError("Unknown game.", 404)
    need(g.user, f"games.{game_id}")
    order = "ASC" if BY_ID[game_id]["better"] == "low" else "DESC"
    rows = db.query(f"SELECT username, best, plays FROM game_scores WHERE game = ? AND best > 0 ORDER BY best {order} LIMIT 10", (game_id,))
    elo = db.query("SELECT username, rating, games FROM elo WHERE game = ? AND games >= 1 ORDER BY rating DESC LIMIT 10", (game_id,))
    return jsonify({"order": order.lower(), "rows": rows, "elo": elo})


@bp.post("/<game_id>/score")
@perm_required("tabs.games")
def submit_score(game_id):
    check_play(g.user, game_id)
    game = BY_ID[game_id]
    score = json_body().get("score")
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100000:
        raise ApiError("Invalid score.")
    lo, hi = game.get("limits", (0, 100000))
    if not lo <= score <= hi:
        raise ApiError("That score is not possible.", 400)          # e.g. a reaction time of 5 ms
    lower = game["better"] == "low"
    name = g.user["username"]
    rows = db.query("SELECT best FROM game_scores WHERE game = ? AND username = ?", (game_id, name))
    if not rows:
        db.execute("INSERT INTO game_scores (game, username, best, plays) VALUES (?, ?, ?, 1)", (game_id, name, score))
        best = score
    else:
        old = rows[0]["best"]
        best = score if old == 0 or (score < old if lower else score > old) else old
        db.execute("UPDATE game_scores SET best = ?, plays = plays + 1 WHERE game = ? AND username = ?", (best, game_id, name))
    good = game.get("good")
    is_good = good is not None and ((score <= good) if lower else (score >= good))
    add_points(name, game_id, PLAY_POINTS + (3 if is_good else 0))
    return jsonify({"best": best, "points_earned": PLAY_POINTS + (3 if is_good else 0)})
