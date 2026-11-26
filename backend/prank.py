"""Pranks: harmless surprises between friends - ONLY for people who switched them on themselves.

Safety rules (they cannot be bypassed by the sender):
- the receiver must have switched "Allow pranks" on (default: off), and may switch it off at any time
- only the fixed kinds below exist (no own pictures or sounds), and every prank has a dismiss button
- limits: 1 prank per receiver per 5 minutes from the same sender, 10 per sender per hour
- the receiver sees WHO sent it; admins can see the log (audit) and can take the permission away
"""
import time

from flask import Blueprint, g, jsonify

import audit
import db
import notify
import perms
import storage
from security import ApiError, find_user, json_body, perm_required

bp = Blueprint("prank", __name__, url_prefix="/api/prank")
KINDS = {"jumpscare": "Jumpscare (a short surprise face)", "confetti": "Confetti", "shake": "Shaking screen", "message": "Big silly message"}


@bp.get("")
@perm_required("tabs.prank")
def state():
    me = g.user["username"]
    row = db.query("SELECT enabled FROM prank_optin WHERE username = ?", (me,))
    return jsonify({"kinds": KINDS, "enabled": bool(row and row[0]["enabled"]), "can_send": perms.has_perm(g.user, "prank.send")})


@bp.put("/optin")
@perm_required("tabs.prank")
def optin():
    on = 1 if json_body().get("enabled") is True else 0
    db.execute("INSERT INTO prank_optin (username, enabled) VALUES (?, ?) ON CONFLICT (username) DO UPDATE SET enabled = ?", (g.user["username"], on, on))
    return jsonify({"enabled": bool(on)})


@bp.get("/targets")
@perm_required("prank.send")
def targets():
    allowed = {r["username"] for r in db.query("SELECT username FROM prank_optin WHERE enabled = 1")}
    users = storage.read("users")
    return jsonify([{"username": u["username"], "display_name": u["display_name"]} for u in users.values()
                    if u["username"] in allowed and u["status"] == "active" and u["username"] != g.user["username"]])


@bp.post("/send")
@perm_required("prank.send")
def send():
    data = json_body()
    kind = data.get("kind")
    if kind not in KINDS:
        raise ApiError("Unknown prank.")
    target = find_user(storage.read("users"), data.get("to"))
    if not target or target["status"] != "active":
        raise ApiError("User not found.", 404)
    me = g.user["username"]
    ok = db.query("SELECT enabled FROM prank_optin WHERE username = ?", (target["username"],))
    if not ok or not ok[0]["enabled"]:
        raise ApiError("This person has not allowed pranks.", 403)
    now = time.time()
    if db.query("SELECT 1 AS x FROM prank_inbox WHERE to_user = ? AND from_user = ? AND created > ?", (target["username"], me, now - 300)):
        raise ApiError("Wait a few minutes before the next prank for the same person.", 429)
    if db.query("SELECT COUNT(*) AS c FROM prank_inbox WHERE from_user = ? AND created > ?", (me, now - 3600))[0]["c"] >= 10:
        raise ApiError("You sent many pranks this hour. Take a break.", 429)
    db.execute("INSERT INTO prank_inbox (to_user, from_user, kind, created, seen) VALUES (?, ?, ?, ?, 0)", (target["username"], me, kind, now))
    audit.log(me, "prank.send", target["username"], kind)
    return jsonify({"message": f"Prank sent to {target['display_name']}."})


@bp.get("/inbox")
@perm_required("tabs.prank")
def inbox():
    """The browser asks every so often. Returns at most one waiting prank (and only if the person still allows them)."""
    me = g.user["username"]
    ok = db.query("SELECT enabled FROM prank_optin WHERE username = ?", (me,))
    if not ok or not ok[0]["enabled"]:
        return jsonify({"prank": None})
    rows = db.query("SELECT id, from_user, kind FROM prank_inbox WHERE to_user = ? AND seen = 0 AND created > ? ORDER BY id LIMIT 1", (me, time.time() - 600))
    if not rows:
        return jsonify({"prank": None})
    db.execute("UPDATE prank_inbox SET seen = 1 WHERE id = ?", (rows[0]["id"],))
    u = find_user(storage.read("users"), rows[0]["from_user"])
    return jsonify({"prank": {"kind": rows[0]["kind"], "from": u["display_name"] if u else rows[0]["from_user"]}})
