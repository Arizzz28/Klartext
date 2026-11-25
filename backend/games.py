"""Games. Each game is its own permission (games.<id>) so the Owner can decide which rank gets which game.
The games themselves run in the browser; the server only keeps the best scores (a simple leaderboard)."""
import time

from flask import Blueprint, g, jsonify

import db
import perms
from security import ApiError, json_body, perm_required, need

GAMES = [
    {"id": "tictactoe", "name": "Tic-Tac-Toe", "text": "You against the computer."},
    {"id": "guess", "name": "Number guess", "text": "Find the secret number from 1 to 100 in as few tries as possible."},
    {"id": "memory", "name": "Memory", "text": "Find all pairs with as few moves as possible."},
]
bp = Blueprint("games", __name__, url_prefix="/api/games")


@bp.get("")
@perm_required("tabs.games")
def list_games():
    out = []
    for game in GAMES:
        mine = db.query("SELECT best, plays FROM game_scores WHERE game = ? AND username = ?", (game["id"], g.user["username"]))
        out.append({**game, "allowed": perms.has_perm(g.user, f"games.{game['id']}"),
                    "my_best": mine[0]["best"] if mine else 0, "my_plays": mine[0]["plays"] if mine else 0})
    return jsonify(out)


@bp.get("/<game_id>/leaderboard")
@perm_required("tabs.games")
def leaderboard(game_id):
    if game_id not in {x["id"] for x in GAMES}:
        raise ApiError("Unknown game.", 404)
    need(g.user, f"games.{game_id}")
    # lower is better for "guess" and "memory" (fewer tries / moves), higher for tictactoe (wins)
    order = "ASC" if game_id in ("guess", "memory") else "DESC"
    rows = db.query(f"SELECT username, best, plays FROM game_scores WHERE game = ? AND best > 0 ORDER BY best {order} LIMIT 10", (game_id,))
    return jsonify({"order": order.lower(), "rows": rows})


@bp.post("/<game_id>/score")
@perm_required("tabs.games")
def submit_score(game_id):
    if game_id not in {x["id"] for x in GAMES}:
        raise ApiError("Unknown game.", 404)
    need(g.user, f"games.{game_id}")
    score = json_body().get("score")
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100000:
        raise ApiError("Invalid score.")
    lower_is_better = game_id in ("guess", "memory")
    rows = db.query("SELECT best FROM game_scores WHERE game = ? AND username = ?", (game_id, g.user["username"]))
    if not rows:
        db.execute("INSERT INTO game_scores (game, username, best, plays) VALUES (?, ?, ?, 1)", (game_id, g.user["username"], score))
        best = score
    else:
        old = rows[0]["best"]
        best = score if old == 0 or (score < old if lower_is_better else score > old) else old
        db.execute("UPDATE game_scores SET best = ?, plays = plays + 1 WHERE game = ? AND username = ?", (best, game_id, g.user["username"]))
    return jsonify({"best": best})
