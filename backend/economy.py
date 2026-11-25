"""Coins, missions, the rank shop (temporary ranks) and gifts.

- Missions give coins ("write 10 messages today"). The progress is counted from the real data on the server
  (messages, reactions, uploads, logins), so it cannot be faked from the browser.
- A mission can be claimed once per period (day / week). The claim is saved together with the coins in ONE
  database transaction, so double clicks or two devices cannot pay it out twice.
- The Owner decides in the settings which ranks are for rent, for how many coins and how many days
  (the total rented time may never exceed shop.max_days, roughly one week by default).
- Admins and the Owner can gift coins (admins up to a daily cap) and temporary ranks.
"""
import datetime
import time

from flask import Blueprint, g, jsonify

import appsettings
import audit
import db
import notify
import perms
import storage
from security import ApiError, find_user, json_body, need, perm_required, public_user

bp = Blueprint("economy", __name__, url_prefix="/api")

KINDS = {
    "messages": "Write messages",
    "reactions": "React to messages",
    "uploads": "Send files",
    "logins": "Log in",
    "notes": "Write notes",
    "tasks_done": "Finish tasks",
}


# ---------------------------------------------------------------- time periods
def _period_start(period, now=None):
    now = datetime.datetime.fromtimestamp(now or time.time(), datetime.timezone.utc)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "weekly":
        day -= datetime.timedelta(days=day.weekday())
    return day


def period_key(period, now=None):
    start = _period_start(period, now)
    return start.strftime("%G-W%V") if period == "weekly" else start.strftime("%Y-%m-%d")


def progress(user, mission, now=None):
    start = _period_start(mission["period"], now).timestamp()
    name, kind = user["username"], mission["kind"]
    if kind == "messages":
        sql, p = "SELECT COUNT(*) AS n FROM messages WHERE sender = ? AND is_system = 0 AND deleted = 0 AND created >= ?", (name, start)
    elif kind == "reactions":
        sql, p = "SELECT COUNT(*) AS n FROM reactions WHERE username = ? AND created >= ?", (name, start)
    elif kind == "uploads":
        sql, p = "SELECT COUNT(*) AS n FROM attachments WHERE username = ? AND kind = 'attachment' AND status = 'ready' AND created >= ?", (name, start)
    elif kind == "logins":
        sql, p = "SELECT COUNT(*) AS n FROM login_log WHERE username = ? AND ok = 1 AND ts >= ?", (name, start)
    elif kind == "notes":
        sql, p = "SELECT COUNT(*) AS n FROM notes WHERE username = ? AND created >= ?", (name, start)
    elif kind == "tasks_done":
        # tasks the person owns and finished (done flag) - counted by creation day, which is good enough for a hobby app
        sql, p = "SELECT COUNT(*) AS n FROM tasks WHERE owner = ? AND done = 1 AND created >= ?", (name, start)
    else:
        return 0
    return db.query(sql, p)[0]["n"]


# ---------------------------------------------------------------- wallet
def balance(username, tx=None):
    rows = (tx or db).query("SELECT coins FROM wallets WHERE username = ?", (username,))
    return rows[0]["coins"] if rows else 0


def add_coins(tx, username, delta, reason, actor=""):
    """Changes a balance inside an open transaction. Refuses to go below zero."""
    tx.execute("INSERT INTO wallets (username, coins) VALUES (?, 0) ON CONFLICT (username) DO NOTHING", (username,))
    if delta < 0:
        n = tx.execute("UPDATE wallets SET coins = coins + ? WHERE username = ? AND coins + ? >= 0", (delta, username, delta))
        if n != 1:
            raise ApiError("You don't have enough coins.", 402)
    else:
        tx.execute("UPDATE wallets SET coins = coins + ? WHERE username = ?", (delta, username))
    tx.execute("INSERT INTO coin_log (username, delta, reason, actor, ts) VALUES (?, ?, ?, ?, ?)",
               (username, delta, reason[:120], actor, time.time()))


@bp.get("/coins")
@perm_required("missions.use")
def my_wallet():
    log = db.query("SELECT delta, reason, actor, ts FROM coin_log WHERE username = ? ORDER BY id DESC LIMIT 30", (g.user["username"],))
    return jsonify({"coins": balance(g.user["username"]), "log": log})


# ---------------------------------------------------------------- missions
def _mission_view(user, m, now=None):
    key = period_key(m["period"], now)
    done = bool(db.query("SELECT 1 AS x FROM mission_claims WHERE username = ? AND mission_id = ? AND period_key = ?",
                         (user["username"], m["id"], key)))
    value = progress(user, m, now)
    return {"id": m["id"], "title": m["title"], "kind": m["kind"], "target": m["target"], "period": m["period"],
            "reward": m["reward"], "active": bool(m["active"]), "progress": min(value, m["target"]),
            "claimed": done, "claimable": (not done) and value >= m["target"]}


