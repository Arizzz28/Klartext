"""What's New (release notes with a per-person 'seen' mark) and optional ads / videos controlled by the Owner."""
import re
import time
from urllib.parse import urlparse

from flask import Blueprint, g, jsonify

import appsettings
import audit
import db
from security import ApiError, clean_text, json_body, login_required, perm_required

bp = Blueprint("extras", __name__, url_prefix="/api")
RELEASE_ID = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,19}$")


# ---------------------------------------------------------------- What's New
def seed_release():
    if db.query("SELECT 1 AS x FROM releases LIMIT 1"):
        return
    db.execute("INSERT INTO releases (id, title, body, created, created_by) VALUES (?, ?, ?, ?, ?)",
               ("3.0.0", "Chatisfying 3.0",
                "Ranks and permissions, five design modes, a floating tab bubble, unread counters, push messages, "
                "missions and coins, calendar, tasks, notes, search, music links, forum, games and an AI helper. "
                "New: please read and accept the Terms of Service and the Privacy Policy.",
                time.time(), "system"))


def unseen_count(username):
    return db.query("SELECT COUNT(*) AS n FROM releases WHERE id NOT IN (SELECT release_id FROM release_seen WHERE username = ?)",
                    (username,))[0]["n"]


@bp.get("/releases")
@login_required
def releases():
    rows = db.query("SELECT * FROM releases ORDER BY created DESC LIMIT 30")
    seen = {r["release_id"] for r in db.query("SELECT release_id FROM release_seen WHERE username = ?", (g.user["username"],))}
    return jsonify([{**r, "seen": r["id"] in seen} for r in rows])


@bp.post("/releases/seen")
@login_required
def mark_seen():
    """Marks ALL current entries as seen by this person (they opened the What's New page)."""
    for r in db.query("SELECT id FROM releases"):
        db.execute("INSERT INTO release_seen (username, release_id) VALUES (?, ?) ON CONFLICT DO NOTHING", (g.user["username"], r["id"]))
    return jsonify({"message": "ok"})


@bp.post("/releases")
@perm_required("admin.releases")
def create_release():
    data = json_body()
    rid = str(data.get("id", "")).strip()
    if not RELEASE_ID.match(rid):
        raise ApiError("The release ID may contain letters, numbers, dots, dashes (max. 20 characters), e.g. 3.1.0")
    title = clean_text(data.get("title"), "Title", 100)
    body = clean_text(data.get("body"), "Text", 4000, required=False)
    if db.query("SELECT 1 AS x FROM releases WHERE id = ?", (rid,)):
        raise ApiError("This release ID already exists.", 409)
    db.execute("INSERT INTO releases (id, title, body, created, created_by) VALUES (?, ?, ?, ?, ?)",
               (rid, title, body, time.time(), g.user["username"]))
    audit.log(g.user["username"], "release_create", rid)
    return jsonify({"message": "Published."}), 201


@bp.delete("/releases/<rid>")
@perm_required("admin.releases")
def delete_release(rid):
    db.execute("DELETE FROM releases WHERE id = ?", (rid,))
    db.execute("DELETE FROM release_seen WHERE release_id = ?", (rid,))
    return jsonify({"message": "Deleted."})


# ---------------------------------------------------------------- ads and videos
def _https(value, field):
    value = str(value or "").strip()
    try:
        p = urlparse(value)
    except ValueError:
        raise ApiError(f"'{field}' is not a valid link.")
    if p.scheme != "https" or not p.hostname or len(value) > 400:
        raise ApiError(f"'{field}' must be an https link.")
    return value


@bp.get("/ads")
@login_required
def ads():
    cfg = appsettings.get()["ads"]
    if not cfg["enabled"]:
        return jsonify({"enabled": False, "items": []})
    rows = db.query("SELECT id, kind, title, url, body FROM ad_items WHERE active = 1 ORDER BY id DESC LIMIT 20")
    return jsonify({"enabled": True, "every_n_visits": cfg["every_n_visits"], "items": rows})


@bp.get("/ads/manage")
@perm_required("admin.ads")
def ads_manage():
    return jsonify(db.query("SELECT * FROM ad_items ORDER BY id DESC LIMIT 100"))


@bp.post("/ads")
@perm_required("admin.ads")
def ads_create():
    data = json_body()
    kind = data.get("kind", "banner")
    if kind not in ("banner", "video"):
        raise ApiError("Type must be banner or video.")
    title = clean_text(data.get("title"), "Title", 80)
    body = clean_text(data.get("body"), "Text", 300, required=False)
    url = _https(data.get("url"), "url")
    db.execute("INSERT INTO ad_items (kind, title, url, body, created) VALUES (?, ?, ?, ?, ?)", (kind, title, url, body, time.time()))
    audit.log(g.user["username"], "ad_create", title)
    return jsonify({"message": "Created."}), 201


@bp.patch("/ads/<int:aid>")
@perm_required("admin.ads")
def ads_toggle(aid):
    active = 1 if json_body().get("active") is True else 0
    if not db.execute("UPDATE ad_items SET active = ? WHERE id = ?", (active, aid)):
        raise ApiError("Not found.", 404)
    return jsonify({"message": "Saved."})


@bp.delete("/ads/<int:aid>")
@perm_required("admin.ads")
def ads_delete(aid):
    db.execute("DELETE FROM ad_items WHERE id = ?", (aid,))
    return jsonify({"message": "Deleted."})
