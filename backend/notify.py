"""Notifications inside the app, unread counters (work across devices) and web push.

- Unread counters are stored on the SERVER (table read_state: per person and chat the last message they saw),
  so a message read on the phone is read on the iPad, too.
- Notifications (admins: new Pro offers; the Owner: permission requests; everybody: coins, ranks ...) live in the
  table notifications.
- Web push: the browser registers a subscription (endpoint + keys). The server sends a short message through
  the push service of the browser maker whenever somebody writes. Needs the VAPID keys (see gen_vapid.py).
"""
import json
import threading
import time

from flask import Blueprint, g, jsonify, request

import config
import db
import perms
import storage
from security import ApiError, json_body, login_required, need, perm_required

bp = Blueprint("notify", __name__, url_prefix="/api")


# ---------------------------------------------------------------- notifications
def notify(username, kind, text, link=""):
    db.execute("INSERT INTO notifications (username, kind, text, link, created) VALUES (?, ?, ?, ?, ?)",
               (username, kind, text[:300], link[:200], time.time()))


def users_with(key, exclude=()):
    ranks = perms.all_ranks()
    return [u["username"] for u in storage.read("users").values()
            if u["status"] == "active" and u["username"] not in exclude and perms.has_perm(u, key, ranks)]


def notify_perm(key, kind, text, link="", exclude=()):
    """Tell everybody who holds a permission (e.g. all admins who may read Pro offers)."""
    for name in users_with(key, exclude):
        notify(name, kind, text, link)


@bp.get("/notifications")
@login_required
def list_notifications():
    rows = db.query("SELECT id, kind, text, link, created, is_read FROM notifications WHERE username = ? "
                    "ORDER BY id DESC LIMIT 50", (g.user["username"],))
    unread = db.query("SELECT COUNT(*) AS n FROM notifications WHERE username = ? AND is_read = 0", (g.user["username"],))[0]["n"]
    return jsonify({"unread": unread, "items": [{**r, "is_read": bool(r["is_read"])} for r in rows]})


@bp.post("/notifications/read")
@login_required
def read_notifications():
    data = json_body()
    ids = data.get("ids")
    if ids is None:
        db.execute("UPDATE notifications SET is_read = 1 WHERE username = ?", (g.user["username"],))
    else:
        if not isinstance(ids, list) or len(ids) > 200 or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
            raise ApiError("Invalid list.")
        if ids:
            db.execute(f"UPDATE notifications SET is_read = 1 WHERE username = ? AND id IN ({db.placeholders(ids)})",
                       [g.user["username"], *ids])
    return jsonify({"message": "ok"})


# ---------------------------------------------------------------- unread counters
def unread_counts(user):
    low = user["username"].lower()
    groups = [gid for gid, gr in storage.read("groups").items() if user["username"] in gr["members"]]
    sql = ("SELECT m.chat_type, m.chat_key, COUNT(*) AS n FROM messages m "
           "LEFT JOIN read_state r ON r.username = ? AND r.chat_type = m.chat_type AND r.chat_key = m.chat_key "
           "LEFT JOIN chat_clears c ON c.username = ? AND c.chat_type = m.chat_type AND c.chat_key = m.chat_key "
           "WHERE m.sender <> ? AND m.is_system = 0 AND m.deleted = 0 "
           "AND m.id > COALESCE(r.last_id, 0) AND m.id > COALESCE(c.cleared_before, 0) "
           "AND ((m.chat_type = 'dm' AND (m.chat_key LIKE ? OR m.chat_key LIKE ?))")
    params = [user["username"], user["username"], user["username"], low + "|%", "%|" + low]
    if groups:
        sql += f" OR (m.chat_type = 'group' AND m.chat_key IN ({db.placeholders(groups)}))"
        params += groups
    sql += ") GROUP BY m.chat_type, m.chat_key"
    dms, grp = {}, {}
    for r in db.query(sql, params):
        if r["chat_type"] == "dm":
            parts = r["chat_key"].split("|")
            if low in parts and len(parts) == 2:
                dms[parts[0] if parts[1] == low else parts[1]] = r["n"]
        else:
            grp[r["chat_key"]] = r["n"]
    note = db.query("SELECT COUNT(*) AS n FROM notifications WHERE username = ? AND is_read = 0", (user["username"],))[0]["n"]
    invites = sum(1 for i in storage.read("invitations") if i["to"] == user["username"] and i["status"] == "pending")
    import extras
    return {"dm": dms, "group": grp, "chats": sum(dms.values()), "groups": sum(grp.values()),
            "notifications": note, "invitations": invites, "whatsnew": extras.unseen_count(user["username"])}


