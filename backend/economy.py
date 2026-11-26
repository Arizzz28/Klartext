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
import random
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
    "none": "Nothing to do (free reward)",
    "messages": "Write messages",
    "reactions": "React to messages",
    "uploads": "Send files",
    "logins": "Log in",
    "notes": "Write notes",
    "tasks_done": "Finish tasks",
    "translate": "Translate texts into German (an admin checks them)",
}
PERIODS = {"hourly": "every hour", "daily": "every day", "weekly": "every week"}

# How rare a mission is. The WEIGHT decides how often it is drawn (the Owner can change the weights in Admin -> Settings).
RARITIES = {
    "common": {"label": "Common", "color": "#6b7b78", "weight": 60},
    "uncommon": {"label": "Uncommon", "color": "#2a9d5c", "weight": 25},
    "rare": {"label": "Rare", "color": "#2f6fd0", "weight": 10},
    "super_rare": {"label": "SUPER RARE", "color": "#7c4dcc", "weight": 4},
    "impossible": {"label": "IMPOSSIBLE", "color": "#c93d57", "weight": 1},
}


def rarity_weights():
    cfg = appsettings.get()["missions"]
    return {k: max(0, int(cfg.get(f"w_{k}", v["weight"]))) for k, v in RARITIES.items()}


def rarity_chances():
    w = rarity_weights()
    total = sum(w.values()) or 1
    return {k: round(100 * v / total, 1) for k, v in w.items()}


# ---------------------------------------------------------------- time periods
def _period_start(period, now=None):
    now = datetime.datetime.fromtimestamp(now or time.time(), datetime.timezone.utc)
    if period == "hourly":
        return now.replace(minute=0, second=0, microsecond=0)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "weekly":
        day -= datetime.timedelta(days=day.weekday())
    return day


def period_key(period, now=None):
    start = _period_start(period, now)
    if period == "weekly":
        return start.strftime("%G-W%V")
    return start.strftime("%Y-%m-%d-%H") if period == "hourly" else start.strftime("%Y-%m-%d")


def seconds_until_reset(period, now=None):
    now = now or time.time()
    start = _period_start(period, now).timestamp()
    length = {"hourly": 3600, "daily": 86400, "weekly": 7 * 86400}[period]
    return max(0, int(start + length - now))


def approved_translations(username, mission_id, key):
    return db.query("SELECT COUNT(*) AS n FROM translation_tasks WHERE username = ? AND mission_id = ? AND period_key = ? AND status = 'approved'",
                    (username, mission_id, key))[0]["n"]


def progress(user, mission, now=None):
    start = _period_start(mission["period"], now).timestamp()
    name, kind = user["username"], mission["kind"]
    if kind == "none":
        return mission["target"]                      # a free reward: nothing to do, it can be collected right away
    if kind == "translate":
        return approved_translations(name, mission["id"], period_key(mission["period"], now))
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
def _slots(period):
    return int(appsettings.get()["missions"].get(f"slots_{period}", 0))


def ensure_draws(username, now=None):
    """Random mode: every person gets their own random missions per period. The draw is saved, so it stays the same until
    the period is over (then a new one is drawn). Returns the set of mission ids the person may see and collect."""
    cfg = appsettings.get()["missions"]
    if cfg.get("mode") != "random":
        return None                                    # None = everybody sees every active mission (the old behaviour)
    weights = rarity_weights()
    chosen = set()
    for period in PERIODS:
        key = period_key(period, now)
        have = {r["mission_id"] for r in db.query("SELECT mission_id FROM mission_draws WHERE username = ? AND period = ? AND period_key = ?",
                                                  (username, period, key))}
        pool = [m for m in db.query("SELECT id, rarity FROM missions WHERE active = 1 AND period = ?", (period,))]
        live = {m["id"] for m in pool}
        have &= live                                   # a deleted or switched-off mission frees its slot
        free = [m for m in pool if m["id"] not in have]
        rng = random.SystemRandom()
        while len(have) < _slots(period) and free:
            w = [weights.get(m["rarity"], 1) for m in free]
            if sum(w) <= 0:
                w = [1] * len(free)
            pick = rng.choices(free, weights=w, k=1)[0]
            free.remove(pick)
            have.add(pick["id"])
            db.execute("INSERT INTO mission_draws (username, period, period_key, mission_id) VALUES (?, ?, ?, ?) "
                       "ON CONFLICT (username, period, period_key, mission_id) DO NOTHING", (username, period, key, pick["id"]))
        # only the slots count: if the Owner lowered the number of slots, show the first ones
        chosen |= set(sorted(have)[:max(_slots(period), 0)] if len(have) > _slots(period) else have)
    return chosen


