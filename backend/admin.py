"""Global administration (admins only): users, roles, groups, private-chat access, stats, audit log, settings."""
import secrets
import time

from flask import Blueprint, g, jsonify, request

import appsettings
import audit
import chat_service
import db
import objstore
import settings as settings_module
import storage
from security import (ApiError, ROLES, admin_required, clean_text, find_user, hash_password, is_super_admin,
                      json_body, public_user, role_of, valid_email, valid_password, valid_username)

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _view(u):
    return {"username": u["username"], "display_name": u["display_name"], "email": u["email"], "status": u["status"],
            "role": role_of(u), "is_admin": role_of(u) == "admin", "is_super_admin": is_super_admin(u),
            "must_change_password": bool(u.get("must_change_password")), "muted_until": u.get("muted_until", 0),
            "created": u.get("created", 0)}


def _target(users, username):
    user = find_user(users, username)
    if not user:
        raise ApiError("User not found.", 404)
    return user


def _protect(target):
    if target["username"] == g.user["username"]:
        raise ApiError("You can't do this to your own account here.", 400)
    if is_super_admin(target):
        raise ApiError("The main admin account is protected.", 403)


# ------------------------------------------------------------------ users
@bp.get("/users")
@admin_required
def list_users():
    order = {"pending": 0, "active": 1, "banned": 2}
    result = [_view(u) for u in storage.read("users").values()]
    result.sort(key=lambda u: (order.get(u["status"], 3), u["username"].lower()))
    return jsonify(result)


@bp.post("/users")
@admin_required
def create_user():
    data = json_body()
    username = valid_username(data.get("username"))
    email = valid_email(data.get("email"))
    role = data.get("role", "user")
    if role not in ROLES:
        raise ApiError("Role must be user, moderator or admin.")
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
            "avatar": "", "role": role, "is_admin": role == "admin", "status": "active",
            "must_change_password": must_change, "token_version": 0, "created": time.time()}
        created = db_["users"][username.lower()]
    audit.log(g.user["username"], "create_user", username, f"role {role}")
    return jsonify({"user": _view(created), "generated_password": generated}), 201


@bp.patch("/users/<username>")
@admin_required
def edit_user(username):
    data = json_body()
    with storage.transaction("users") as db_:
        target = _target(db_["users"], username)
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
        if "role" in data:
            if data["role"] not in ROLES:
                raise ApiError("Role must be user, moderator or admin.")
            _protect(target)
            target["role"] = data["role"]
            target["is_admin"] = data["role"] == "admin"
            changes.append(f"role {data['role']}")
        result = _view(target)
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
@admin_required
def approve(username):
    return _set_status(username, "active")


@bp.post("/users/<username>/suspend")
@admin_required
def suspend(username):
    return _set_status(username, "banned")


@bp.post("/users/<username>/reset-password")
@admin_required
def reset_password(username):
    password = (request.get_json(silent=True) or {}).get("password")     # body is optional
    generated = None
    if password:
        valid_password(password)
    else:
        password = generated = secrets.token_urlsafe(9)
    with storage.transaction("users") as db_:
        target = _target(db_["users"], username)
        if is_super_admin(target) and target["username"] != g.user["username"]:
            raise ApiError("The main admin account is protected.", 403)
        target["password_hash"] = hash_password(password)
        target["must_change_password"] = True
        target["token_version"] += 1
    audit.log(g.user["username"], "reset_password", target["username"])
    return jsonify({"message": f"New password set for {target['username']}. They must change it at the next login.",
                    "generated_password": generated})


@bp.post("/users/<username>/logout-all")
@admin_required
def logout_all(username):
    with storage.transaction("users") as db_:
        target = _target(db_["users"], username)
        target["token_version"] += 1
    audit.log(g.user["username"], "logout_all", target["username"])
    return jsonify({"message": f"{target['username']} was logged out everywhere."})


@bp.post("/users/<username>/delete")
@admin_required
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
        for gid, group in list(db_["groups"].items()):
            if name not in group["members"]:
                continue
            was_only_admin = group["members"][name] == "admin" and sum(r == "admin" for r in group["members"].values()) == 1
            del group["members"][name]
            if not group["members"]:
                del db_["groups"][gid]
                purge_groups.append(gid)
            elif was_only_admin:
                group["members"][next(iter(group["members"]))] = "admin"      # ownership goes to the next member
        db_["invitations"] = [i for i in db_["invitations"] if name not in (i["from"], i["to"])]
        del db_["users"][name.lower()]
    chat_service.purge_user(name, delete_group_messages)
    for gid in purge_groups:
        chat_service.purge_chat("group", gid)
    audit.log(g.user["username"], "delete_user", name, "group messages deleted" if delete_group_messages else "group messages kept")
    return jsonify({"message": f"{name} was deleted."})