@bp.get("/unread")
@login_required
def unread():
    return jsonify(unread_counts(g.user))


@bp.post("/chats/<chat_type>/<key>/read")
@login_required
def mark_read(chat_type, key):
    import chat_service
    chat = chat_service.resolve(chat_type, key, g.user)
    last = db.query("SELECT MAX(id) AS m FROM messages WHERE chat_type = ? AND chat_key = ?", (chat["type"], chat["key"]))[0]["m"] or 0
    db.execute("INSERT INTO read_state (username, chat_type, chat_key, last_id) VALUES (?, ?, ?, ?) "
               "ON CONFLICT (username, chat_type, chat_key) DO UPDATE SET last_id = "
               "CASE WHEN excluded.last_id > read_state.last_id THEN excluded.last_id ELSE read_state.last_id END",
               (g.user["username"], chat["type"], chat["key"], last))
    return jsonify({"message": "ok"})


def init_read_state():
    """First start of Version 3: everything that already exists counts as read (no wall of old 'unread' badges)."""
    if db.query("SELECT 1 AS x FROM read_state LIMIT 1"):
        return 0
    rows = db.query("SELECT chat_type, chat_key, MAX(id) AS m FROM messages GROUP BY chat_type, chat_key")
    groups = storage.read("groups")
    n = 0
    for r in rows:
        if r["chat_type"] == "dm":
            members = [u for u in storage.read("users").values() if u["username"].lower() in r["chat_key"].split("|")]
            names = [u["username"] for u in members]
        else:
            names = list(groups.get(r["chat_key"], {}).get("members", {}))
        for name in names:
            db.execute("INSERT INTO read_state (username, chat_type, chat_key, last_id) VALUES (?, ?, ?, ?) "
                       "ON CONFLICT (username, chat_type, chat_key) DO NOTHING", (name, r["chat_type"], r["chat_key"], r["m"]))
            n += 1
    return n


# ---------------------------------------------------------------- web push
def push_enabled():
    return bool(config.VAPID_PUBLIC_KEY and config.VAPID_PRIVATE_KEY)


@bp.get("/push/key")
@login_required
def push_key():
    return jsonify({"enabled": push_enabled(), "public_key": config.VAPID_PUBLIC_KEY if push_enabled() else ""})


# The server sends a message to the address the browser gives it. Without a check, somebody could enter ANY web
# address and make this server call it (SSRF). So only the push services of the big browser makers are accepted.
PUSH_SERVICE_HOSTS = ("fcm.googleapis.com", "android.googleapis.com", "updates.push.services.mozilla.com",
                      "push.apple.com", "notify.windows.com")


def _is_push_service(endpoint):
    from urllib.parse import urlparse
    if not isinstance(endpoint, str) or len(endpoint) > 1000:
        return False
    try:
        p = urlparse(endpoint)
        port = p.port
    except ValueError:
        return False
    host = (p.hostname or "").lower()
    return (p.scheme == "https" and not p.username and not p.password and port in (None, 443)
            and any(host == h or host.endswith("." + h) for h in PUSH_SERVICE_HOSTS))