def _mission_view(user, m, now=None):
    key = period_key(m["period"], now)
    done = bool(db.query("SELECT 1 AS x FROM mission_claims WHERE username = ? AND mission_id = ? AND period_key = ?",
                         (user["username"], m["id"], key)))
    value = progress(user, m, now)
    rar = RARITIES.get(m["rarity"], RARITIES["common"])
    out = {"id": m["id"], "title": m["title"], "kind": m["kind"], "target": m["target"], "period": m["period"],
           "reward": m["reward"], "active": bool(m["active"]), "progress": min(value, m["target"]),
           "claimed": done, "claimable": (not done) and value >= m["target"],
           "rarity": m["rarity"], "rarity_label": rar["label"], "rarity_color": rar["color"],
           "chance": rarity_chances().get(m["rarity"], 0), "resets_in": seconds_until_reset(m["period"], now)}
    if m["kind"] == "translate":
        out["tasks"] = translation_tasks(user["username"], m, key)
    return out


@bp.get("/missions")
@perm_required("missions.use")
def list_missions():
    cfg = appsettings.get()["missions"]
    if not cfg["enabled"]:
        return jsonify({"enabled": False, "missions": [], "kinds": KINDS})
    allowed = ensure_draws(g.user["username"])
    rows = db.query("SELECT * FROM missions WHERE active = 1 ORDER BY id")
    if allowed is not None:
        rows = [m for m in rows if m["id"] in allowed]
    return jsonify({"enabled": True, "mode": cfg.get("mode"), "missions": [_mission_view(g.user, m) for m in rows],
                    "kinds": KINDS, "rarities": {k: {**v, "chance": rarity_chances()[k]} for k, v in RARITIES.items()}})


@bp.post("/missions/<int:mid>/claim")
@perm_required("missions.use")
def claim(mid):
    rows = db.query("SELECT * FROM missions WHERE id = ? AND active = 1", (mid,))
    if not rows or not appsettings.get()["missions"]["enabled"]:
        raise ApiError("Mission not found.", 404)
    m = rows[0]
    allowed = ensure_draws(g.user["username"])
    if allowed is not None and mid not in allowed:       # random mode: only the missions drawn for YOU can be collected
        raise ApiError("Mission not found.", 404)
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


# ---------------------------------------------------------------- translation missions
def translation_tasks(username, mission, key):
    """The texts a person has to translate for this mission and period (drawn once, then kept)."""
    rows = db.query("SELECT t.id, t.item_id, t.answer, t.status, t.note, i.source, i.hint FROM translation_tasks t "
                    "JOIN translation_items i ON i.id = t.item_id WHERE t.username = ? AND t.mission_id = ? AND t.period_key = ? ORDER BY t.id",
                    (username, mission["id"], key))
    need_n = mission["target"] - len(rows)
    if need_n > 0:
        used = {r["item_id"] for r in rows}
        # texts this person already had approved are not given again
        done = {r["item_id"] for r in db.query("SELECT item_id FROM translation_tasks WHERE username = ? AND status = 'approved'", (username,))}
        pool = [i for i in db.query("SELECT id FROM translation_items WHERE active = 1") if i["id"] not in used and i["id"] not in done]
        random.shuffle(pool)
        for item in pool[:need_n]:
            db.execute("INSERT INTO translation_tasks (username, mission_id, period_key, item_id, created) VALUES (?, ?, ?, ?, ?)",
                       (username, mission["id"], key, item["id"], time.time()))
        rows = db.query("SELECT t.id, t.item_id, t.answer, t.status, t.note, i.source, i.hint FROM translation_tasks t "
                        "JOIN translation_items i ON i.id = t.item_id WHERE t.username = ? AND t.mission_id = ? AND t.period_key = ? ORDER BY t.id",
                        (username, mission["id"], key))
    return rows


@bp.post("/missions/<int:mid>/translate")
@perm_required("missions.use")
def submit_translation(mid):
    rows = db.query("SELECT * FROM missions WHERE id = ? AND active = 1 AND kind = 'translate'", (mid,))
    if not rows:
        raise ApiError("Mission not found.", 404)
    m = rows[0]
    allowed = ensure_draws(g.user["username"])
    if allowed is not None and mid not in allowed:
        raise ApiError("Mission not found.", 404)
    answers = json_body().get("answers")
    if not isinstance(answers, dict) or len(answers) > 50:
        raise ApiError("Invalid answers.")
    key = period_key(m["period"])
    mine = {t["id"]: t for t in translation_tasks(g.user["username"], m, key)}
    sent = 0
    for tid, text in answers.items():
        task = mine.get(int(tid)) if str(tid).isdigit() else None
        text = str(text).strip()[:400]
        if not task or task["status"] in ("approved", "submitted") or not text:
            continue                                   # approved or waiting for the check: can not be changed
        db.execute("UPDATE translation_tasks SET answer = ?, status = 'submitted', submitted = ?, note = '' WHERE id = ? AND username = ?",
                   (text, time.time(), task["id"], g.user["username"]))
        sent += 1
    if sent:
        notify.notify_perm("translations.review", "mission", f"{g.user['display_name']} sent {sent} translation(s) to check.", "#/missions", exclude=(g.user["username"],))
    return jsonify({"message": f"{sent} translation(s) sent. An admin checks them.", "sent": sent})


