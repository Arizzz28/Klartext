"""Global administration: approve/suspend users, edit the whitelist, remove groups."""
from flask import Blueprint, g, jsonify

import storage
from security import ApiError, admin_required, find_user, json_body, valid_username

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@bp.get("/users")
@admin_required
def list_users():
    users = storage.read("users").values()
    order = {"pending": 0, "active": 1, "banned": 2}
    result = [{"username": u["username"], "display_name": u["display_name"], "email": u["email"],
               "status": u["status"], "is_admin": u.get("is_admin", False)} for u in users]
    result.sort(key=lambda u: (order.get(u["status"], 3), u["username"].lower()))
    return jsonify(result)


def _set_status(username, status):
    with storage.transaction("users") as db:
        user = find_user(db["users"], username)
        if not user:
            raise ApiError("User not found.", 404)
        if user["username"] == g.user["username"]:
            raise ApiError("You cannot change your own account here.", 400)
        user["status"] = status
        user["token_version"] += 1      # kicks the user out of every device
    return jsonify({"message": f"{user['username']} is now {status}."})


@bp.post("/users/<username>/approve")
@admin_required
def approve(username):
    return _set_status(username, "active")


@bp.post("/users/<username>/suspend")
@admin_required
def suspend(username):
    return _set_status(username, "banned")


@bp.get("/whitelist")
@admin_required
def get_whitelist():
    return jsonify(sorted(storage.read("whitelist")))


@bp.post("/whitelist")
@admin_required
def add_whitelist():
    name = valid_username(json_body().get("username")).lower()
    with storage.transaction("whitelist") as db:
        if name not in db["whitelist"]:
            db["whitelist"].append(name)
    return jsonify({"message": f"{name} added to the whitelist."}), 201


@bp.delete("/whitelist/<username>")
@admin_required
def remove_whitelist(username):
    with storage.transaction("whitelist") as db:
        db["whitelist"] = [n for n in db["whitelist"] if n != username.lower()]
    return jsonify({"message": "Removed."})


@bp.get("/groups")
@admin_required
def list_groups():
    return jsonify([{"id": gr["id"], "name": gr["name"], "join_mode": gr["join_mode"],
                     "member_count": len(gr["members"]), "created_by": gr["created_by"]}
                    for gr in storage.read("groups").values()])


@bp.delete("/groups/<gid>")
@admin_required
def delete_group(gid):
    with storage.transaction("groups", "group_messages", "invitations") as db:
        if gid not in db["groups"]:
            raise ApiError("Group not found.", 404)
        del db["groups"][gid]
        db["group_messages"] = [m for m in db["group_messages"] if m["group_id"] != gid]
        db["invitations"] = [i for i in db["invitations"] if i["group_id"] != gid]
    return jsonify({"message": "Group deleted."})
