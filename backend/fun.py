"""The Fun tab: three small extras that make the app more fun to come back to.

1. Daily streak   - claim a few coins once a day; the more days in a row, the more (capped, so it can not run away)
2. Badges         - achievements that are CALCULATED from what you already did (nothing to cheat, nothing extra to store)
3. Polls          - ask a question with 2-6 answers; everybody votes once; results show live
"""
import datetime
import json
import time

from flask import Blueprint, g, jsonify

import db
import economy
import perms
from security import ApiError, json_body, perm_required

bp = Blueprint("fun", __name__, url_prefix="/api/fun")
STREAK_COINS = [2, 3, 4, 5, 6, 8, 10]                     # day 1, 2, 3 ... day 7 and later = 10


def _today():
    return datetime.datetime.now(datetime.timezone.utc).date()


def _streak_row(name):
    r = db.query("SELECT last_day, streak, best FROM streaks WHERE username = ?", (name,))
    return r[0] if r else {"last_day": "", "streak": 0, "best": 0}


def _current_streak(row):
    """The streak only counts while it is not broken: claimed today or yesterday."""
    if not row["last_day"]:
        return 0
    gap = (_today() - datetime.date.fromisoformat(row["last_day"])).days
    return row["streak"] if gap <= 1 else 0


BADGES = [
    ("first_win", "First win", "Win a game.", lambda s: s["wins"] >= 1),
    ("gamer", "Gamer", "Earn 20 game points.", lambda s: s["game_points"] >= 20),
    ("pro_gamer", "Pro gamer", "Earn 100 game points.", lambda s: s["game_points"] >= 100),
    ("duelist", "Duelist", "Play a game against another person.", lambda s: s["elo_games"] >= 1),
    ("rated", "Rated 1100", "Reach Elo 1100 in any game.", lambda s: s["best_elo"] >= 1100),
    ("streak7", "One week", "Claim the daily bonus 7 days in a row.", lambda s: s["best_streak"] >= 7),
    ("collector", "Collector", "Complete 10 missions.", lambda s: s["claims"] >= 10),
    ("rich", "Rich", "Own 500 coins.", lambda s: s["coins"] >= 500),
]


def _stats(name):
    q = lambda sql: db.query(sql, (name,))
    st = _streak_row(name)
    return {
        "wins": q("SELECT COUNT(*) AS c FROM matches WHERE winner = ?")[0]["c"],
        "game_points": q("SELECT COALESCE(SUM(points), 0) AS c FROM game_points WHERE username = ?")[0]["c"],
        "elo_games": q("SELECT COALESCE(SUM(games), 0) AS c FROM elo WHERE username = ?")[0]["c"],
        "best_elo": q("SELECT COALESCE(MAX(rating), 0) AS c FROM elo WHERE username = ?")[0]["c"],
        "best_streak": st["best"],
        "claims": q("SELECT COUNT(*) AS c FROM mission_claims WHERE username = ?")[0]["c"],
        "coins": economy.balance(name),
    }


@bp.get("")
@perm_required("tabs.fun")
def overview():
    name = g.user["username"]
    row = _streak_row(name)
    cur = _current_streak(row)
    claimed_today = row["last_day"] == _today().isoformat()
    s = _stats(name)
    return jsonify({"streak": cur, "best": row["best"], "claimed_today": claimed_today,
                    "next_reward": STREAK_COINS[min(cur if claimed_today else cur, len(STREAK_COINS) - 1)],
                    "badges": [{"id": i, "name": n, "text": t, "earned": bool(fn(s))} for i, n, t, fn in BADGES]})