@bp.get("/missions")
@perm_required("missions.use")
def list_missions():
    if not appsettings.get()["missions"]["enabled"]:
        return jsonify({"enabled": False, "missions": [], "kinds": KINDS})
    rows = db.query("SELECT * FROM missions WHERE active = 1 ORDER BY id")
    return jsonify({"enabled": True, "missions": [_mission_view(g.user, m) for m in rows], "kinds": KINDS})


@bp.post("/missions/<int:mid>/claim")
@perm_required("missions.use")
def claim(mid):
    rows = db.query("SELECT * FROM missions WHERE id = ? AND active = 1", (mid,))
    if not rows or not appsettings.get()["missions"]["enabled"]:
        raise ApiError("Mission not found.", 404)
    m = rows[0]
    if progress(g.user, m) < m["target"]:
        raise ApiError("You haven't finished this mission yet.", 400)
    key = period_key(m["period"])
    with db.transaction() as tx:
        # The primary key (username, mission, period) makes a second claim fail, even with two devices at once.
        n = tx.execute("INSERT INTO mission_claims (username, mission_id, period_key, ts) VALUES (?, ?, ?, ?) "
                       "ON CONFLICT (username, mission_id, period_key) DO NOTHING", (g.user["username"], mid, key, time.time()))
        if n != 1:
            raise ApiError("You already collected this reward.", 409)
        add_coins(tx, g.user["username"], m["reward"], f"Mission: {m['title']}")
        coins = balance(g.user["username"], tx)
    return jsonify({"coins": coins, "reward": m["reward"]})


def _mission_input(data):
    title = str(data.get("title", "")).strip()
    if not 3 <= len(title) <= 80:
        raise ApiError("The title needs 3 to 80 characters.")
    if data.get("kind") not in KINDS:
        raise ApiError("Unknown mission type.")
    if data.get("period") not in ("daily", "weekly"):
        raise ApiError("Period must be daily or weekly.")
    for key, hi in (("target", 10000), ("reward", 100000)):
        v = data.get(key)
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= hi:
            raise ApiError(f"'{key}' must be a whole number between 1 and {hi}.")
    return title, data["kind"], data["period"], data["target"], data["reward"]


@bp.get("/missions/manage")
@perm_required("missions.manage")
def manage_list():
    return jsonify({"missions": db.query("SELECT * FROM missions ORDER BY id"), "kinds": KINDS})


@bp.post("/missions")
@perm_required("missions.manage")
def create_mission():
    title, kind, period, target, reward = _mission_input(json_body())
    db.execute("INSERT INTO missions (title, kind, target, period, reward) VALUES (?, ?, ?, ?, ?)", (title, kind, target, period, reward))
    audit.log(g.user["username"], "mission_create", title)
    return jsonify({"message": "Mission created."}), 201


@bp.put("/missions/<int:mid>")
@perm_required("missions.manage")
def edit_mission(mid):
    data = json_body()
    title, kind, period, target, reward = _mission_input(data)
    n = db.execute("UPDATE missions SET title = ?, kind = ?, period = ?, target = ?, reward = ?, active = ? WHERE id = ?",
                   (title, kind, period, target, reward, 1 if data.get("active", True) is True else 0, mid))
    if not n:
        raise ApiError("Mission not found.", 404)
    audit.log(g.user["username"], "mission_edit", f"#{mid}")
    return jsonify({"message": "Saved."})


@bp.delete("/missions/<int:mid>")
@perm_required("missions.manage")
def delete_mission(mid):
    db.execute("DELETE FROM missions WHERE id = ?", (mid,))
    audit.log(g.user["username"], "mission_delete", f"#{mid}")
    return jsonify({"message": "Deleted."})


def seed_missions():
    """A few starter missions on the very first start (the Owner can change or delete them)."""
    if db.query("SELECT 1 AS x FROM missions LIMIT 1"):
        return
    for title, kind, target, period, reward in [
            ("Write 10 messages today", "messages", 10, "daily", 20),
            ("React to 5 messages today", "reactions", 5, "daily", 10),
            ("Log in today", "logins", 1, "daily", 5),
            ("Write 100 messages this week", "messages", 100, "weekly", 120)]:
        db.execute("INSERT INTO missions (title, kind, target, period, reward) VALUES (?, ?, ?, ?, ?)", (title, kind, target, period, reward))


# ---------------------------------------------------------------- shop: rent a rank
def give_lease(username, rank_id, days, cap_days, actor=""):
    """Extends or starts a temporary rank. The remaining time can never exceed cap_days."""
    now = time.time()
    with storage.transaction("users", "ranks") as s:
        user = find_user(s["users"], username)
        rank = s["ranks"].get(rank_id)
        if not user or not rank or rank.get("is_owner"):
            raise ApiError("Rank or user not found.", 404)
        lease = user.get("lease") or {}
        current = lease.get("until", 0) if lease.get("rank") == rank_id and lease.get("until", 0) > now else now
        until = min(current + days * 86400, now + cap_days * 86400)
        if until <= current + 1 and current > now:
            raise ApiError(f"You already have the maximum rental time ({cap_days} days).", 409)
        user["lease"] = {"rank": rank_id, "until": until}
    return until


