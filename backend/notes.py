"""Private notes. Only the author can read them - except people whose rank has the separate permission
admin.notes: they can open the notes of people BELOW their rank. Every such look is written to the audit log
and the author gets a notification, so it is never secret."""
import time

from flask import Blueprint, g, jsonify

import audit
import db
import notify
import perms
import storage
from security import ApiError, clean_text, find_user, json_body, perm_required

bp = Blueprint("notes", __name__, url_prefix="/api/notes")
MAX_NOTES = 200


def _note(row):
    return {"id": row["id"], "title": row["title"], "body": row["body"], "created": row["created"], "updated": row["updated"]}


@bp.get("")
@perm_required("tabs.notes")
def list_notes():
    rows = db.query("SELECT * FROM notes WHERE username = ? ORDER BY updated DESC", (g.user["username"],))
    return jsonify([_note(r) for r in rows])


@bp.post("")
@perm_required("tabs.notes")
def create_note():
    data = json_body()
    title = clean_text(data.get("title"), "Title", 120, required=False)
    body = clean_text(data.get("body"), "Note", 20000, required=False)
    if not title and not body:
        raise ApiError("The note is empty.")
    if db.query("SELECT COUNT(*) AS n FROM notes WHERE username = ?", (g.user["username"],))[0]["n"] >= MAX_NOTES:
        raise ApiError(f"You can have at most {MAX_NOTES} notes.", 409)
    now = time.time()
    nid = db.query("INSERT INTO notes (username, title, body, created, updated) VALUES (?, ?, ?, ?, ?) RETURNING id",
                   (g.user["username"], title, body, now, now))[0]["id"]
    return jsonify({"id": nid}), 201


@bp.put("/<int:nid>")
@perm_required("tabs.notes")
def update_note(nid):
    data = json_body()
    title = clean_text(data.get("title"), "Title", 120, required=False)
    body = clean_text(data.get("body"), "Note", 20000, required=False)
    n = db.execute("UPDATE notes SET title = ?, body = ?, updated = ? WHERE id = ? AND username = ?",
                   (title, body, time.time(), nid, g.user["username"]))
    if not n:
        raise ApiError("Note not found.", 404)
    return jsonify({"message": "Saved."})


@bp.delete("/<int:nid>")
@perm_required("tabs.notes")
def delete_note(nid):
    if not db.execute("DELETE FROM notes WHERE id = ? AND username = ?", (nid, g.user["username"])):
        raise ApiError("Note not found.", 404)
    return jsonify({"message": "Deleted."})


@bp.get("/of/<username>")
@perm_required("admin.notes")
def notes_of(username):
    target = find_user(storage.read("users"), username)
    if not target:
        raise ApiError("User not found.", 404)
    if target["username"] != g.user["username"] and not perms.is_owner(g.user) and not perms.can_manage(g.user, target):
        raise ApiError("You can only open notes of people whose rank is below yours.", 403)
    rows = db.query("SELECT * FROM notes WHERE username = ? ORDER BY updated DESC", (target["username"],))
    if target["username"] != g.user["username"]:
        audit.log(g.user["username"], "view_notes", target["username"], f"{len(rows)} notes")
        notify.notify(target["username"], "notes", f"{g.user['display_name']} (staff) looked at your notes.", "#/notes")
    return jsonify({"user": target["username"], "notes": [_note(r) for r in rows]})
