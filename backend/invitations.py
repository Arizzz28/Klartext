"""Group invitations. Rule: only group admins may invite; the invited user can accept or decline."""
import time

from flask import Blueprint, g, jsonify

import storage
from security import ApiError, find_user, json_body, login_required, public_user

bp = Blueprint("invitations", __name__, url_prefix="/api")


@bp.post("/groups/<gid>/invitations")
@login_required
def invite(gid):
    username = json_body().get("username")
    with storage.transaction("users", "groups", "invitations") as db:
        group = db["groups"].get(gid)
        if not group:
            raise ApiError("Group not found.", 404)
        if group["members"].get(g.user["username"]) != "admin":
            raise ApiError("Only group admins can invite people.", 403)
        target = find_user(db["users"], username)
        if not target or target["status"] != "active":
            raise ApiError("User not found.", 404)
        if target["username"] in group["members"]:
            raise ApiError("That user is already in this group.", 409)
        if any(i["group_id"] == gid and i["to"] == target["username"] and i["status"] == "pending"
               for i in db["invitations"]):
            raise ApiError("That user already has a pending invitation.", 409)
        db["invitations"].append({"id": storage.next_id(db["invitations"]), "group_id": gid,
                                  "from": g.user["username"], "to": target["username"],
                                  "status": "pending", "ts": time.time()})
    return jsonify({"message": f"Invitation sent to {target['username']}."}), 201


@bp.get("/invitations")
@login_required
def my_invitations():
    groups = storage.read("groups")
    users = storage.read("users")
    result = []
    for inv in storage.read("invitations"):
        group = groups.get(inv["group_id"])
        if inv["to"] == g.user["username"] and inv["status"] == "pending" and group:
            inviter = find_user(users, inv["from"])
            result.append({"id": inv["id"], "ts": inv["ts"],
                           "group": {"id": group["id"], "name": group["name"], "avatar": group["avatar"]},
                           "from": public_user(inviter) if inviter else {"username": inv["from"], "display_name": inv["from"], "avatar": ""}})
    return jsonify(result)


def _answer(iid, accept):
    with storage.transaction("groups", "invitations") as db:
        inv = next((i for i in db["invitations"] if i["id"] == iid), None)
        if not inv or inv["to"] != g.user["username"] or inv["status"] != "pending":
            raise ApiError("Invitation not found.", 404)
        group = db["groups"].get(inv["group_id"])
        if accept:
            if not group:
                raise ApiError("This group no longer exists.", 404)
            group["members"].setdefault(g.user["username"], "member")
        inv["status"] = "accepted" if accept else "declined"
    return {"group_id": inv["group_id"]}


@bp.post("/invitations/<int:iid>/accept")
@login_required
def accept(iid):
    return jsonify(_answer(iid, True))


@bp.post("/invitations/<int:iid>/decline")
@login_required
def decline(iid):
    return jsonify(_answer(iid, False))