@bp.get("/translations/review")
@perm_required("translations.review")
def review_list():
    rows = db.query("SELECT t.id, t.username, t.answer, t.submitted, i.source, i.hint FROM translation_tasks t "
                    "JOIN translation_items i ON i.id = t.item_id WHERE t.status = 'submitted' ORDER BY t.submitted LIMIT 100")
    users = storage.read("users")
    for r in rows:
        u = find_user(users, r["username"])
        r["display_name"] = u["display_name"] if u else r["username"]
    return jsonify({"items": rows})


@bp.post("/translations/<int:tid>/review")
@perm_required("translations.review")
def review_one(tid):
    data = json_body()
    approve = data.get("approve") is True
    note = str(data.get("note", "")).strip()[:200]
    rows = db.query("SELECT * FROM translation_tasks WHERE id = ? AND status = 'submitted'", (tid,))
    if not rows:
        raise ApiError("Nothing to check here (already done?).", 404)
    task = rows[0]
    if task["username"].lower() == g.user["username"].lower() and not perms.is_owner(g.user):
        raise ApiError("You can not check your own translation.", 403)
    db.execute("UPDATE translation_tasks SET status = ?, reviewed_by = ?, reviewed_at = ?, note = ? WHERE id = ?",
               ("approved" if approve else "open", g.user["username"], time.time(), note, tid))
    # a rejected translation goes back to "open" so the person can try again (the note says what was wrong)
    notify.notify(task["username"], "mission", "Your translation was approved." if approve else "A translation needs another try."
                  + (f" {note}" if note else ""), "#/missions")
    audit.log(g.user["username"], "translation_review", task["username"], "approved" if approve else "rejected")
    return jsonify({"message": "Saved."})


@bp.get("/translations/items")
@perm_required("missions.manage")
def item_list():
    return jsonify({"items": db.query("SELECT * FROM translation_items ORDER BY id DESC LIMIT 300")})


@bp.post("/translations/items")
@perm_required("missions.manage")
def item_add():
    data = json_body()
    source = str(data.get("source", "")).strip()
    if not 2 <= len(source) <= 300:
        raise ApiError("The text needs 2 to 300 characters.")
    db.execute("INSERT INTO translation_items (source, hint) VALUES (?, ?)", (source, str(data.get("hint", "")).strip()[:200]))
    return jsonify({"message": "Added."}), 201


@bp.delete("/translations/items/<int:iid>")
@perm_required("missions.manage")
def item_delete(iid):
    db.execute("UPDATE translation_items SET active = 0 WHERE id = ?", (iid,))
    return jsonify({"message": "Removed."})


def seed_translation_items():
    if db.query("SELECT 1 AS x FROM translation_items LIMIT 1"):
        return
    for text, hint in [("Write a message", "Button text in the chat"), ("Mark all as read", ""), ("Create account", ""),
                       ("Forgot your password?", ""), ("Nothing here yet", "empty list"), ("Rent a rank", ""),
                       ("Start page after login", ""), ("Delete my account", ""), ("Download my data", ""),
                       ("Your password is wrong.", "error message"), ("The upload failed. Check your connection.", "error message"),
                       ("Send a friend request", ""), ("Notifications", ""), ("Collect your reward", ""),
                       ("This file type is not allowed.", "error message"), ("Choose a design", "")]:
        db.execute("INSERT INTO translation_items (source, hint) VALUES (?, ?)", (text, hint))


def _mission_input(data):
    title = str(data.get("title", "")).strip()
    if not 3 <= len(title) <= 80:
        raise ApiError("The title needs 3 to 80 characters.")
    if data.get("kind") not in KINDS:
        raise ApiError("Unknown mission type.")
    if data.get("period") not in PERIODS:
        raise ApiError("The reset must be hourly, daily or weekly.")
    rarity = data.get("rarity", "common")
    if rarity not in RARITIES:
        raise ApiError("Unknown rarity.")
    for key, hi in (("target", 10000), ("reward", 100000)):
        v = data.get(key)
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= hi:
            raise ApiError(f"'{key}' must be a whole number between 1 and {hi}.")
    return title, data["kind"], data["period"], data["target"], data["reward"], rarity