@bp.post("/streak")
@perm_required("tabs.fun")
def claim_streak():
    name = g.user["username"]
    row = _streak_row(name)
    today = _today().isoformat()
    if row["last_day"] == today:
        raise ApiError("You already collected today. Come back tomorrow!", 400)
    cur = _current_streak(row) + 1
    reward = STREAK_COINS[min(cur - 1, len(STREAK_COINS) - 1)]
    best = max(row["best"], cur)
    with db.transaction() as tx:
        tx.execute("INSERT INTO streaks (username, last_day, streak, best) VALUES (?, ?, ?, ?) "
                   "ON CONFLICT (username) DO UPDATE SET last_day = ?, streak = ?, best = ?", (name, today, cur, best, today, cur, best))
        economy.add_coins(tx, name, reward, f"Daily streak day {cur}", "")
    return jsonify({"streak": cur, "reward": reward, "message": f"Day {cur}! +{reward} coins."})


# ---------------------------------------------------------------- polls
def _poll(row, me):
    opts = json.loads(row["options"])
    votes = db.query("SELECT choice, COUNT(*) AS n FROM poll_votes WHERE poll_id = ? GROUP BY choice", (row["id"],))
    counts = {v["choice"]: v["n"] for v in votes}
    mine = db.query("SELECT choice FROM poll_votes WHERE poll_id = ? AND username = ?", (row["id"], me))
    return {"id": row["id"], "author": row["author"], "question": row["question"], "closed": bool(row["closed"]),
            "options": [{"text": t, "votes": counts.get(i, 0)} for i, t in enumerate(opts)], "my_vote": mine[0]["choice"] if mine else None}


@bp.get("/polls")
@perm_required("tabs.fun")
def polls():
    rows = db.query("SELECT * FROM polls ORDER BY id DESC LIMIT 20")
    return jsonify({"polls": [_poll(r, g.user["username"]) for r in rows], "can_create": perms.has_perm(g.user, "polls.create")})


@bp.post("/polls")
@perm_required("polls.create")
def create_poll():
    data = json_body()
    q = str(data.get("question") or "").strip()
    opts = [str(o).strip() for o in (data.get("options") or []) if str(o).strip()]
    if not 3 <= len(q) <= 150 or not 2 <= len(opts) <= 6 or any(len(o) > 60 for o in opts) or len(set(opts)) != len(opts):
        raise ApiError("A poll needs a question (3-150 characters) and 2 to 6 different answers (up to 60 characters each).")
    if db.query("SELECT COUNT(*) AS c FROM polls WHERE author = ? AND created > ?", (g.user["username"], time.time() - 3600))[0]["c"] >= 5:
        raise ApiError("You made many polls this hour. Take a break.", 429)
    db.execute("INSERT INTO polls (author, question, options, created, closed) VALUES (?, ?, ?, ?, 0)", (g.user["username"], q, json.dumps(opts), time.time()))
    return jsonify({"ok": True}), 201


@bp.post("/polls/<int:pid>/vote")
@perm_required("tabs.fun")
def vote(pid):
    rows = db.query("SELECT * FROM polls WHERE id = ?", (pid,))
    if not rows or rows[0]["closed"]:
        raise ApiError("This poll is closed or does not exist.", 404)
    choice = json_body().get("choice")
    n = len(json.loads(rows[0]["options"]))
    if isinstance(choice, bool) or not isinstance(choice, int) or not 0 <= choice < n:
        raise ApiError("Unknown answer.")
    try:
        db.execute("INSERT INTO poll_votes (poll_id, username, choice) VALUES (?, ?, ?)", (pid, g.user["username"], choice))
    except Exception:
        raise ApiError("You already voted.", 400)
    return jsonify(_poll(rows[0], g.user["username"]))


@bp.post("/polls/<int:pid>/close")
@perm_required("tabs.fun")
def close_poll(pid):
    rows = db.query("SELECT * FROM polls WHERE id = ?", (pid,))
    if not rows:
        raise ApiError("Poll not found.", 404)
    if rows[0]["author"] != g.user["username"] and not perms.has_perm(g.user, "admin.users"):
        raise ApiError("Only the author or a moderator can close a poll.", 403)
    db.execute("UPDATE polls SET closed = 1 WHERE id = ?", (pid,))
    return jsonify({"ok": True})
