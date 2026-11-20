"""Groups: create, join, leave, manage members, group messages.
Every permission is checked here on the server - the frontend only hides buttons."""
import time

from flask import Blueprint, g, jsonify, request

import config
import storage
from security import (ApiError, clean_avatar, clean_text, find_user, json_body, login_required,
                      public_user)

bp = Blueprint("groups", __name__, url_prefix="/api/groups")


def _role(group, username):
    return group["members"].get(username)


def _summary(group, me, last=None):
    return {"id": group["id"], "name": group["name"], "description": group["description"],
            "avatar": group["avatar"], "join_mode": group["join_mode"],
            "member_count": len(group["members"]), "role": _role(group, me), "last": last}


def _get_group(db, gid):
    group = db["groups"].get(gid)
    if not group:
        raise ApiError("Group not found.", 404)
    return group


def _need_member(group):
    if not _role(group, g.user["username"]):
        raise ApiError("You are not a member of this group.", 403)


def _need_admin(group):
    if _role(group, g.user["username"]) != "admin":
        raise ApiError("Only group admins can do this.", 403)


def _new_id(groups):
    return str(max([int(k) for k in groups] + [0]) + 1)


@bp.get("")
@login_required
def my_groups():
    me = g.user["username"]
    groups = storage.read("groups")
    last = {}
    for m in storage.read("group_messages"):
        last[m["group_id"]] = {"text": m["text"], "ts": m["ts"], "from": m["from"]}
    mine = [_summary(gr, me, last.get(gr["id"])) for gr in groups.values() if _role(gr, me)]
    mine.sort(key=lambda s: (s["last"] or {"ts": 0})["ts"], reverse=True)
    return jsonify(mine)


@bp.get("/discover")
@login_required
def discover():
    me = g.user["username"]
    groups = storage.read("groups").values()
    return jsonify([_summary(gr, me) for gr in groups if gr["join_mode"] == "open" and not _role(gr, me)])


@bp.post("")
@login_required
def create_group():
    data = json_body()
    name = clean_text(data.get("name"), "Group name", 40)
    description = clean_text(data.get("description"), "Description", 200, required=False)
    join_mode = data.get("join_mode")
    if join_mode not in ("open", "invite_only"):
        raise ApiError("Join mode must be 'open' or 'invite_only'.")
    avatar = clean_avatar(data.get("avatar"))
    with storage.transaction("groups") as db:
        gid = _new_id(db["groups"])
        db["groups"][gid] = {"id": gid, "name": name, "description": description, "avatar": avatar,
                             "join_mode": join_mode, "created_by": g.user["username"],
                             "created": time.time(), "members": {g.user["username"]: "admin"}}
        result = _summary(db["groups"][gid], g.user["username"])
    return jsonify(result), 201


@bp.get("/<gid>")
@login_required
def group_details(gid):
    group = _get_group({"groups": storage.read("groups")}, gid)
    _need_member(group)
    users = storage.read("users")
    members = []
    for username, role in group["members"].items():
        user = find_user(users, username)
        if user:
            members.append({**public_user(user), "role": role})
    members.sort(key=lambda m: (m["role"] != "admin", m["display_name"].lower()))
    return jsonify({**_summary(group, g.user["username"]), "created_by": group["created_by"], "members": members})


@bp.patch("/<gid>")
@login_required
def update_group(gid):
    data = json_body()
    with storage.transaction("groups") as db:
        group = _get_group(db, gid)
        _need_admin(group)
        if "name" in data:
            group["name"] = clean_text(data["name"], "Group name", 40)
        if "description" in data:
            group["description"] = clean_text(data["description"], "Description", 200, required=False)
        if "avatar" in data:
            group["avatar"] = clean_avatar(data["avatar"])
        result = _summary(group, g.user["username"])
    return jsonify(result)


@bp.post("/<gid>/join")
@login_required
def join_group(gid):
    with storage.transaction("groups") as db:
        group = _get_group(db, gid)
        if _role(group, g.user["username"]):
            raise ApiError("You are already in this group.", 409)
        if group["join_mode"] != "open":
            raise ApiError("This group is invite-only.", 403)
        group["members"][g.user["username"]] = "member"
    return jsonify({"message": "Joined."})


@bp.post("/<gid>/leave")
@login_required
def leave_group(gid):
    me = g.user["username"]
    with storage.transaction("groups", "group_messages", "invitations") as db:
        group = _get_group(db, gid)
        _need_member(group)
        admins = [u for u, r in group["members"].items() if r == "admin"]
        if len(group["members"]) == 1:        # last person: the group disappears
            del db["groups"][gid]
            db["group_messages"] = [m for m in db["group_messages"] if m["group_id"] != gid]
            db["invitations"] = [i for i in db["invitations"] if i["group_id"] != gid]
        elif admins == [me]:
            raise ApiError("You are the last admin. Make someone else an admin before leaving.", 409)
        else:
            del group["members"][me]
    return jsonify({"message": "You left the group."})


@bp.post("/<gid>/members/<username>/remove")
@login_required
def remove_member(gid, username):
    with storage.transaction("groups") as db:
        group = _get_group(db, gid)
        _need_admin(group)
        target = find_user(storage.read("users"), username)
        name = target["username"] if target else username
        if name == g.user["username"]:
            raise ApiError("Use 'Leave group' to leave.")
        if name not in group["members"]:
            raise ApiError("That user is not in this group.", 404)
        del group["members"][name]
    return jsonify({"message": "Member removed."})


@bp.post("/<gid>/members/<username>/promote")
@login_required
def promote_member(gid, username):
    with storage.transaction("groups") as db:
        group = _get_group(db, gid)
        _need_admin(group)
        target = find_user(storage.read("users"), username)
        name = target["username"] if target else username
        if name not in group["members"]:
            raise ApiError("That user is not in this group.", 404)
        group["members"][name] = "admin"
    return jsonify({"message": "Member is now an admin."})


@bp.get("/<gid>/messages")
@login_required
def get_group_messages(gid):
    _need_member(_get_group({"groups": storage.read("groups")}, gid))
    after = request.args.get("after", 0, type=int)
    msgs = [m for m in storage.read("group_messages") if m["group_id"] == gid and m["id"] > after]
    return jsonify([{"id": m["id"], "from": m["from"], "text": m["text"], "ts": m["ts"]} for m in msgs])


@bp.post("/<gid>/messages")
@login_required
def send_group_message(gid):
    text = clean_text(json_body().get("text"), "Message", config.MAX_MESSAGE_LENGTH)
    with storage.transaction("groups", "group_messages") as db:
        _need_member(_get_group(db, gid))
        msg = {"id": storage.next_id(db["group_messages"]), "group_id": gid,
               "from": g.user["username"], "text": text, "ts": time.time()}
        db["group_messages"].append(msg)
    return jsonify({"id": msg["id"], "from": msg["from"], "text": msg["text"], "ts": msg["ts"]}), 201
