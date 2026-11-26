"""Administration: users, ranks, permission requests, groups, private-chat access, stats, audit log, settings.
Every route checks its OWN permission (see perms.py) - there is no general "admin" switch any more."""
import re
import secrets
import time

from flask import Blueprint, g, jsonify, request

import accounts
import appsettings
import audit
import chat_service
import db
import notify
import objstore
import perms
import settings as settings_module
import storage
from security import (ApiError, clean_text, find_user, hash_password, is_super_admin, json_body, need,
                      perm_required, public_user, valid_email, valid_password, valid_username)

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _view(u, ranks=None):
    ranks = ranks or perms.all_ranks()
    return {"username": u["username"], "display_name": u["display_name"], "email": u["email"], "status": u["status"],
            "rank": perms.rank_public(perms.rank_of(u, ranks)), "base_rank_id": perms.base_rank_of(u, ranks)["id"],
            "is_owner": is_super_admin(u), "extra_perms": u.get("extra_perms", []),
            "lease_until": (u.get("lease") or {}).get("until", 0),
            "must_change_password": bool(u.get("must_change_password")), "muted_until": u.get("muted_until", 0),
            "created": u.get("created", 0), "consent": (u.get("consent") or {}).get("at", 0)}


def _target(users, username):
    user = find_user(users, username)
    if not user:
        raise ApiError("User not found.", 404)
    return user


def _protect(target):
    """You may only act on people whose rank is BELOW yours. The Owner can never be touched."""
    if target["username"] == g.user["username"]:
        raise ApiError("You can't do this to your own account here.", 400)
    if is_super_admin(target):
        raise ApiError("The Owner account is protected.", 403)
    if not perms.can_manage(g.user, target):
        raise ApiError("This person's rank is not below yours.", 403)


def _rank_for_assignment(rank_id, ranks):
    rank = ranks.get(rank_id)
    if not rank or rank.get("is_owner"):
        raise ApiError("Unknown rank.")
    if not perms.is_owner(g.user) and rank["level"] >= perms.level_of(g.user, ranks):
        raise ApiError("You can only give ranks below your own.", 403)
    return rank


# ------------------------------------------------------------------ users
@bp.get("/users")
@perm_required("admin.users")
def list_users():
    order = {"pending": 0, "active": 1, "banned": 2}
    ranks = perms.all_ranks()
    result = [_view(u, ranks) for u in storage.read("users").values()]
    result.sort(key=lambda u: (order.get(u["status"], 3), u["username"].lower()))
    return jsonify(result)


@bp.post("/users")
@perm_required("admin.users")
def create_user():
    data = json_body()
    username = valid_username(data.get("username"))
    email = valid_email(data.get("email"))
    ranks = perms.all_ranks()
    rank_id = data.get("rank") or perms.default_rank_id()
    _rank_for_assignment(rank_id, ranks)
    generated = None
    password = data.get("password")
    if password:
        valid_password(password)
    else:
        password = generated = secrets.token_urlsafe(9)
    display = clean_text(data.get("display_name") or username, "Display name", 40)
    must_change = data.get("must_change_password", True) is True
    with storage.transaction("users") as db_:
        if username.lower() in db_["users"]:
            raise ApiError("That username is already taken.", 409)
        if any(u["email"].lower() == email.lower() for u in db_["users"].values()):
            raise ApiError("That email address is already registered.", 409)
        db_["users"][username.lower()] = {
            "username": username, "email": email, "password_hash": hash_password(password), "display_name": display,
            "avatar": "", "rank": rank_id, "status": "active",
            "must_change_password": must_change, "token_version": 0, "created": time.time()}
        created = db_["users"][username.lower()]
    audit.log(g.user["username"], "create_user", username, f"rank {rank_id}")
    return jsonify({"user": _view(created), "generated_password": generated}), 201


