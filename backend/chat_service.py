"""Everything about messages: sending, editing, deleting, reactions, reports, clearing chats.

A chat is identified by (chat_type, chat_key):
- "dm":    chat_key = both usernames in lowercase, sorted, joined by "|"   (e.g. "anna|bob")
- "group": chat_key = the group id

All permission checks that depend on the chat live here or in messages.py, never in the frontend.
"""
import json
import re
import time

import appsettings
import audit
import config
import db
import objstore
import storage
from security import ApiError, clean_text, find_user, rate_limit, role_of

MAX_ATTACHMENTS = 10
MAX_REACTION_KINDS = 12
_BAD_EMOJI = re.compile(r"[A-Za-z0-9\s<>&\"'`\\]")


def dm_key(a, b):
    return "|".join(sorted([a.lower(), b.lower()]))


def valid_emoji(value):
    return (isinstance(value, str) and 1 <= len(value) <= 16 and not _BAD_EMOJI.search(value)
            and any(ord(c) > 0x2000 for c in value))


# ---------------------------------------------------------------- who may use a chat
def resolve(chat_type, key, user):
    """Checks that `user` may use this chat and returns {type, key, partner?, group?}."""
    if chat_type == "dm":
        partner = find_user(storage.read("users"), key)
        if not partner or partner["status"] != "active" or partner["username"] == user["username"]:
            raise ApiError("User not found.", 404)
        return {"type": "dm", "key": dm_key(user["username"], partner["username"]), "partner": partner}
    if chat_type == "group":
        group = storage.read("groups").get(str(key))
        if not group:
            raise ApiError("Group not found.", 404)
        if user["username"] not in group["members"]:
            raise ApiError("You are not a member of this group.", 403)
        return {"type": "group", "key": group["id"], "group": group}
    raise ApiError("Unknown chat type.", 400)


def is_member(chat_type, chat_key, username):
    if chat_type == "dm":
        return username.lower() in chat_key.split("|")
    group = storage.read("groups").get(chat_key)
    return bool(group and username in group["members"])


def can_moderate(user, chat):
    """May this user delete other people's messages / clear this chat for everybody?"""
    if role_of(user) in ("moderator", "admin"):
        return True
    return chat["type"] == "group" and chat["group"]["members"].get(user["username"]) == "admin"


# ---------------------------------------------------------------- reading
def _in(sql_template, ids, extra=()):
    return db.query(sql_template.replace("{IN}", db.placeholders(ids)), tuple(ids) + tuple(extra))


def _serialize(rows, me, users):
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    reactions, attachments = {}, {}
    for r in _in("SELECT * FROM reactions WHERE message_id IN ({IN}) ORDER BY created", ids):
        reactions.setdefault(r["message_id"], {}).setdefault(r["emoji"], []).append(r["username"])
    for a in _in("SELECT * FROM attachments WHERE message_id IN ({IN}) AND status = 'ready' ORDER BY created", ids):
        attachments.setdefault(a["message_id"], []).append(a)
    reply_ids = sorted({r["reply_to"] for r in rows if r["reply_to"]})
    replies = {r["id"]: r for r in _in("SELECT id, sender, body, deleted FROM messages WHERE id IN ({IN})", reply_ids)} if reply_ids else {}

    def name_of(username):
        u = find_user(users, username)
        return u["display_name"] if u else "Deleted user"

    out = []
    for r in rows:
        reply = replies.get(r["reply_to"]) if r["reply_to"] else None
        out.append({
            "id": r["id"], "sender": r["sender"], "sender_name": name_of(r["sender"]),
            "text": "" if r["deleted"] else r["body"], "ts": r["created"], "edited": r["edited"],
            "deleted": bool(r["deleted"]), "system": bool(r["is_system"]),
            "reply": ({"id": reply["id"], "sender_name": name_of(reply["sender"]),
                       "text": "" if reply["deleted"] else reply["body"][:140], "deleted": bool(reply["deleted"])}
                      if reply else None),
            "reactions": [{"emoji": e, "count": len(us), "mine": me["username"] in us, "users": us[:30]}
                          for e, us in reactions.get(r["id"], {}).items()],
            "attachments": [{"id": a["id"], "name": a["name"], "mime": a["mime"], "size": a["size"],
                             "kind": objstore.file_kind(a["mime"]),
                             "url": objstore.presign_get(a["storage_key"], a["name"], a["mime"]) if objstore.enabled() else ""}
                            for a in attachments.get(r["id"], [])],
        })
    return out


