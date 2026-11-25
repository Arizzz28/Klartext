"""Messages for private chats AND groups, reactions, reports, clearing, chat backgrounds.

URL pattern:  /api/chats/<dm|group>/<username or group id>/...
For private chats the key is the other person's username, for groups it is the group id.
"""
from flask import Blueprint, g, jsonify, request

import appsettings
import chat_service
import db
from security import ApiError, clean_background, json_body, login_required, perm_required

bp = Blueprint("messages", __name__, url_prefix="/api")


def _chat(chat_type, key):
    return chat_service.resolve(chat_type, key, g.user)


@bp.get("/messages/conversations")
@login_required
def conversations():
    return jsonify(chat_service.conversations(g.user))


@bp.get("/chats/<chat_type>/<key>/messages")
@login_required
def list_messages(chat_type, key):
    chat = _chat(chat_type, key)
    limit = min(max(request.args.get("limit", 100, type=int), 1), 200)
    before = request.args.get("before", type=int)
    result = chat_service.fetch(chat["type"], chat["key"], g.user, limit, before)
    result["can_moderate"] = chat_service.can_moderate(g.user, chat)
    return jsonify(result)


@bp.post("/chats/<chat_type>/<key>/messages")
@perm_required("chat.write")
def send_message(chat_type, key):
    data = json_body()
    chat = _chat(chat_type, key)
    reply_to = data.get("reply_to")
    if reply_to is not None and (isinstance(reply_to, bool) or not isinstance(reply_to, int)):
        raise ApiError("Invalid reply.")
    ids = data.get("attachment_ids") or []
    if not isinstance(ids, list) or not all(isinstance(i, str) and len(i) <= 64 for i in ids):
        raise ApiError("Invalid attachments.")
    return jsonify(chat_service.post(chat, g.user, data.get("text", ""), reply_to, ids)), 201


@bp.post("/chats/<chat_type>/<key>/clear")
@login_required
def clear_chat(chat_type, key):
    scope = json_body().get("scope")
    chat = _chat(chat_type, key)
    if scope == "me":
        chat_service.clear_for_me(chat, g.user)
        return jsonify({"message": "Chat cleared for you."})
    if scope == "all":
        if not chat_service.can_moderate(g.user, chat):
            raise ApiError("Only group admins, moderators and admins can clear a chat for everybody.", 403)
        chat_service.clear_for_all(chat, g.user)
        return jsonify({"message": "Chat cleared for everybody."})
    raise ApiError("Scope must be 'me' or 'all'.")


# ---------- chat background (only visible to yourself) ----------
@bp.get("/chats/<chat_type>/<key>/settings")
@login_required
def get_chat_settings(chat_type, key):
    chat = _chat(chat_type, key)
    rows = db.query("SELECT background, dim FROM chat_settings WHERE username = ? AND chat_type = ? AND chat_key = ?",
                    (g.user["username"], chat["type"], chat["key"]))
    mine = rows[0] if rows else {"background": "", "dim": 30}
    return jsonify({**mine, "default": appsettings.get()["background"]["default"],
                    "allow_custom": appsettings.get()["background"]["allow_custom"]})


@bp.put("/chats/<chat_type>/<key>/settings")
@login_required
def put_chat_settings(chat_type, key):
    data = json_body()
    chat = _chat(chat_type, key)
    background = clean_background(data.get("background", ""), appsettings.PRESET_BACKGROUNDS)
    if background.startswith("data:") and not appsettings.get()["background"]["allow_custom"]:
        raise ApiError("Your own background images are switched off by the admins.", 403)
    dim = data.get("dim", 30)
    if isinstance(dim, bool) or not isinstance(dim, int) or not 0 <= dim <= 80:
        raise ApiError("Dimming must be between 0 and 80.")
    db.execute("INSERT INTO chat_settings (username, chat_type, chat_key, background, dim) VALUES (?, ?, ?, ?, ?) "
               "ON CONFLICT (username, chat_type, chat_key) DO UPDATE SET background = excluded.background, dim = excluded.dim",
               (g.user["username"], chat["type"], chat["key"], background, dim))
    return jsonify({"background": background, "dim": dim})


# ---------- single messages ----------
@bp.patch("/messages/<int:mid>")
@perm_required("chat.write")
def edit_message(mid):
    return jsonify(chat_service.edit(mid, g.user, json_body().get("text")))


@bp.delete("/messages/<int:mid>")
@login_required
def delete_message(mid):
    chat_service.delete(mid, g.user)
    return jsonify({"message": "Message deleted."})


@bp.put("/messages/<int:mid>/reactions/<emoji>")
@perm_required("chat.react")
def add_reaction(mid, emoji):
    return jsonify(chat_service.react(mid, g.user, emoji, True))


@bp.delete("/messages/<int:mid>/reactions/<emoji>")
@login_required
def remove_reaction(mid, emoji):
    return jsonify(chat_service.react(mid, g.user, emoji, False))


@bp.post("/messages/<int:mid>/report")
@perm_required("chat.report")
def report_message(mid):
    chat_service.report(mid, g.user, json_body().get("reason", ""))
    return jsonify({"message": "Thanks, the moderators will have a look."}), 201
