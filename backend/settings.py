"""Public settings, the loading screen (picture + music) and personal preferences."""
from flask import Blueprint, g, jsonify

import appsettings
import db
import objstore
import storage
import perms
from security import ApiError, json_body, login_required, optional_user

bp = Blueprint("settings", __name__, url_prefix="/api")


def asset_url(asset_id, kinds):
    if not asset_id or not objstore.enabled():
        return ""
    rows = db.query("SELECT * FROM attachments WHERE id = ? AND status = 'ready'", (asset_id,))
    if not rows or rows[0]["kind"] not in kinds:
        return ""
    return objstore.presign_get(rows[0]["storage_key"], rows[0]["name"], rows[0]["mime"])


def release_asset(asset_id):
    """Deletes an uploaded loading picture/music (row and file)."""
    rows = db.query("SELECT storage_key FROM attachments WHERE id = ? AND kind LIKE 'loading_%'", (asset_id,))
    if rows:
        objstore.delete([rows[0]["storage_key"]])
        db.execute("DELETE FROM attachments WHERE id = ?", (asset_id,))


def check_asset(asset_id, kind, username):
    """The asset must exist, be finished, be of the right kind and belong to this person."""
    if not asset_id:
        return ""
    rows = db.query("SELECT id FROM attachments WHERE id = ? AND kind = ? AND username = ? AND status = 'ready'",
                    (asset_id, kind, username))
    if not rows:
        raise ApiError("That file is not available. Please upload it again.", 400)
    return asset_id


def effective_loading(user):
    s = appsettings.get()["loading"]
    image_id, music_id = s["image_asset"], s["music_asset"]
    if user:
        prefs = user.get("prefs", {})
        if (s["allow_user_image"] or perms.has_perm(user, "admin.settings")) and prefs.get("loading_image"):
            image_id = prefs["loading_image"]
        if (s["allow_user_music"] or perms.has_perm(user, "admin.settings")) and prefs.get("loading_music"):
            music_id = prefs["loading_music"]
        if prefs.get("music_off") and s["allow_user_mute"]:
            music_id = ""
    return {"title": s["title"], "image": asset_url(image_id, ("loading_image",)),
            "music": asset_url(music_id, ("loading_music",)), "volume": s["music_volume"],
            "can_mute": s["allow_user_mute"], "allow_user_image": s["allow_user_image"],
            "allow_user_music": s["allow_user_music"]}


@bp.get("/config")
def public_config():
    s = appsettings.get()
    return jsonify({
        "announcement": s["announcement"], "registration_mode": s["registration_mode"],
        "uploads": {"enabled": bool(s["uploads_enabled"] and objstore.enabled()), "max_image_mb": s["max_image_mb"],
                    "max_video_mb": s["max_video_mb"], "max_file_mb": s["max_file_mb"]},
        "background": s["background"], "presets": list(appsettings.PRESET_BACKGROUNDS),
    })


@bp.get("/loading")
def loading():
    return jsonify(effective_loading(optional_user()))


@bp.put("/me/loading")
@login_required
def update_my_loading():
    data = json_body()
    s = appsettings.get()["loading"]
    admin = perms.has_perm(g.user, "admin.settings")
    with storage.transaction("users") as db_:
        user = db_["users"][g.user["username"].lower()]
        prefs = user.setdefault("prefs", {})
        old = []
        if "image_asset" in data:
            if not (admin or s["allow_user_image"]):
                raise ApiError("Custom loading images are switched off.", 403)
            new = check_asset(data["image_asset"], "loading_image", user["username"])
            if prefs.get("loading_image") and prefs["loading_image"] != new:
                old.append(prefs["loading_image"])
            prefs["loading_image"] = new
        if "music_asset" in data:
            if not (admin or s["allow_user_music"]):
                raise ApiError("Custom loading music is switched off.", 403)
            new = check_asset(data["music_asset"], "loading_music", user["username"])
            if prefs.get("loading_music") and prefs["loading_music"] != new:
                old.append(prefs["loading_music"])
            prefs["loading_music"] = new
        if "music_off" in data:
            if not isinstance(data["music_off"], bool):
                raise ApiError("music_off must be true or false.")
            if data["music_off"] and not s["allow_user_mute"]:
                raise ApiError("Turning the music off is not allowed.", 403)
            prefs["music_off"] = data["music_off"]
        result = prefs
    for asset in old:
        release_asset(asset)
    return jsonify(result)