def cleared_floor(username, chat_type, chat_key):
    rows = db.query("SELECT cleared_before FROM chat_clears WHERE username = ? AND chat_type = ? AND chat_key = ?",
                    (username, chat_type, chat_key))
    return rows[0]["cleared_before"] if rows else 0


def fetch(chat_type, chat_key, me, limit=100, before=None, ignore_clear=False):
    floor = 0 if ignore_clear else cleared_floor(me["username"], chat_type, chat_key)
    sql = "SELECT * FROM messages WHERE chat_type = ? AND chat_key = ? AND id > ?"
    params = [chat_type, chat_key, floor]
    if before:
        sql += " AND id < ?"
        params.append(before)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = list(reversed(db.query(sql, params)))
    return {"messages": _serialize(rows, me, storage.read("users")), "has_more": len(rows) == limit}


def _one(message_id, me):
    rows = db.query("SELECT * FROM messages WHERE id = ?", (message_id,))
    return _serialize(rows, me, storage.read("users"))[0] if rows else None


# ---------------------------------------------------------------- writing
def post(chat, user, text, reply_to=None, attachment_ids=()):
    text = clean_text(text, "Message", config.MAX_MESSAGE_LENGTH, required=False)
    attachment_ids = list(attachment_ids or [])
    if not text and not attachment_ids:
        raise ApiError("Message must not be empty.")
    if len(attachment_ids) > MAX_ATTACHMENTS:
        raise ApiError(f"At most {MAX_ATTACHMENTS} files per message.")
    if user.get("muted_until", 0) > time.time():
        until = time.strftime("%H:%M", time.localtime(user["muted_until"]))
        raise ApiError(f"You are muted until {until}.", 403)
    rate_limit(f"msg:{user['username']}", appsettings.get()["messages_per_minute"], 60)

    with db.transaction() as tx:
        if reply_to is not None:
            ok = tx.query("SELECT id FROM messages WHERE id = ? AND chat_type = ? AND chat_key = ?",
                          (reply_to, chat["type"], chat["key"]))
            if not ok:
                raise ApiError("The message you reply to does not exist.", 404)
        new_id = tx.query(
            "INSERT INTO messages (chat_type, chat_key, sender, body, reply_to, created) VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
            (chat["type"], chat["key"], user["username"], text, reply_to, time.time()))[0]["id"]
        for att_id in attachment_ids:
            n = tx.execute(
                "UPDATE attachments SET message_id = ? WHERE id = ? AND username = ? AND kind = 'attachment' "
                "AND status = 'ready' AND message_id IS NULL AND chat_type = ? AND chat_key = ?",
                (new_id, att_id, user["username"], chat["type"], chat["key"]))
            if n != 1:
                raise ApiError("One of the files is not available. Please upload it again.", 400)
    return _one(new_id, user)


def _message_row(message_id):
    rows = db.query("SELECT * FROM messages WHERE id = ?", (message_id,))
    if not rows:
        raise ApiError("Message not found.", 404)
    return rows[0]


def _need_access(row, user):
    if not is_member(row["chat_type"], row["chat_key"], user["username"]):
        raise ApiError("You are not part of this chat.", 403)


def edit(message_id, user, text):
    row = _message_row(message_id)
    if row["sender"] != user["username"] or row["deleted"] or row["is_system"]:
        raise ApiError("You can only edit your own messages.", 403)
    text = clean_text(text, "Message", config.MAX_MESSAGE_LENGTH)
    db.execute("UPDATE messages SET body = ?, edited = ? WHERE id = ?", (text, time.time(), message_id))
    return _one(message_id, user)


def delete(message_id, user):
    row = _message_row(message_id)
    if role_of(user) not in ("moderator", "admin"):
        _need_access(row, user)
    if row["is_system"]:
        raise ApiError("System messages cannot be deleted.", 403)
    own = row["sender"] == user["username"]
    if not own:
        if row["chat_type"] == "group":
            group = storage.read("groups").get(row["chat_key"])
            group_admin = bool(group and group["members"].get(user["username"]) == "admin")
        else:
            group_admin = False
        if not (group_admin or role_of(user) in ("moderator", "admin")):
            raise ApiError("You can't delete this message.", 403)
    keys = [a["storage_key"] for a in db.query("SELECT storage_key FROM attachments WHERE message_id = ?", (message_id,))]
    with db.transaction() as tx:
        tx.execute("UPDATE messages SET body = '', deleted = 1 WHERE id = ?", (message_id,))
        tx.execute("DELETE FROM reactions WHERE message_id = ?", (message_id,))
        tx.execute("DELETE FROM attachments WHERE message_id = ?", (message_id,))
    objstore.delete(keys)
    if not own:
        audit.log(user["username"], "delete_message", f"#{message_id} by {row['sender']}", f"{row['chat_type']}:{row['chat_key']}")