@bp.patch("/users/<username>")
@perm_required("admin.users")
def edit_user(username):
    data = json_body()
    ranks = perms.all_ranks()
    with storage.transaction("users") as db_:
        target = _target(db_["users"], username)
        if target["username"] != g.user["username"]:
            _protect(target)
        changes = []
        if "display_name" in data:
            target["display_name"] = clean_text(data["display_name"], "Display name", 40)
            changes.append("display name")
        if "email" in data:
            email = valid_email(data["email"])
            if any(u["email"].lower() == email.lower() and u is not target for u in db_["users"].values()):
                raise ApiError("That email address is already registered.", 409)
            target["email"] = email
            changes.append("email")
        if "rank" in data:
            need(g.user, "admin.manage_ranks")
            _protect(target)
            _rank_for_assignment(data["rank"], ranks)
            target["rank"] = data["rank"]
            changes.append(f"rank {data['rank']}")
        if data.get("clear_lease") is True:
            need(g.user, "admin.manage_ranks")
            _protect(target)
            target.pop("lease", None)
            changes.append("rental ended")
        result = _view(target, ranks)
    audit.log(g.user["username"], "edit_user", username, ", ".join(changes))
    return jsonify(result)


def _set_status(username, status):
    with storage.transaction("users") as db_:
        target = _target(db_["users"], username)
        _protect(target)
        target["status"] = status
        target["token_version"] += 1          # kicks the user out of every device
    audit.log(g.user["username"], f"status_{status}", target["username"])
    return jsonify({"message": f"{target['username']} is now {status}."})


@bp.post("/users/<username>/approve")
@perm_required("admin.users")
def approve(username):
    return _set_status(username, "active")


@bp.post("/users/<username>/suspend")
@perm_required("admin.users")
def suspend(username):
    return _set_status(username, "banned")


@bp.post("/users/<username>/reset-password")
@perm_required("admin.users")
def reset_password(username):
    password = (request.get_json(silent=True) or {}).get("password")     # body is optional
    generated = None
    if password:
        valid_password(password)
    else:
        password = generated = secrets.token_urlsafe(9)
    with storage.transaction("users") as db_:
        target = _target(db_["users"], username)
        if target["username"] != g.user["username"]:
            _protect(target)
        target["password_hash"] = hash_password(password)
        target["must_change_password"] = True
        target["token_version"] += 1
    audit.log(g.user["username"], "reset_password", target["username"])
    return jsonify({"message": f"New password set for {target['username']}. They must change it at the next login.",
                    "generated_password": generated})


@bp.post("/users/<username>/logout-all")
@perm_required("admin.users")
def logout_all(username):
    with storage.transaction("users") as db_:
        target = _target(db_["users"], username)
        if target["username"] != g.user["username"]:
            _protect(target)
        target["token_version"] += 1
    audit.log(g.user["username"], "logout_all", target["username"])
    return jsonify({"message": f"{target['username']} was logged out everywhere."})


@bp.post("/users/<username>/delete")
@perm_required("admin.delete_users")
def delete_user(username):
    """Deletes an account completely. Private chats of that person are deleted;
    group messages are deleted or kept as 'Deleted user' (admin's choice)."""
    data = json_body()
    delete_group_messages = data.get("delete_group_messages") is True
    purge_groups = []
    with storage.transaction("users", "groups", "invitations", "whitelist") as db_:
        target = _target(db_["users"], username)
        _protect(target)
        if str(data.get("confirm", "")).lower() != target["username"].lower():
            raise ApiError("Type the username to confirm the deletion.")
        name = target["username"]
        purge_groups = accounts.remove_account_records(db_, name)
    accounts.finish_deletion(name, delete_group_messages, purge_groups)
    audit.log(g.user["username"], "delete_user", name, "group messages deleted" if delete_group_messages else "group messages kept")
    return jsonify({"message": f"{name} was deleted."})


# ------------------------------------------------------------------ whitelist
@bp.get("/whitelist")
@perm_required("admin.whitelist")
def get_whitelist():
    return jsonify(sorted(storage.read("whitelist")))


@bp.post("/whitelist")
@perm_required("admin.whitelist")
def add_whitelist():
    name = valid_username(json_body().get("username")).lower()
    with storage.transaction("whitelist") as db_:
        if name not in db_["whitelist"]:
            db_["whitelist"].append(name)
    audit.log(g.user["username"], "whitelist_add", name)
    return jsonify({"message": f"{name} added to the whitelist."}), 201


@bp.delete("/whitelist/<username>")
@perm_required("admin.whitelist")
def remove_whitelist(username):
    with storage.transaction("whitelist") as db_:
        db_["whitelist"] = [n for n in db_["whitelist"] if n != username.lower()]
    audit.log(g.user["username"], "whitelist_remove", username.lower())
    return jsonify({"message": "Removed."})