@bp.get("/shop")
@perm_required("shop.use")
def shop():
    cfg = appsettings.get()["shop"]
    ranks = perms.all_ranks()
    items = []
    for item in cfg["items"]:
        r = ranks.get(item["rank_id"])
        if r and not r.get("is_owner"):
            items.append({**item, "rank": perms.rank_public(r), "designs": r.get("designs", []),
                          "perm_count": len(r.get("perms", []))})
    lease = perms.lease_of(g.user, ranks)
    return jsonify({"enabled": cfg["enabled"], "max_days": cfg["max_days"], "items": items,
                    "coins": balance(g.user["username"]),
                    "lease": {"rank": perms.rank_public(lease), "until": g.user["lease"]["until"]} if lease else None})


@bp.post("/shop/rent")
@perm_required("shop.use")
def rent():
    cfg = appsettings.get()["shop"]
    rank_id = json_body().get("rank_id")
    item = next((i for i in cfg["items"] if i["rank_id"] == rank_id), None)
    if not cfg["enabled"] or not item:
        raise ApiError("This rank is not for rent.", 404)
    ranks = perms.all_ranks()
    rank = ranks.get(rank_id)
    if not rank or rank.get("is_owner") or rank["level"] >= 60:
        raise ApiError("This rank is not for rent.", 404)
    if perms.level_of(g.user, ranks) >= rank["level"] and not perms.lease_of(g.user, ranks):
        raise ApiError("You already have this rank or a higher one.", 409)
    with db.transaction() as tx:                     # pay first; a failed rental below rolls the payment back
        add_coins(tx, g.user["username"], -item["price"], f"Rented {rank['name']} for {item['days']} day(s)")
        until = give_lease(g.user["username"], rank_id, item["days"], cfg["max_days"])
        coins = balance(g.user["username"], tx)
    return jsonify({"coins": coins, "until": until, "rank": perms.rank_public(rank)})


# ---------------------------------------------------------------- gifts (admins and Owner)
def _gift_today(actor):
    since = _period_start("daily").timestamp()
    return db.query("SELECT COALESCE(SUM(delta), 0) AS s FROM coin_log WHERE actor = ? AND reason LIKE 'Gift%' AND delta > 0 AND ts >= ?",
                    (actor, since))[0]["s"]


@bp.post("/coins/gift")
@perm_required("coins.gift")
def gift_coins():
    data = json_body()
    users = storage.read("users")
    target = find_user(users, data.get("username"))
    amount = data.get("amount")
    if not target or target["status"] != "active":
        raise ApiError("User not found.", 404)
    if isinstance(amount, bool) or not isinstance(amount, int) or not 1 <= amount <= 1_000_000:
        raise ApiError("The amount must be a whole number of coins.")
    if not perms.is_owner(g.user):
        cap = appsettings.get()["coins"]["admin_daily_gift_cap"]
        if _gift_today(g.user["username"]) + amount > cap:
            raise ApiError(f"You can gift at most {cap} coins per day.", 403)
    with db.transaction() as tx:
        add_coins(tx, target["username"], amount, f"Gift from {g.user['display_name']}", g.user["username"])
    notify.notify(target["username"], "gift", f"{g.user['display_name']} gave you {amount} coins.", "#/missions")
    audit.log(g.user["username"], "gift_coins", target["username"], str(amount))
    return jsonify({"message": f"{amount} coins sent to {target['display_name']}."})


@bp.post("/ranks/gift")
@perm_required("ranks.gift")
def gift_rank():
    data = json_body()
    users = storage.read("users")
    ranks = perms.all_ranks()
    target = find_user(users, data.get("username"))
    rank = ranks.get(data.get("rank_id"))
    days = data.get("days")
    if not target or target["status"] != "active" or not rank or rank.get("is_owner"):
        raise ApiError("User or rank not found.", 404)
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365:
        raise ApiError("Days must be a whole number between 1 and 365.")
    if not perms.is_owner(g.user):
        if rank["level"] >= perms.level_of(g.user, ranks):
            raise ApiError("You can only gift ranks below your own.", 403)
        if days > appsettings.get()["shop"]["gift_max_days"]:
            raise ApiError(f"You can gift a rank for at most {appsettings.get()['shop']['gift_max_days']} days.", 403)
    until = give_lease(target["username"], rank["id"], days, 365)
    notify.notify(target["username"], "gift", f"{g.user['display_name']} gave you the rank {rank['name']} for {days} day(s).", "#/missions")
    audit.log(g.user["username"], "gift_rank", target["username"], f"{rank['id']} {days}d")
    return jsonify({"message": f"{target['display_name']} has {rank['name']} until {time.strftime('%d.%m.%Y', time.gmtime(until))}."})