def react(message_id, user, emoji, add):
    if not valid_emoji(emoji):
        raise ApiError("That is not an emoji.")
    row = _message_row(message_id)
    _need_access(row, user)
    if row["deleted"] or row["is_system"]:
        raise ApiError("You can't react to this message.")
    if add:
        kinds = {r["emoji"] for r in db.query("SELECT emoji FROM reactions WHERE message_id = ?", (message_id,))}
        if emoji not in kinds and len(kinds) >= MAX_REACTION_KINDS:
            raise ApiError(f"A message can have at most {MAX_REACTION_KINDS} different reactions.")
        db.execute("INSERT INTO reactions (message_id, username, emoji, created) VALUES (?, ?, ?, ?) "
                   "ON CONFLICT (message_id, username, emoji) DO NOTHING", (message_id, user["username"], emoji, time.time()))
    else:
        db.execute("DELETE FROM reactions WHERE message_id = ? AND username = ? AND emoji = ?",
                   (message_id, user["username"], emoji))
    return _one(message_id, user)


def report(message_id, user, reason):
    row = _message_row(message_id)
    _need_access(row, user)
    if row["sender"] == user["username"]:
        raise ApiError("You can't report your own message.")
    reason = clean_text(reason, "Reason", 300, required=False)
    if db.query("SELECT id FROM reports WHERE message_id = ? AND reporter = ? AND status = 'open'", (message_id, user["username"])):
        raise ApiError("You already reported this message.", 409)
    context = db.query("SELECT id, sender, body, created, deleted FROM messages WHERE chat_type = ? AND chat_key = ? "
                       "AND id BETWEEN ? AND ? ORDER BY id",
                       (row["chat_type"], row["chat_key"], message_id - 5, message_id + 2))
    snapshot = json.dumps({"chat_type": row["chat_type"], "chat_key": row["chat_key"], "sender": row["sender"],
                           "context": [{"id": m["id"], "sender": m["sender"], "text": "" if m["deleted"] else m["body"],
                                        "ts": m["created"]} for m in context]})
    db.execute("INSERT INTO reports (message_id, reporter, reason, snapshot, created) VALUES (?, ?, ?, ?, ?)",
               (message_id, user["username"], reason, snapshot, time.time()))


# ---------------------------------------------------------------- clearing / removing chats
def clear_for_me(chat, user):
    last = db.query("SELECT MAX(id) AS m FROM messages WHERE chat_type = ? AND chat_key = ?", (chat["type"], chat["key"]))[0]["m"] or 0
    db.execute("INSERT INTO chat_clears (username, chat_type, chat_key, cleared_before) VALUES (?, ?, ?, ?) "
               "ON CONFLICT (username, chat_type, chat_key) DO UPDATE SET cleared_before = excluded.cleared_before",
               (user["username"], chat["type"], chat["key"], last))


def purge_chat(chat_type, chat_key, keep_settings=False):
    """Really deletes all messages, reactions and files of a chat."""
    where = "chat_type = ? AND chat_key = ?"
    keys = [a["storage_key"] for a in db.query(
        f"SELECT storage_key FROM attachments WHERE message_id IN (SELECT id FROM messages WHERE {where})", (chat_type, chat_key))]
    with db.transaction() as tx:
        tx.execute(f"DELETE FROM reactions WHERE message_id IN (SELECT id FROM messages WHERE {where})", (chat_type, chat_key))
        tx.execute(f"DELETE FROM attachments WHERE message_id IN (SELECT id FROM messages WHERE {where})", (chat_type, chat_key))
        tx.execute(f"DELETE FROM messages WHERE {where}", (chat_type, chat_key))
        if not keep_settings:
            tx.execute(f"DELETE FROM chat_clears WHERE {where}", (chat_type, chat_key))
            tx.execute(f"DELETE FROM chat_settings WHERE {where}", (chat_type, chat_key))
    objstore.delete(keys)


def clear_for_all(chat, actor):
    purge_chat(chat["type"], chat["key"], keep_settings=True)
    db.execute("DELETE FROM chat_clears WHERE chat_type = ? AND chat_key = ?", (chat["type"], chat["key"]))
    system_message(chat["type"], chat["key"], actor["username"], f"{actor['display_name']} cleared this chat.")
    audit.log(actor["username"], "clear_chat", f"{chat['type']}:{chat['key']}")


