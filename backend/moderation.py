"""Tools for moderators (and admins): reports and muting."""
import json
import time

from flask import Blueprint, g, jsonify, request

import audit
import chat_service
import db
import perms
import storage
from security import ApiError, find_user, json_body, perm_required

bp = Blueprint("moderation", __name__, url_prefix="/api/mod")


@bp.get("/reports")
@perm_required("mod.reports")
def list_reports():
    status = request.args.get("status", "open")
    rows = db.query("SELECT * FROM reports WHERE status = ? ORDER BY id DESC LIMIT 100", ("open" if status == "open" else "closed",))
    users = storage.read("users")
    out = []
    for r in rows:
        snap = json.loads(r["snapshot"])
        name = lambda u: (find_user(users, u) or {}).get("display_name", u)
        out.append({"id": r["id"], "message_id": r["message_id"], "reporter": name(r["reporter"]), "reason": r["reason"],
                    "created": r["created"], "status": r["status"], "handled_by": r["handled_by"],
                    "sender": snap["sender"], "sender_name": name(snap["sender"]), "chat_type": snap["chat_type"],
                    "context": [{**m, "sender_name": name(m["sender"]), "reported": m["id"] == r["message_id"]} for m in snap["context"]]})
    return jsonify(out)


@bp.post("/reports/<int:rid>/resolve")
@perm_required("mod.reports")
def resolve_report(rid):
    action = json_body().get("action")
    if action not in ("dismiss", "delete_message"):
        raise ApiError("Action must be 'dismiss' or 'delete_message'.")
    rows = db.query("SELECT * FROM reports WHERE id = ? AND status = 'open'", (rid,))
    if not rows:
        raise ApiError("Report not found.", 404)
    report = rows[0]
    if action == "delete_message" and report["message_id"]:
        existing = db.query("SELECT deleted FROM messages WHERE id = ?", (report["message_id"],))
        if existing and not existing[0]["deleted"]:
            chat_service.delete(report["message_id"], g.user)
    db.execute("UPDATE reports SET status = 'closed', handled_by = ?, handled_at = ? WHERE id = ?",
               (g.user["username"], time.time(), rid))
    audit.log(g.user["username"], f"report_{action}", f"report #{rid}")
    return jsonify({"message": "Report closed."})


@bp.post("/users/<username>/mute")
@perm_required("mod.mute")
def mute(username):
    minutes = json_body().get("minutes")
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 0 <= minutes <= 43200:
        raise ApiError("Minutes must be between 0 and 43200 (30 days). Use 0 to unmute.")
    with storage.transaction("users") as db_:
        target = find_user(db_["users"], username)
        if not target:
            raise ApiError("User not found.", 404)
        if not perms.can_manage(g.user, target):
            raise ApiError("You can't mute this person (their rank is not below yours).", 403)
        target["muted_until"] = time.time() + minutes * 60 if minutes else 0
    audit.log(g.user["username"], "mute" if minutes else "unmute", target["username"], f"{minutes} min" if minutes else "")
    return jsonify({"message": f"{target['username']} is muted for {minutes} minutes." if minutes else f"{target['username']} can write again."})