# ------------------------------------------------------------------ groups and chats
@bp.get("/groups")
@perm_required("admin.groups")
def list_groups():
    return jsonify([{"id": gr["id"], "name": gr["name"], "join_mode": gr["join_mode"],
                     "member_count": len(gr["members"]), "created_by": gr["created_by"]}
                    for gr in storage.read("groups").values()])


@bp.get("/groups/<gid>/messages")
@perm_required("admin.groups")
def read_group(gid):
    """Stage 1 of the privacy rules: admins may read GROUP chats (members are told in the group info)."""
    group = storage.read("groups").get(gid)
    if not group:
        raise ApiError("Group not found.", 404)
    before = request.args.get("before", type=int)
    result = chat_service.fetch("group", gid, g.user, 100, before, ignore_clear=True)
    audit.log(g.user["username"], "view_group", f"{group['name']} (#{gid})")
    return jsonify(result)


@bp.post("/groups/<gid>/clear")
@perm_required("admin.groups")
def clear_group(gid):
    group = storage.read("groups").get(gid)
    if not group:
        raise ApiError("Group not found.", 404)
    chat_service.clear_for_all({"type": "group", "key": gid}, g.user)
    return jsonify({"message": "Group chat cleared."})


@bp.delete("/groups/<gid>")
@perm_required("admin.groups")
def delete_group(gid):
    with storage.transaction("groups", "invitations") as db_:
        group = db_["groups"].get(gid)
        if not group:
            raise ApiError("Group not found.", 404)
        del db_["groups"][gid]
        db_["invitations"] = [i for i in db_["invitations"] if i["group_id"] != gid]
    chat_service.purge_chat("group", gid)
    audit.log(g.user["username"], "delete_group", f"{group['name']} (#{gid})")
    return jsonify({"message": "Group deleted."})


@bp.post("/private-chats/clear")
@perm_required("admin.groups")
def clear_private():
    """Clearing a private chat does NOT require reading it."""
    data = json_body()
    users = storage.read("users")
    a, b = _target(users, data.get("user_a")), _target(users, data.get("user_b"))
    if a["username"] == b["username"]:
        raise ApiError("Pick two different people.")
    chat_service.clear_for_all({"type": "dm", "key": chat_service.dm_key(a["username"], b["username"])}, g.user)
    return jsonify({"message": "Private chat cleared."})


@bp.post("/private-chats/access")
@perm_required("chat.inspect")
def private_access():
    """Stage 3 ("emergency access"): reading a private chat needs a written reason.
    The two people see a notice in their chat and the access is written to the audit log. Never silent."""
    data = json_body()
    reason = clean_text(data.get("reason"), "Reason", 300)
    if len(reason) < 10:
        raise ApiError("Please give a real reason (at least 10 characters).")
    users = storage.read("users")
    a, b = _target(users, data.get("user_a")), _target(users, data.get("user_b"))
    if a["username"] == b["username"]:
        raise ApiError("Pick two different people.")
    for person in (a, b):          # you can only look into chats of people BELOW your rank (the Owner: everybody)
        if person["username"] != g.user["username"] and not perms.is_owner(g.user) and not perms.can_manage(g.user, person):
            raise ApiError("You can only open chats of people whose rank is below yours.", 403)
    key = chat_service.dm_key(a["username"], b["username"])
    before = request.args.get("before", type=int)
    if before is None:        # only the first page counts as "an access"; loading older messages does not repeat the notice
        chat_service.system_message("dm", key, g.user["username"],
                                    f"An admin ({g.user['display_name']}) viewed this chat. Reason: {reason}")
        audit.log(g.user["username"], "private_chat_access", f"{a['username']} + {b['username']}", reason)
    return jsonify(chat_service.fetch("dm", key, g.user, 200, before, ignore_clear=True))


# ------------------------------------------------------------------ overview, log, settings


@bp.get("/chat-overview")
@perm_required("chat.inspect")
def chat_overview():
    """Metadata only: WHO talks with WHOM and how much - no message text. Opening a chat needs a reason (see above)."""
    rows = db.query("SELECT chat_key, COUNT(*) AS n, MAX(created) AS last FROM messages WHERE chat_type = 'dm' "
                    "AND is_system = 0 GROUP BY chat_key ORDER BY last DESC LIMIT 200")
    users = storage.read("users")
    out = []
    for r in rows:
        parts = r["chat_key"].split("|")
        a, b = (find_user(users, p) for p in parts) if len(parts) == 2 else (None, None)
        if a and b:
            out.append({"user_a": a["username"], "user_b": b["username"], "name_a": a["display_name"],
                        "name_b": b["display_name"], "messages": r["n"], "last": r["last"]})
    return jsonify(out)