def system_message(chat_type, chat_key, actor, text):
    db.execute("INSERT INTO messages (chat_type, chat_key, sender, body, created, is_system) VALUES (?, ?, ?, ?, ?, 1)",
               (chat_type, chat_key, actor, text, time.time()))


def purge_user(username, delete_group_messages):
    """Removes what a deleted account leaves behind. Private chats always go; group messages optionally."""
    low = username.lower()
    # private chats with this person
    dm_keys = [r["chat_key"] for r in db.query("SELECT DISTINCT chat_key FROM messages WHERE chat_type = 'dm'")
               if low in r["chat_key"].split("|")]
    for key in dm_keys:
        purge_chat("dm", key)
    if delete_group_messages:
        mine = [r["id"] for r in db.query("SELECT id FROM messages WHERE chat_type = 'group' AND sender = ?", (username,))]
        for i in range(0, len(mine), 400):
            part = mine[i:i + 400]
            keys = [a["storage_key"] for a in _in("SELECT storage_key FROM attachments WHERE message_id IN ({IN})", part)]
            db.execute(f"DELETE FROM reactions WHERE message_id IN ({db.placeholders(part)})", part)
            db.execute(f"DELETE FROM attachments WHERE message_id IN ({db.placeholders(part)})", part)
            db.execute(f"DELETE FROM messages WHERE id IN ({db.placeholders(part)})", part)
            objstore.delete(keys)
    # everything else this person owns
    keys = [a["storage_key"] for a in db.query("SELECT storage_key FROM attachments WHERE username = ?", (username,))]
    db.execute("DELETE FROM attachments WHERE username = ?", (username,))
    db.execute("DELETE FROM reactions WHERE username = ?", (username,))
    db.execute("DELETE FROM chat_clears WHERE username = ?", (username,))
    db.execute("DELETE FROM chat_settings WHERE username = ?", (username,))
    objstore.delete(keys)


# ---------------------------------------------------------------- lists
def conversations(me):
    low = me["username"].lower()
    rows = db.query(
        "SELECT * FROM messages WHERE id IN (SELECT MAX(id) FROM messages WHERE chat_type = 'dm' "
        "AND (chat_key LIKE ? OR chat_key LIKE ?) GROUP BY chat_key)", (low + "|%", "%|" + low))
    users = storage.read("users")
    out = []
    for r in rows:
        parts = r["chat_key"].split("|")
        if low not in parts:
            continue
        partner = find_user(users, parts[0] if parts[1] == low else parts[1]) if len(parts) == 2 else None
        if not partner or partner["status"] != "active":
            continue
        if r["id"] <= cleared_floor(me["username"], "dm", r["chat_key"]):
            continue
        text = "Message deleted" if r["deleted"] else (r["body"] or "Attachment")
        out.append({"user": {"username": partner["username"], "display_name": partner["display_name"],
                             "avatar": partner.get("avatar", ""), "role": role_of(partner)},
                    "last": {"text": text, "ts": r["created"], "from": r["sender"]}})
    out.sort(key=lambda c: c["last"]["ts"], reverse=True)
    return out


def last_group_messages(me, group_ids):
    if not group_ids:
        return {}
    rows = _in("SELECT * FROM messages WHERE id IN (SELECT MAX(id) FROM messages WHERE chat_type = 'group' "
               "AND chat_key IN ({IN}) GROUP BY chat_key)", list(group_ids))
    out = {}
    for r in rows:
        if r["id"] > cleared_floor(me["username"], "group", r["chat_key"]):
            out[r["chat_key"]] = {"text": "Message deleted" if r["deleted"] else (r["body"] or "Attachment"),
                                  "ts": r["created"], "from": r["sender"]}
    return out


# ---------------------------------------------------------------- one-time move of the old data
def migrate_legacy():
    """Version 1 kept messages in two big lists. Move them into the messages table once."""
    old_dm = storage.read("messages")
    old_group = storage.read("group_messages")
    if not old_dm and not old_group:
        return 0
    rows = [("dm", dm_key(m["from"], m["to"]), m["from"], m["text"], m["ts"]) for m in old_dm]
    rows += [("group", str(m["group_id"]), m["from"], m["text"], m["ts"]) for m in old_group]
    rows.sort(key=lambda r: r[4])
    with db.transaction() as tx:
        for chat_type, chat_key, sender, body, ts in rows:
            tx.execute("INSERT INTO messages (chat_type, chat_key, sender, body, created) VALUES (?, ?, ?, ?, ?)",
                       (chat_type, chat_key, sender, body, ts))
    storage.write("messages", [])
    storage.write("group_messages", [])
    print(f"[MIGRATION] Moved {len(rows)} old messages into the messages table", flush=True)
    return len(rows)
