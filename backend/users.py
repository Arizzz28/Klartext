"""Profiles, personal preferences (design, tabs, layout), consent to the legal texts, profile visitors."""
import time

from flask import Blueprint, g, jsonify, request

import appsettings
import audit
import db
import legalconf
import perms
import storage
from security import (ApiError, check_password, clean_avatar, clean_text, find_user, hash_password, json_body,
                      login_required, me_view, need, perm_required, public_user, valid_password)

bp = Blueprint("users", __name__, url_prefix="/api")

# Which pages exist is defined in ONE place: frontend/tabs.js. The server only checks that a name looks like a name,
# so adding a page never needs a change here (the frontend ignores names it does not know).


@bp.get("/me")
@login_required
def get_me():
    return jsonify(me_view(g.user))


@bp.patch("/me")
@login_required
def update_me():
    data = json_body()
    with storage.transaction("users") as db_:
        user = db_["users"][g.user["username"].lower()]
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
    with storage.transaction("users") as db_:
        user = db_["users"][g.user["username"].lower()]
        if not check_password(user["password_hash"], str(data.get("current", ""))):
            raise ApiError("Your current password is wrong.", 403)
        user["password_hash"] = hash_password(new_password)
        user["token_version"] += 1          # logs out all other devices
        user["must_change_password"] = False
    return jsonify({"message": "Password changed. Please log in again."})


# ---------------------------------------------------------------- legal texts
@bp.get("/legal")
def legal_info():
    """Public: versions of the texts and the operator data the Owner entered (empty = not filled in yet)."""
    legal = appsettings.get()["legal"]
    return jsonify({"terms_version": legalconf.TERMS_VERSION, "privacy_version": legalconf.PRIVACY_VERSION,
                    "operator": {k: legal.get(k, "") for k in ("operator_name", "operator_address", "operator_email",
                                                              "operator_phone", "min_age", "note")}})


@bp.post("/me/consent")
@login_required
def give_consent():
    data = json_body()
    if data.get("terms") is not True or data.get("privacy") is not True:
        raise ApiError("You have to accept both the Terms of Service and the Privacy Policy.")
    if data.get("terms_version") != legalconf.TERMS_VERSION or data.get("privacy_version") != legalconf.PRIVACY_VERSION:
        raise ApiError("The texts were updated. Please reload the page and read them again.", 409)
    with storage.transaction("users") as db_:
        user = db_["users"][g.user["username"].lower()]
        user["consent"] = legalconf.consent_record()
        result = me_view(user)
    return jsonify(result)


# ---------------------------------------------------------------- preferences
@bp.put("/me/prefs")
@login_required
def put_prefs():
    data = json_body()
    user = g.user
    changes = {}
    if "design" in data:
        need(user, "design.change")
        if data["design"] not in perms.allowed_designs(user):
            raise ApiError("Your rank doesn't include this design.", 403)
        changes["design"] = data["design"]
    if "tabs" in data:
        need(user, "tabs.editor")
        tabs = data["tabs"]
        if (not isinstance(tabs, list) or len(tabs) > 40 or len(set(map(str, tabs))) != len(tabs)
                or not all(isinstance(t, str) and appsettings.TAB_ID_RE.match(t) for t in tabs)):
            raise ApiError("Invalid tab list.")
        changes["tabs"] = tabs
    if "bubble" in data:
        need(user, "tabs.bubble")
        b = data["bubble"]
        if not isinstance(b, dict):
            raise ApiError("Invalid bubble settings.")
        pos = b.get("pos")
        ok_pos = isinstance(pos, dict) and all(isinstance(pos.get(k), (int, float)) and 0 <= pos[k] <= 1 for k in ("x", "y"))
        changes["bubble"] = {"on": bool(b.get("on", True)), "pos": {"x": float(pos["x"]), "y": float(pos["y"])} if ok_pos else {"x": 0.9, "y": 0.8}}
    if "use_pc" in data:                           # send my requests to the Owner's PC while it is online
        need(user, "pc.backend")
        changes["use_pc"] = bool(data["use_pc"])
    if "windows" in data:                          # desktop mode: tabs open as movable windows
        need(user, "layout.windows")
        if not isinstance(data["windows"], dict):
            raise ApiError("Invalid window settings.")
        changes["windows"] = {"on": bool(data["windows"].get("on"))}
    if "layout" in data:
        need(user, "layout.move")
        lay = data["layout"]
        if not isinstance(lay, dict) or lay.get("side", "left") not in ("left", "right") or lay.get("list_side", "inner") not in ("inner", "outer"):
            raise ApiError("Invalid layout.")
        width = lay.get("list_width", 330)
        if isinstance(width, bool) or not isinstance(width, int) or not 220 <= width <= 520:
            raise ApiError("The list width must be between 220 and 520.")
        changes["layout"] = {"side": lay.get("side", "left"), "list_side": lay.get("list_side", "inner"),
                             "list_width": width, "rail": bool(lay.get("rail", False))}
    if "widgets" in data:
        need(user, "tabs.widgets")
        w = data["widgets"]
        if not isinstance(w, list) or len(w) > 12 or any(x not in WIDGETS for x in w):
            raise ApiError("Unknown widget.")
        changes["widgets"] = w
    if "start_page" in data:                       # everybody may choose where the app opens ("" = use the default)
        changes["start_page"] = "" if data["start_page"] == "" else appsettings.valid_tab_id(data["start_page"])
    if "push_preview" in data:
        need(user, "push.use")
        changes["push_preview"] = bool(data["push_preview"])
    if not changes:
        raise ApiError("Nothing to change.")
    with storage.transaction("users") as db_:
        u = db_["users"][user["username"].lower()]
        u.setdefault("prefs", {}).update(changes)
        result = me_view(u)
    return jsonify(result)


WIDGETS = ("clock", "unread", "coins", "tasks_today", "next_event", "mission_progress", "visitors", "quote")


# ---------------------------------------------------------------- people
@bp.get("/users")
@login_required
def list_users():
    query = request.args.get("q", "").strip().lower()[:40]
    users = storage.read("users").values()
    ranks = perms.all_ranks()
    result = [public_user(u, ranks) for u in users
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
    _record_visit(g.user, user)
    return jsonify(public_user(user))


def _record_visit(visitor, visited):
    """Remembers who looked at a profile (at most once per hour per person)."""
    if visitor["username"] == visited["username"] or not appsettings.get()["visitors"]["enabled"]:
        return
    now = time.time()
    if db.query("SELECT 1 AS x FROM profile_visits WHERE visited = ? AND visitor = ? AND ts > ?",
                (visited["username"], visitor["username"], now - 3600)):
        return
    db.execute("INSERT INTO profile_visits (visited, visitor, ts) VALUES (?, ?, ?)",
               (visited["username"], visitor["username"], now))
    keep = appsettings.get()["visitors"]["keep_days"] * 86400
    db.execute("DELETE FROM profile_visits WHERE ts < ?", (now - keep,))


@bp.get("/me/visitors")
@perm_required("tabs.visitors")
def my_visitors():
    rows = db.query("SELECT visitor, ts FROM profile_visits WHERE visited = ? ORDER BY ts DESC LIMIT 100", (g.user["username"],))
    users = storage.read("users")
    out = []
    for r in rows:
        u = find_user(users, r["visitor"])
        if u:
            out.append({**public_user(u), "ts": r["ts"]})
    return jsonify({"enabled": appsettings.get()["visitors"]["enabled"],
                    "keep_days": appsettings.get()["visitors"]["keep_days"], "visitors": out})