@bp.post("/push/subscribe")
@perm_required("push.use")
def push_subscribe():
    if not push_enabled():
        raise ApiError("Push messages are not set up on this server yet.", 503)
    data = json_body()
    keys = data.get("keys") or {}
    endpoint = str(data.get("endpoint", ""))
    if not _is_push_service(endpoint) or not isinstance(keys, dict) \
            or not isinstance(keys.get("p256dh"), str) or not isinstance(keys.get("auth"), str) \
            or len(keys["p256dh"]) > 200 or len(keys["auth"]) > 100:
        raise ApiError("Invalid push subscription.")
    n = db.query("SELECT COUNT(*) AS n FROM push_subscriptions WHERE username = ?", (g.user["username"],))[0]["n"]
    if n >= 10:
        db.execute("DELETE FROM push_subscriptions WHERE endpoint IN (SELECT endpoint FROM push_subscriptions "
                   "WHERE username = ? ORDER BY created LIMIT 1)", (g.user["username"],))
    db.execute("INSERT INTO push_subscriptions (endpoint, username, p256dh, auth, created) VALUES (?, ?, ?, ?, ?) "
               "ON CONFLICT (endpoint) DO UPDATE SET username = excluded.username, p256dh = excluded.p256dh, auth = excluded.auth",
               (endpoint, g.user["username"], keys["p256dh"], keys["auth"], time.time()))
    return jsonify({"message": "Push messages are on for this device."}), 201


@bp.post("/push/unsubscribe")
@login_required
def push_unsubscribe():
    endpoint = str(json_body().get("endpoint", ""))
    db.execute("DELETE FROM push_subscriptions WHERE endpoint = ? AND username = ?", (endpoint, g.user["username"]))
    return jsonify({"message": "Push messages are off for this device."})


def _webpush_send(subscription, payload):
    """One push. Separate function so tests can replace it."""
    from pywebpush import webpush
    webpush(subscription_info=subscription, data=payload, vapid_private_key=config.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": config.VAPID_SUBJECT}, ttl=3600)


def _deliver(usernames, payload):
    if not usernames:
        return
    rows = db.query(f"SELECT * FROM push_subscriptions WHERE username IN ({db.placeholders(usernames)})", list(usernames))
    for row in rows:
        try:
            _webpush_send({"endpoint": row["endpoint"], "keys": {"p256dh": row["p256dh"], "auth": row["auth"]}}, json.dumps(payload))
        except Exception as e:                       # noqa: BLE001 - one broken device must not stop the others
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):                 # the browser says this subscription is gone
                db.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (row["endpoint"],))
            else:
                print(f"[PUSH] failed: {type(e).__name__}", flush=True)


def push_to(usernames, title, body, url="#/chats", sync=False):
    """Sends a push to all devices of the given people (in the background so the request stays fast)."""
    if not push_enabled() or not usernames:
        return
    payload = {"title": title, "body": body, "url": url}
    if sync:
        _deliver(list(usernames), payload)
    else:
        threading.Thread(target=_deliver, args=(list(usernames), payload), daemon=True).start()


def on_message(chat, sender, text, has_files=False, sync=False):
    """Called after a message was saved: tell the other members."""
    if not push_enabled():
        return
    users = storage.read("users")
    ranks = perms.all_ranks()
    if chat["type"] == "dm":
        names = [chat["partner"]["username"]]
        title, url = sender["display_name"], f"#/chats/{sender['username']}"
    else:
        names = [m for m in chat["group"]["members"] if m != sender["username"]]
        title, url = f"{sender['display_name']} · {chat['group']['name']}", f"#/groups/{chat['group']['id']}"
    plain, preview = [], []
    for name in names:
        u = users.get(name.lower())
        if not u or u["status"] != "active" or not perms.has_perm(u, "push.use", ranks):
            continue
        (preview if u.get("prefs", {}).get("push_preview") else plain).append(name)
    snippet = (text or ("Sent a file" if has_files else "New message"))[:90]
    push_to(preview, title, snippet, url, sync)
    push_to(plain, title, "New message", url, sync)