# ------------------------------------------------------------------ statistics, log, settings
STAT_LABELS = {
    "users": "Users (active)", "pending": "Waiting for approval", "ranks": "Accounts per rank", "messages": "Messages",
    "messages_24h": "Messages (24 h)", "groups": "Groups", "files": "Files", "storage_mb": "Storage used (MB)",
    "open_reports": "Open reports", "offers_open": "Open Pro offers", "coins_total": "Coins in circulation",
    "notes": "Notes", "tasks": "Tasks", "forum_posts": "Forum posts", "logins_24h": "Logins (24 h)"}


def _compute_stats(keys):
    users = list(storage.read("users").values())
    day = time.time() - 86400
    one = lambda sql, p=(): db.query(sql, p)[0]
    out = {}
    for key in keys:
        if key == "users":
            out[key] = sum(u["status"] == "active" for u in users)
        elif key == "pending":
            out[key] = sum(u["status"] == "pending" for u in users)
        elif key == "ranks":
            ranks = perms.all_ranks()
            out[key] = {r["name"]: sum(perms.base_rank_of(u, ranks)["id"] == r["id"] for u in users) for r in ranks.values()}
        elif key == "messages":
            out[key] = one("SELECT COUNT(*) AS n FROM messages WHERE is_system = 0")["n"]
        elif key == "messages_24h":
            out[key] = one("SELECT COUNT(*) AS n FROM messages WHERE is_system = 0 AND created > ?", (day,))["n"]
        elif key == "groups":
            out[key] = len(storage.read("groups"))
        elif key == "files":
            out[key] = one("SELECT COUNT(*) AS n FROM attachments WHERE status = 'ready'")["n"]
        elif key == "storage_mb":
            out[key] = round(one("SELECT COALESCE(SUM(size), 0) AS s FROM attachments WHERE status = 'ready'")["s"] / 1048576, 1)
        elif key == "open_reports":
            out[key] = one("SELECT COUNT(*) AS n FROM reports WHERE status = 'open'")["n"]
        elif key == "offers_open":
            out[key] = one("SELECT COUNT(*) AS n FROM offers WHERE status = 'open'")["n"]
        elif key == "coins_total":
            out[key] = one("SELECT COALESCE(SUM(coins), 0) AS s FROM wallets")["s"]
        elif key == "notes":
            out[key] = one("SELECT COUNT(*) AS n FROM notes")["n"]
        elif key == "tasks":
            out[key] = one("SELECT COUNT(*) AS n FROM tasks")["n"]
        elif key == "forum_posts":
            out[key] = one("SELECT COUNT(*) AS n FROM forum_posts")["n"]
        elif key == "logins_24h":
            out[key] = one("SELECT COUNT(*) AS n FROM login_log WHERE ok = 1 AND ts > ?", (day,))["n"]
    return out


@bp.get("/stats")
@perm_required("admin.stats")
def stats():
    """Admins see the statistics the Owner switched on; the Owner sees all of them."""
    from appsettings import STAT_KEYS
    keys = list(STAT_KEYS) if perms.is_owner(g.user) else appsettings.get()["stats"]["enabled"]
    return jsonify({"labels": {k: STAT_LABELS[k] for k in keys}, "values": _compute_stats(keys),
                    "storage_configured": objstore.enabled(), "all_keys": {k: STAT_LABELS[k] for k in STAT_KEYS}
                    if perms.is_owner(g.user) else None})


@bp.get("/audit")
@perm_required("admin.audit")
def audit_log():
    return jsonify(audit.recent(100, request.args.get("before", type=int)))


