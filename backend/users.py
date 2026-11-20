"""Profiles and user search."""
from flask import Blueprint, g, jsonify, request

import storage
from security import (ApiError, check_password, clean_avatar, clean_text, find_user, hash_password,
                      json_body, login_required, me_view, public_user, valid_password)

bp = Blueprint("users", __name__, url_prefix="/api")


@bp.get("/me")
@login_required
def get_me():
    return jsonify(me_view(g.user))


@bp.patch("/me")
@login_required
def update_me():
    data = json_body()
    with storage.transaction("users") as db:
        user = db["users"][g.user["username"].lower()]
        if "display_name" in data:
            user["display_name"] = clean_text(data["display_name"], "Display name", 40)
        if "avatar" in data:
            user["avatar"] = clean_avatar(data["avatar"])
        result = me_view(user)
    return jsonify(result)


@bp.post("/me/password")
@login_required
def change_password():
    data = json_body()
    new_password = valid_password(data.get("new"))
    with storage.transaction("users") as db:
        user = db["users"][g.user["username"].lower()]
        if not check_password(user["password_hash"], str(data.get("current", ""))):
            raise ApiError("Your current password is wrong.", 403)
        user["password_hash"] = hash_password(new_password)
        user["token_version"] += 1          # logs out all other devices
    return jsonify({"message": "Password changed. Please log in again."})


@bp.get("/users")
@login_required
def list_users():
    query = request.args.get("q", "").strip().lower()[:40]
    users = storage.read("users").values()
    result = [public_user(u) for u in users
              if u["status"] == "active" and u["username"] != g.user["username"]
              and (not query or query in u["username"].lower() or query in u["display_name"].lower())]
    result.sort(key=lambda u: u["display_name"].lower())
    return jsonify(result[:50])


@bp.get("/users/<username>")
@login_required
def get_user(username):
    user = find_user(storage.read("users"), username)
    if not user or user["status"] != "active":
        raise ApiError("User not found.", 404)
    return jsonify(public_user(user))