# ------------------------------------------------------------------ whitelist
@bp.get("/whitelist")
@admin_required
def get_whitelist():
    return jsonify(sorted(storage.read("whitelist")))


@bp.post("/whitelist")
@admin_required
def add_whitelist():
    name = valid_username(json_body().get("username")).lower()
    with storage.transaction("whitelist") as db_:
        if name not in db_["whitelist"]:
            db_["whitelist"].append(name)
    audit.log(g.user["username"], "whitelist_add", name)
    return jsonify({"message": f"{name} added to the whitelist."}), 201


@bp.delete("/whitelist/<username>")
@admin_required
def remove_whitelist(username):
    with storage.transaction("whitelist") as db_:
        db_["whitelist"] = [n for n in db_["whitelist"] if n != username.lower()]
    audit.log(g.user["username"], "whitelist_remove", username.lower())
    return jsonify({"message": "Removed."})


# ------------------------------------------------------------------ groups and chats
@bp.get("/groups")
@admin_required
def list_groups():
    return jsonify([{"id": gr["id"], "name": gr["name"], "join_mode": gr["join_mode"],
                     "member_count": len(gr["members"]), "created_by": gr["created_by"]}
                    for gr in storage.read("groups").values()])


@bp.get("/groups/<gid>/messages")
@admin_required
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
@admin_required
def clear_group(gid):
    group = storage.read("groups").get(gid)
    if not group:
        raise ApiError("Group not found.", 404)
    chat_service.clear_for_all({"type": "group", "key": gid}, g.user)
    return jsonify({"message": "Group chat cleared."})


@bp.delete("/groups/<gid>")
@admin_required
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
@admin_required
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
@admin_required
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
    key = chat_service.dm_key(a["username"], b["username"])
    before = request.args.get("before", type=int)
    if before is None:        # only the first page counts as "an access"; loading older messages does not repeat the notice
        chat_service.system_message("dm", key, g.user["username"],
                                    f"An admin ({g.user['display_name']}) viewed this chat. Reason: {reason}")
        audit.log(g.user["username"], "private_chat_access", f"{a['username']} + {b['username']}", reason)
    return jsonify(chat_service.fetch("dm", key, g.user, 200, before, ignore_clear=True))


# ------------------------------------------------------------------ overview, log, settings
@bp.get("/stats")
@admin_required
def stats():
    users = list(storage.read("users").values())
    day = time.time() - 86400
    messages = db.query("SELECT COUNT(*) AS n FROM messages WHERE is_system = 0")[0]["n"]
    today = db.query("SELECT COUNT(*) AS n FROM messages WHERE is_system = 0 AND created > ?", (day,))[0]["n"]
    files = db.query("SELECT COUNT(*) AS n, COALESCE(SUM(size), 0) AS s FROM attachments WHERE status = 'ready'")[0]
    return jsonify({
        "users": {"total": len(users), "active": sum(u["status"] == "active" for u in users),
                  "pending": sum(u["status"] == "pending" for u in users), "suspended": sum(u["status"] == "banned" for u in users)},
        "roles": {r: sum(role_of(u) == r for u in users) for r in ROLES},
        "groups": len(storage.read("groups")), "messages": messages, "messages_24h": today,
        "files": files["n"], "storage_mb": round(files["s"] / (1024 * 1024), 1),
        "open_reports": db.query("SELECT COUNT(*) AS n FROM reports WHERE status = 'open'")[0]["n"],
        "storage_configured": objstore.enabled()})


@bp.get("/audit")
@admin_required
def audit_log():
    return jsonify(audit.recent(100, request.args.get("before", type=int)))


@bp.get("/settings")
@admin_required
def get_settings():
    s = appsettings.get()
    loading = settings_module.effective_loading(None)
    return jsonify({"settings": s, "loading_preview": loading, "storage_configured": objstore.enabled(),
                    "presets": list(appsettings.PRESET_BACKGROUNDS)})


@bp.put("/settings")
@admin_required
def put_settings():
    clean = appsettings.validate(json_body())
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
    return jsonify({"settings": saved})