@bp.get("/settings")
@perm_required("admin.settings")
def get_settings():
    s = appsettings.get()
    loading = settings_module.effective_loading(None)
    owner_cfg = perms.has_perm(g.user, "owner.config")
    if not owner_cfg:                              # the Owner-only blocks are hidden from other admins
        s = {k: v for k, v in s.items() if k not in appsettings.OWNER_KEYS}
    return jsonify({"settings": s, "loading_preview": loading, "storage_configured": objstore.enabled(),
                    "presets": list(appsettings.PRESET_BACKGROUNDS), "owner_config": owner_cfg,
                    "stat_keys": STAT_LABELS})


@bp.put("/settings")
@perm_required("admin.settings")
def put_settings():
    clean = appsettings.validate(json_body())
    if any(k in appsettings.OWNER_KEYS for k in clean):
        need(g.user, "owner.config")
    if "default_rank" in clean:
        rank = perms.all_ranks().get(clean["default_rank"])
        if not rank or rank.get("is_owner") or rank["level"] >= 60:
            raise ApiError("New accounts can only start with a rank below the Mod level.")
    old = appsettings.get()["loading"]
    loading = clean.get("loading", {})
    for field, kind in (("image_asset", "loading_image"), ("music_asset", "loading_music")):
        if field in loading:
            settings_module.check_asset(loading[field], kind, g.user["username"])
    if "background" in clean and clean["background"].get("default") and \
            clean["background"]["default"] not in appsettings.PRESET_BACKGROUNDS:
        raise ApiError("Unknown background preset.")
    saved = appsettings.save(clean)
    for field in ("image_asset", "music_asset"):
        if field in loading and old[field] and old[field] != loading[field]:
            settings_module.release_asset(old[field])
    audit.log(g.user["username"], "change_settings", ", ".join(sorted(clean)))
    return jsonify({"settings": saved if perms.has_perm(g.user, "owner.config") else
                    {k: v for k, v in saved.items() if k not in appsettings.OWNER_KEYS}})


# ------------------------------------------------------------------ ranks (Owner) and the permission list
def _rank_view(r):
    return {**r, "perms": sorted(r.get("perms", []))}


@bp.get("/ranks")
@perm_required("admin.access")
def get_ranks():
    ranks = perms.all_ranks()
    users = storage.read("users").values()
    counts = {}
    for u in users:
        rid = perms.base_rank_of(u, ranks)["id"]
        counts[rid] = counts.get(rid, 0) + 1
    out = [{**_rank_view(r), "users": counts.get(r["id"], 0)} for r in sorted(ranks.values(), key=lambda r: r["level"])]
    can_edit = perms.has_perm(g.user, "owner.ranks")
    return jsonify({"ranks": out, "can_edit": can_edit, "designs": {d: perms.DESIGN_LABELS[d] for d in perms.DESIGNS},
                    "registry": [{"key": k, "label": l, "group": gr, "built": k not in perms.NOT_BUILT}
                                 for k, l, gr in perms.registry()]})


def _clean_rank(data, existing=None):
    name = clean_text(data.get("name"), "Rank name", 24)
    level = data.get("level")
    if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 99:
        raise ApiError("The level must be a whole number between 1 and 99 (100 is the Owner).")
    color = str(data.get("color") or "#888888")
    if not re.match(r"^#[0-9a-fA-F]{6}$", color):
        raise ApiError("The colour must look like #1a2b3c.")
    keys = data.get("perms")
    if not isinstance(keys, list) or any(k not in perms.all_keys() for k in keys):
        raise ApiError("Unknown permission in the list.")
    designs = data.get("designs", ["classic"])
    if not isinstance(designs, list) or any(d not in perms.DESIGNS for d in designs) or not designs:
        raise ApiError("Pick at least one valid design.")
    offered = data["offered"] if isinstance(data.get("offered"), bool) else (existing or {}).get("offered", True)
    perks = str(data.get("perks_text", (existing or {}).get("perks_text", ""))).strip()[:400]
    return {"name": name, "level": level, "color": color, "perms": sorted(set(keys)), "designs": [d for d in perms.DESIGNS if d in designs],
            "offered": offered, "perks_text": perks}


@bp.post("/ranks")
@perm_required("owner.ranks")
def create_rank():
    clean = _clean_rank(json_body())
    with storage.transaction("ranks") as db_:
        base = re.sub(r"[^a-z0-9]+", "_", clean["name"].lower()).strip("_") or "rank"
        rid, n = base, 2
        while rid in db_["ranks"]:
            rid, n = f"{base}_{n}", n + 1
        if any(r["name"].lower() == clean["name"].lower() for r in db_["ranks"].values()):
            raise ApiError("A rank with this name already exists.", 409)
        db_["ranks"][rid] = {"id": rid, **clean}
    audit.log(g.user["username"], "rank_create", rid)
    return jsonify({"id": rid}), 201


