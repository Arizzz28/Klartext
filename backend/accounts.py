"""A person's own rights over their data: delete the account yourself, download a copy of your data.

Both work even before the current Terms are accepted (see security.CONSENT_EXEMPT): somebody who does not agree to
new Terms must still be able to leave and to take their data with them.
"""
import json
import time

from flask import Blueprint, Response, g, jsonify

import audit
import chat_service
import db
import perms
import storage
from security import ApiError, check_password, find_user, is_super_admin, json_body, login_required, rate_limit

bp = Blueprint("accounts", __name__, url_prefix="/api/me")

EXPORT_MAX_MESSAGES = 50000


def remove_account_records(db_, name):
    """Takes the account out of users, groups, invitations (call it INSIDE storage.transaction("users", "groups",
    "invitations", "whitelist")). Returns the ids of groups that became empty and must be purged afterwards."""
    emptied = []
    for gid, group in list(db_["groups"].items()):
        if name not in group["members"]:
            continue
        was_only_admin = group["members"][name] == "admin" and sum(r == "admin" for r in group["members"].values()) == 1
        del group["members"][name]
        if not group["members"]:
            del db_["groups"][gid]
            emptied.append(gid)
        elif was_only_admin:
            group["members"][next(iter(group["members"]))] = "admin"      # ownership goes to the next member
    db_["invitations"] = [i for i in db_["invitations"] if name not in (i["from"], i["to"])]
    del db_["users"][name.lower()]
    return emptied


def finish_deletion(name, delete_group_messages, emptied_groups):
    """The part after the account is gone: messages, files, personal data of the newer features."""
    chat_service.purge_user(name, delete_group_messages)
    for gid in emptied_groups:
        chat_service.purge_chat("group", gid)


@bp.post("/delete")
@login_required
def delete_myself():
    data = json_body()
    me = g.user
    rate_limit(f"selfdelete:{me['username'].lower()}", 5, 600)
    if is_super_admin(me):
        raise ApiError("The Owner account cannot be deleted here. Hand the Owner role to somebody else first.", 403)
    if str(data.get("confirm", "")).strip().lower() != me["username"].lower():
        raise ApiError("Type your username to confirm.")
    if not check_password(me["password_hash"], str(data.get("password", ""))):
        raise ApiError("Your password is wrong.", 403)
    delete_group_messages = data.get("delete_group_messages", True) is not False
    with storage.transaction("users", "groups", "invitations", "whitelist") as db_:
        if me["username"].lower() not in db_["users"]:
            raise ApiError("Account not found.", 404)
        emptied = remove_account_records(db_, me["username"])
    finish_deletion(me["username"], delete_group_messages, emptied)
    audit.log(me["username"], "delete_self", me["username"], "group messages deleted" if delete_group_messages else "group messages kept")
    return jsonify({"message": "Your account and your data were deleted."})


# ---------------------------------------------------------------- download my data
def _rows(sql, params=()):
    return [dict(r) for r in db.query(sql, params)]


@bp.get("/export")
@login_required
def export_my_data():
    """Everything the app stores ABOUT YOU, as one JSON file. Messages of other people are not included (they are
    theirs); you get your own messages, notes, calendar, tasks and so on."""
    me = g.user
    name, low = me["username"], me["username"].lower()
    users = storage.read("users")

    def who(username):
        u = find_user(users, username)
        return u["display_name"] if u else "Deleted user"

    chats = {}
    for r in _rows("SELECT chat_type, chat_key, body, created, edited, deleted FROM messages WHERE sender = ? AND is_system = 0 "
                   "ORDER BY id LIMIT ?", (name, EXPORT_MAX_MESSAGES)):
        if r["chat_type"] == "dm":
            partner = next((p for p in r["chat_key"].split("|") if p != low), "")
            label = f"Private chat with {who(partner)}"
        else:
            group = storage.read("groups").get(r["chat_key"])
            label = f"Group: {group['name']}" if group else "Group (deleted)"
        chats.setdefault(label, []).append({"text": "" if r["deleted"] else r["body"], "sent": r["created"], "edited": r["edited"],
                                            "deleted": bool(r["deleted"])})

    ranks = perms.all_ranks()
    out = {
        "about": "A copy of the data Chatisfying stores about you. Messages written by other people are not included.",
        "exported_at": time.time(),
        "profile": {"username": name, "display_name": me["display_name"], "email": me["email"], "created": me.get("created"),
                    "rank": perms.rank_of(me, ranks)["name"], "accepted_terms": me.get("consent"),
                    "settings": me.get("prefs", {})},
        "my_messages": chats,
        "notes": _rows("SELECT title, body, created, updated FROM notes WHERE username = ?", (name,)),
        "calendar": _rows("SELECT title, note, start_ts, end_ts FROM events WHERE owner = ?", (name,)),
        "tasks": _rows("SELECT title, done, due FROM tasks WHERE owner = ?", (name,)),
        "forum_posts": _rows("SELECT title, body, created FROM forum_posts WHERE author = ?", (name,)),
        "forum_comments": _rows("SELECT body, created FROM forum_comments WHERE author = ?", (name,)),
        "playlists": [{**p, "tracks": _rows("SELECT title, url FROM playlist_tracks WHERE playlist_id = ?", (p["id"],))}
                      for p in _rows("SELECT id, name, visibility FROM playlists WHERE owner = ?", (name,))],
        "custom_tabs": _rows("SELECT title, kind, content FROM custom_tabs WHERE username = ?", (name,)),
        "offers": _rows("SELECT text, created, status FROM offers WHERE username = ?", (name,)),
        "notifications": _rows("SELECT kind, text, created FROM notifications WHERE username = ?", (name,)),
        "coins": {"balance": (_rows("SELECT coins FROM wallets WHERE username = ?", (name,)) or [{"coins": 0}])[0]["coins"],
                  "history": _rows("SELECT delta, reason, ts FROM coin_log WHERE username = ?", (name,))},
        "game_scores": _rows("SELECT game, best, plays FROM game_scores WHERE username = ?", (name,)),
        "login_history": _rows("SELECT ts, ok FROM login_log WHERE username = ? ORDER BY id DESC LIMIT 200", (name,)),
        "push_devices": len(_rows("SELECT endpoint FROM push_subscriptions WHERE username = ?", (name,))),
        "uploaded_files": _rows("SELECT name, mime, size, created FROM attachments WHERE username = ? AND status = 'ready'", (name,)),
    }
    body = json.dumps(out, ensure_ascii=False, indent=1, default=str)
    return Response(body, mimetype="application/json",
                    headers={"Content-Disposition": f'attachment; filename="chatisfying-{low}.json"'})
