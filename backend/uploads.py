"""Uploads. The file itself goes from the browser straight into the object storage.

1. POST   /api/uploads              -> checks the rules, returns a signed upload link
2. (browser PUTs the file to that link)
3. POST   /api/uploads/<id>/confirm -> server checks the stored file really exists and is not too big
4. send the message with attachment_ids   (see messages.py)
"""
import os
import re
import time
import uuid

from flask import Blueprint, g, jsonify

import appsettings
import chat_service
import config
import db
import objstore
from security import ApiError, json_body, login_required, role_of

bp = Blueprint("uploads", __name__, url_prefix="/api/uploads")
MIME_RE = re.compile(r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$")
MB = 1024 * 1024


def _safe_name(name):
    name = os.path.basename(str(name or "").replace("\\", "/"))
    name = "".join(c for c in name if c.isprintable()).strip()[:120]
    if not name:
        raise ApiError("The file needs a name.")
    return name


def _limit_bytes(kind, mime, settings):
    if kind == "loading_image":
        return settings["loading"]["max_image_mb"] * MB
    if kind == "loading_music":
        return settings["loading"]["max_music_mb"] * MB
    what = objstore.file_kind(mime)
    mb = {"image": settings["max_image_mb"], "video": settings["max_video_mb"]}.get(what, settings["max_file_mb"])
    return min(mb, config.HARD_MAX_UPLOAD_MB) * MB


def summary(row):
    return {"id": row["id"], "name": row["name"], "mime": row["mime"], "size": row["size"],
            "kind": objstore.file_kind(row["mime"]),
            "url": objstore.presign_get(row["storage_key"], row["name"], row["mime"])}


@bp.post("")
@login_required
def start_upload():
    if not objstore.enabled():
        raise ApiError("Uploads are not set up on this server yet.", 503)
    settings = appsettings.get()
    data = json_body()
    user = g.user
    kind = data.get("kind", "attachment")
    name = _safe_name(data.get("filename"))
    mime = str(data.get("mime") or "application/octet-stream").lower()[:100]
    size = data.get("size")
    if kind not in ("attachment", "loading_image", "loading_music"):
        raise ApiError("Unknown upload type.")
    if not MIME_RE.match(mime):
        raise ApiError("Unknown file type.")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ApiError("The file is empty.")

    chat_type = chat_key = None
    is_admin = role_of(user) == "admin"
    if kind == "attachment":
        if not settings["uploads_enabled"]:
            raise ApiError("Uploads are switched off by the admins.", 403)
        chat = chat_service.resolve(data.get("chat_type"), data.get("chat_key"), user)
        chat_type, chat_key = chat["type"], chat["key"]
        if any(name.lower().endswith(ext) for ext in settings["blocked_extensions"]):
            raise ApiError("This file type is not allowed.", 400)
    elif kind == "loading_image":
        if mime not in objstore.INLINE_IMAGE:
            raise ApiError("Please choose a PNG, JPEG, GIF, WebP or AVIF image.")
        if not (is_admin or settings["loading"]["allow_user_image"]):
            raise ApiError("Custom loading images are switched off.", 403)
    else:
        if mime not in objstore.INLINE_AUDIO:
            raise ApiError("Please choose an MP3, OGG, WAV, AAC or M4A file.")
        if not (is_admin or settings["loading"]["allow_user_music"]):
            raise ApiError("Custom loading music is switched off.", 403)

    if size > _limit_bytes(kind, mime, settings):
        raise ApiError(f"That file is too big (limit: {_limit_bytes(kind, mime, settings) // MB} MB).", 413)

    # remove stale unfinished uploads of this user, then check the quota
    stale = db.query("SELECT id, storage_key FROM attachments WHERE username = ? AND status = 'pending' AND created < ?",
                     (user["username"], time.time() - 86400))
    if stale:
        objstore.delete([s["storage_key"] for s in stale])
        db.execute(f"DELETE FROM attachments WHERE id IN ({db.placeholders(stale)})", [s["id"] for s in stale])
    used = db.query("SELECT COALESCE(SUM(size), 0) AS s FROM attachments WHERE username = ?", (user["username"],))[0]["s"]
    if used + size > settings["user_quota_mb"] * MB:
        raise ApiError(f"Your storage limit of {settings['user_quota_mb']} MB would be exceeded.", 413)

    att_id = uuid.uuid4().hex
    key = f"{kind}/{user['username'].lower()}/{att_id}"
    db.execute("INSERT INTO attachments (id, username, kind, chat_type, chat_key, storage_key, name, mime, size, created) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (att_id, user["username"], kind, chat_type, chat_key, key, name, mime, size, time.time()))
    return jsonify({"id": att_id, "upload_url": objstore.presign_put(key, mime), "headers": {"Content-Type": mime}}), 201


def _own(att_id, status):
    rows = db.query("SELECT * FROM attachments WHERE id = ? AND username = ? AND status = ?", (att_id, g.user["username"], status))
    if not rows:
        raise ApiError("Upload not found.", 404)
    return rows[0]


@bp.post("/<att_id>/confirm")
@login_required
def confirm(att_id):
    row = _own(att_id, "pending")
    real = objstore.head(row["storage_key"])
    if real is None:
        raise ApiError("The file did not arrive. Please try again.", 400)
    if real == 0 or real > _limit_bytes(row["kind"], row["mime"], appsettings.get()):
        objstore.delete([row["storage_key"]])
        db.execute("DELETE FROM attachments WHERE id = ?", (att_id,))
        raise ApiError("The uploaded file is empty or too big.", 413)
    db.execute("UPDATE attachments SET status = 'ready', size = ? WHERE id = ?", (real, att_id))
    row.update(size=real, status="ready")
    return jsonify(summary(row))


@bp.delete("/<att_id>")
@login_required
def cancel(att_id):
    rows = db.query("SELECT * FROM attachments WHERE id = ? AND username = ? AND message_id IS NULL", (att_id, g.user["username"]))
    if not rows:
        raise ApiError("Upload not found.", 404)
    objstore.delete([rows[0]["storage_key"]])
    db.execute("DELETE FROM attachments WHERE id = ?", (att_id,))
    return jsonify({"message": "Upload removed."})


@bp.get("/<att_id>/url")
@login_required
def fresh_url(att_id):
    """A new download link (the old one may have expired)."""
    rows = db.query("SELECT * FROM attachments WHERE id = ? AND status = 'ready'", (att_id,))
    if not rows:
        raise ApiError("File not found.", 404)
    row = rows[0]
    if row["message_id"]:
        message = db.query("SELECT chat_type, chat_key FROM messages WHERE id = ?", (row["message_id"],))
        if not message or not chat_service.is_member(message[0]["chat_type"], message[0]["chat_key"], g.user["username"]):
            raise ApiError("File not found.", 404)
    elif not row["kind"].startswith("loading_") and row["username"] != g.user["username"]:
        raise ApiError("File not found.", 404)
    return jsonify({"url": objstore.presign_get(row["storage_key"], row["name"], row["mime"])})