@bp.get("/missions/manage")
@perm_required("missions.manage")
def manage_list():
    return jsonify({"missions": db.query("SELECT * FROM missions ORDER BY id"), "kinds": KINDS, "periods": PERIODS,
                    "rarities": {k: {**v, "chance": rarity_chances()[k]} for k, v in RARITIES.items()}})


@bp.post("/missions")
@perm_required("missions.manage")
def create_mission():
    title, kind, period, target, reward, rarity = _mission_input(json_body())
    db.execute("INSERT INTO missions (title, kind, target, period, reward, rarity) VALUES (?, ?, ?, ?, ?, ?)",
               (title, kind, target, period, reward, rarity))
    audit.log(g.user["username"], "mission_create", title)
    return jsonify({"message": "Mission created."}), 201


@bp.put("/missions/<int:mid>")
@perm_required("missions.manage")
def edit_mission(mid):
    data = json_body()
    title, kind, period, target, reward, rarity = _mission_input(data)
    n = db.execute("UPDATE missions SET title = ?, kind = ?, period = ?, target = ?, reward = ?, rarity = ?, active = ? WHERE id = ?",
                   (title, kind, period, target, reward, rarity, 1 if data.get("active", True) is True else 0, mid))
    if not n:
        raise ApiError("Mission not found.", 404)
    audit.log(g.user["username"], "mission_edit", f"#{mid}")
    return jsonify({"message": "Saved."})


@bp.delete("/missions/<int:mid>")
@perm_required("missions.manage")
def delete_mission(mid):
    db.execute("DELETE FROM missions WHERE id = ?", (mid,))
    db.execute("DELETE FROM mission_draws WHERE mission_id = ?", (mid,))
    audit.log(g.user["username"], "mission_delete", f"#{mid}")
    return jsonify({"message": "Deleted."})


def seed_missions():
    """A few starter missions on the very first start (the Owner can change or delete them)."""
    seed_translation_items()
    if db.query("SELECT 1 AS x FROM missions LIMIT 1"):
        return
    for title, kind, target, period, reward, rarity in [
            ("Write 10 messages today", "messages", 10, "daily", 20, "common"),
            ("React to 5 messages today", "reactions", 5, "daily", 10, "common"),
            ("Log in today", "logins", 1, "daily", 5, "common"),
            ("Free daily bonus", "none", 1, "daily", 3, "uncommon"),
            ("Translate 5 texts into German", "translate", 5, "weekly", 150, "rare"),
            ("Write 100 messages this week", "messages", 100, "weekly", 120, "common")]:
        db.execute("INSERT INTO missions (title, kind, target, period, reward, rarity) VALUES (?, ?, ?, ?, ?, ?)",
                   (title, kind, target, period, reward, rarity))


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


@bp.post("/coins/send")
@perm_required("coins.send")
def send_coins():
    """Everybody may send their OWN coins to somebody else (with a daily limit the Owner sets)."""
    data = json_body()
    me = g.user
    target = find_user(storage.read("users"), data.get("username"))
    amount = data.get("amount")
    if not target or target["status"] != "active":
        raise ApiError("User not found.", 404)
    if target["username"].lower() == me["username"].lower():
        raise ApiError("You can not send coins to yourself.")
    if isinstance(amount, bool) or not isinstance(amount, int) or not 1 <= amount <= 1_000_000:
        raise ApiError("The amount must be a whole number of coins.")
    cap = appsettings.get()["coins"]["user_daily_send_cap"]
    since = _period_start("daily").timestamp()
    sent = db.query("SELECT COALESCE(-SUM(delta), 0) AS s FROM coin_log WHERE username = ? AND reason LIKE 'Sent to%' AND delta < 0 AND ts >= ?",
                    (me["username"], since))[0]["s"]
    if sent + amount > cap:
        raise ApiError(f"You can send at most {cap} coins per day (you already sent {int(sent)}).", 403)
    with db.transaction() as tx:                      # both sides or none
        add_coins(tx, me["username"], -amount, f"Sent to {target['display_name']}", me["username"])
        add_coins(tx, target["username"], amount, f"From {me['display_name']}", me["username"])
        coins = balance(me["username"], tx)
    notify.notify(target["username"], "gift", f"{me['display_name']} sent you {amount} coins.", "#/missions")
    return jsonify({"coins": coins, "message": f"{amount} coins sent to {target['display_name']}."})


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