@bp.put("/ranks/<rid>")
@perm_required("owner.ranks")
def edit_rank(rid):
    data = json_body()
    with storage.transaction("ranks") as db_:
        rank = db_["ranks"].get(rid)
        if not rank:
            raise ApiError("Rank not found.", 404)
        if rank.get("is_owner"):             # the Owner rank can only be renamed / recoloured; it always has everything
            rank["name"] = clean_text(data.get("name"), "Rank name", 24)
            if re.match(r"^#[0-9a-fA-F]{6}$", str(data.get("color", ""))):
                rank["color"] = data["color"]
        else:
            if any(r["name"].lower() == str(data.get("name", "")).strip().lower() and r["id"] != rid for r in db_["ranks"].values()):
                raise ApiError("A rank with this name already exists.", 409)
            rank.update(_clean_rank(data, rank))
    audit.log(g.user["username"], "rank_edit", rid)
    return jsonify({"message": "Saved."})


@bp.delete("/ranks/<rid>")
@perm_required("owner.ranks")
def delete_rank(rid):
    ranks = perms.all_ranks()
    rank = ranks.get(rid)
    if not rank:
        raise ApiError("Rank not found.", 404)
    if rank.get("is_owner"):
        raise ApiError("The Owner rank cannot be deleted.", 403)
    fallback = perms.default_rank_id() if perms.default_rank_id() != rid else next(
        (r["id"] for r in sorted(ranks.values(), key=lambda r: r["level"]) if r["id"] != rid and not r.get("is_owner")), None)
    if not fallback:
        raise ApiError("There has to be at least one other rank.", 409)
    moved = 0
    with storage.transaction("ranks", "users") as db_:
        del db_["ranks"][rid]
        for u in db_["users"].values():
            if u.get("rank") == rid:
                u["rank"] = fallback
                moved += 1
            if (u.get("lease") or {}).get("rank") == rid:
                u.pop("lease", None)
    shop = appsettings.get()["shop"]
    if any(i["rank_id"] == rid for i in shop["items"]):
        appsettings.save({"shop": {"items": [i for i in shop["items"] if i["rank_id"] != rid]}})
    if appsettings.get()["default_rank"] == rid:
        appsettings.save({"default_rank": fallback})
    audit.log(g.user["username"], "rank_delete", rid, f"{moved} accounts moved to {fallback}")
    return jsonify({"message": f"Rank deleted. {moved} account(s) now have the rank {ranks[fallback]['name']}."})


# ------------------------------------------------------------------ permission requests (admin -> Owner)
@bp.post("/requests")
@perm_required("admin.request")
def send_request():
    data = json_body()
    key = data.get("perm")
    if key not in perms.all_keys():
        raise ApiError("Unknown permission.")
    if perms.has_perm(g.user, key):
        raise ApiError("You already have this permission.", 409)
    text = clean_text(data.get("text"), "Reason", 400)
    if db.query("SELECT 1 AS x FROM perm_requests WHERE from_user = ? AND perm = ? AND status = 'open'", (g.user["username"], key)):
        raise ApiError("You already asked for this permission.", 409)
    db.execute("INSERT INTO perm_requests (from_user, perm, text, created) VALUES (?, ?, ?, ?)",
               (g.user["username"], key, text, time.time()))
    notify.notify_perm("owner.requests", "request", f"{g.user['display_name']} asks for the permission {key}.", "#/admin")
    return jsonify({"message": "Your request was sent to the Owner."}), 201


@bp.get("/requests")
@perm_required("admin.request")
def list_requests():
    if perms.has_perm(g.user, "owner.requests"):
        rows = db.query("SELECT * FROM perm_requests ORDER BY (status = 'open') DESC, id DESC LIMIT 100")
    else:
        rows = db.query("SELECT * FROM perm_requests WHERE from_user = ? ORDER BY id DESC LIMIT 50", (g.user["username"],))
    return jsonify(rows)


@bp.post("/requests/<int:rid>/decide")
@perm_required("owner.requests")
def decide_request(rid):
    data = json_body()
    approve = data.get("approve")
    if not isinstance(approve, bool):
        raise ApiError("'approve' must be true or false.")
    answer = clean_text(data.get("answer"), "Answer", 300, required=False)
    rows = db.query("SELECT * FROM perm_requests WHERE id = ? AND status = 'open'", (rid,))
    if not rows:
        raise ApiError("Request not found.", 404)
    req = rows[0]
    if approve:
        with storage.transaction("users") as db_:
            target = find_user(db_["users"], req["from_user"])
            if target:
                extra = set(target.get("extra_perms", []))
                extra.add(req["perm"])
                target["extra_perms"] = sorted(extra)
    db.execute("UPDATE perm_requests SET status = ?, decided_by = ?, decided_at = ?, answer = ? WHERE id = ?",
               ("approved" if approve else "denied", g.user["username"], time.time(), answer, rid))
    notify.notify(req["from_user"], "request", f"Your request for {req['perm']} was {'approved' if approve else 'denied'}."
                  + (f" {answer}" if answer else ""), "#/admin")
    audit.log(g.user["username"], "request_approved" if approve else "request_denied", req["from_user"], req["perm"])
    return jsonify({"message": "Done."})


@bp.post("/users/<username>/extra-perms")
@perm_required("owner.requests")
def set_extra_perms(username):
    """The Owner can also hand out or take back single permissions directly (without a request)."""
    keys = json_body().get("perms")
    if not isinstance(keys, list) or any(k not in perms.all_keys() for k in keys):
        raise ApiError("Unknown permission in the list.")
    with storage.transaction("users") as db_:
        target = _target(db_["users"], username)
        target["extra_perms"] = sorted(set(keys))
    audit.log(g.user["username"], "extra_perms", username, ", ".join(sorted(set(keys))))
    return jsonify({"message": "Saved."})


# ------------------------------------------------------------------ Pro offers (admins)
@bp.get("/offers")
@perm_required("admin.offers")
def list_offers():
    status = request.args.get("status", "open")
    rows = db.query("SELECT * FROM offers WHERE status = ? ORDER BY id DESC LIMIT 100", ("open" if status == "open" else "closed",)) \
        if status in ("open", "closed") else db.query("SELECT * FROM offers ORDER BY id DESC LIMIT 100")
    users = storage.read("users")
    return jsonify([{**r, "name": (find_user(users, r["username"]) or {}).get("display_name", r["username"])} for r in rows])


@bp.post("/offers/<int:oid>/decide")
@perm_required("admin.offers")
def decide_offer(oid):
    data = json_body()
    accept = data.get("accept")
    if not isinstance(accept, bool):
        raise ApiError("'accept' must be true or false.")
    answer = clean_text(data.get("answer"), "Answer", 300, required=False)
    rows = db.query("SELECT * FROM offers WHERE id = ? AND status = 'open'", (oid,))
    if not rows:
        raise ApiError("Offer not found.", 404)
    offer = rows[0]
    reward = ""
    if accept and data.get("rank_id"):
        import economy
        ranks = perms.all_ranks()
        rank = _rank_for_assignment(data["rank_id"], ranks) if not perms.is_owner(g.user) else ranks.get(data["rank_id"])
        if not rank or rank.get("is_owner"):
            raise ApiError("Unknown rank.")
        days = data.get("days", 1)
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365:
            raise ApiError("Days must be between 1 and 365.")
        limit = 365 if perms.is_owner(g.user) else appsettings.get()["shop"]["gift_max_days"]
        if days > limit:
            raise ApiError(f"You can reward at most {limit} days.", 403)
        economy.give_lease(offer["username"], rank["id"], days, 365, g.user["username"])
        reward = f"{rank['name']} for {days} day(s)"
    db.execute("UPDATE offers SET status = ?, decided_by = ?, decided_at = ?, answer = ?, reward = ? WHERE id = ?",
               ("accepted" if accept else "declined", g.user["username"], time.time(), answer, reward, oid))
    notify.notify(offer["username"], "offer", f"Your offer was {'accepted' if accept else 'declined'}."
                  + (f" Reward: {reward}." if reward else "") + (f" {answer}" if answer else ""), "#/profile")
    audit.log(g.user["username"], "offer_accepted" if accept else "offer_declined", offer["username"], reward)
    return jsonify({"message": "Done."})
