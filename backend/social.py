"""Global search, music playlists (links to legal streaming services only), the forum and custom tabs."""
import re
import time
from urllib.parse import urlparse

from flask import Blueprint, g, jsonify, request

import db
import perms
import storage
from security import ApiError, clean_text, find_user, json_body, need, perm_required, public_user

bp = Blueprint("social", __name__, url_prefix="/api")


# ================================================================ search
def _like(q):
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").lower() + "%"


@bp.get("/search")
@perm_required("tabs.search")
def search():
    q = request.args.get("q", "").strip()[:60]
    if len(q) < 2:
        return jsonify({"users": [], "groups": [], "messages": [], "notes": [], "tasks": [], "events": []})
    me, low = g.user["username"], g.user["username"].lower()
    pat, ql = _like(q), q.lower()
    ranks = perms.all_ranks()
    users = storage.read("users")
    found_users = [public_user(u, ranks) for u in users.values() if u["status"] == "active" and u["username"] != me
                   and (ql in u["username"].lower() or ql in u["display_name"].lower())][:10]
    groups = [{"id": gr["id"], "name": gr["name"], "member": me in gr["members"]} for gr in storage.read("groups").values()
              if ql in gr["name"].lower() and (me in gr["members"] or gr["join_mode"] == "open")][:10]
    my_groups = [gid for gid, gr in storage.read("groups").items() if me in gr["members"]]
    sql = ("SELECT m.id, m.chat_type, m.chat_key, m.sender, m.body, m.created FROM messages m "
           "LEFT JOIN chat_clears c ON c.username = ? AND c.chat_type = m.chat_type AND c.chat_key = m.chat_key "
           "WHERE m.deleted = 0 AND m.is_system = 0 AND LOWER(m.body) LIKE ? ESCAPE '\\' AND m.id > COALESCE(c.cleared_before, 0) "
           "AND ((m.chat_type = 'dm' AND (m.chat_key LIKE ? OR m.chat_key LIKE ?))")
    params = [me, pat, low + "|%", "%|" + low]
    if my_groups:
        sql += f" OR (m.chat_type = 'group' AND m.chat_key IN ({db.placeholders(my_groups)}))"
        params += my_groups
    sql += ") ORDER BY m.id DESC LIMIT 30"
    messages = []
    for r in db.query(sql, params):
        if r["chat_type"] == "dm":
            parts = r["chat_key"].split("|")
            if low not in parts:
                continue
            other = parts[0] if parts[1] == low else parts[1]
            link, where = f"#/chats/{other}", (find_user(users, other) or {}).get("display_name", other)
        else:
            gr = storage.read("groups").get(r["chat_key"])
            link, where = f"#/groups/{r['chat_key']}", gr["name"] if gr else "Group"
        messages.append({"text": r["body"][:160], "where": where, "link": link, "ts": r["created"],
                         "from": (find_user(users, r["sender"]) or {}).get("display_name", r["sender"])})
    notes = tasks = events = []
    if perms.has_perm(g.user, "tabs.notes"):
        notes = [{"id": r["id"], "title": r["title"] or r["body"][:40]} for r in db.query(
            "SELECT id, title, body FROM notes WHERE username = ? AND (LOWER(title) LIKE ? ESCAPE '\\' OR LOWER(body) LIKE ? ESCAPE '\\') LIMIT 10", (me, pat, pat))]
    if perms.has_perm(g.user, "tabs.tasks"):
        tasks = [{"id": r["id"], "title": r["title"]} for r in db.query(
            "SELECT id, title FROM tasks WHERE (owner = ? OR id IN (SELECT task_id FROM task_shares WHERE username = ?)) "
            "AND LOWER(title) LIKE ? ESCAPE '\\' LIMIT 10", (me, me, pat))]
    if perms.has_perm(g.user, "tabs.calendar"):
        events = [{"id": r["id"], "title": r["title"], "start": r["start_ts"]} for r in db.query(
            "SELECT id, title, start_ts FROM events WHERE (owner = ? OR id IN (SELECT event_id FROM event_shares WHERE username = ?)) "
            "AND LOWER(title) LIKE ? ESCAPE '\\' LIMIT 10", (me, me, pat))]
    return jsonify({"users": found_users, "groups": groups, "messages": messages, "notes": notes, "tasks": tasks, "events": events})


# ================================================================ music
# Only links to well-known streaming services. We do not host, copy or play any audio ourselves, and nothing is
# loaded from these services until you click a link. Whether a track on those services is legal is up to the service.
MUSIC_HOSTS = ("youtube.com", "youtu.be", "music.youtube.com", "soundcloud.com", "open.spotify.com", "spotify.com",
               "bandcamp.com", "music.apple.com", "deezer.com", "tidal.com", "audiomack.com")


def _music_url(value):
    value = str(value or "").strip()
    try:
        parsed = urlparse(value)
    except ValueError:
        raise ApiError("That link is not valid.")
    host = (parsed.hostname or "").lower()
    ok = parsed.scheme == "https" and len(value) <= 400 and any(host == h or host.endswith("." + h) for h in MUSIC_HOSTS)
    if not ok:
        raise ApiError("Only https links to YouTube, SoundCloud, Spotify, Bandcamp, Apple Music, Deezer, Tidal or Audiomack are allowed.")
    return value


def _playlist_row(r, me, tracks):
    return {"id": r["id"], "name": r["name"], "visibility": r["visibility"], "owner": r["owner"], "mine": r["owner"] == me,
            "tracks": tracks.get(r["id"], [])}


@bp.get("/playlists")
@perm_required("tabs.music")
def list_playlists():
    me = g.user["username"]
    rows = db.query("SELECT * FROM playlists WHERE owner = ? OR visibility = 'everyone' ORDER BY id DESC LIMIT 100", (me,))
    tracks = {}
    if rows:
        for t in db.query(f"SELECT id, playlist_id, title, url FROM playlist_tracks WHERE playlist_id IN ({db.placeholders(rows)}) ORDER BY id",
                          [r["id"] for r in rows]):
            tracks.setdefault(t["playlist_id"], []).append({"id": t["id"], "title": t["title"], "url": t["url"]})
    return jsonify([_playlist_row(r, me, tracks) for r in rows])


@bp.post("/playlists")
@perm_required("tabs.music")
def create_playlist():
    data = json_body()
    name = clean_text(data.get("name"), "Name", 60)
    vis = data.get("visibility", "private")
    if vis not in ("private", "everyone"):
        raise ApiError("Visibility must be private or everyone.")
    if db.query("SELECT COUNT(*) AS n FROM playlists WHERE owner = ?", (g.user["username"],))[0]["n"] >= 30:
        raise ApiError("You can have at most 30 playlists.", 409)
    pid = db.query("INSERT INTO playlists (owner, name, visibility, created) VALUES (?, ?, ?, ?) RETURNING id",
                   (g.user["username"], name, vis, time.time()))[0]["id"]
    return jsonify({"id": pid}), 201


@bp.delete("/playlists/<int:pid>")
@perm_required("tabs.music")
def delete_playlist(pid):
    if not db.execute("DELETE FROM playlists WHERE id = ? AND owner = ?", (pid, g.user["username"])):
        raise ApiError("Playlist not found.", 404)
    db.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (pid,))
    return jsonify({"message": "Deleted."})


@bp.post("/playlists/<int:pid>/tracks")
@perm_required("tabs.music")
def add_track(pid):
    data = json_body()
    if not db.query("SELECT 1 AS x FROM playlists WHERE id = ? AND owner = ?", (pid, g.user["username"])):
        raise ApiError("Playlist not found.", 404)
    title = clean_text(data.get("title"), "Title", 120)
    url = _music_url(data.get("url"))
    if db.query("SELECT COUNT(*) AS n FROM playlist_tracks WHERE playlist_id = ?", (pid,))[0]["n"] >= 200:
        raise ApiError("A playlist can have at most 200 tracks.", 409)
    db.execute("INSERT INTO playlist_tracks (playlist_id, title, url, added_by, created) VALUES (?, ?, ?, ?, ?)",
               (pid, title, url, g.user["username"], time.time()))
    return jsonify({"message": "Added."}), 201


@bp.delete("/playlists/<int:pid>/tracks/<int:tid>")
@perm_required("tabs.music")
def delete_track(pid, tid):
    if not db.query("SELECT 1 AS x FROM playlists WHERE id = ? AND owner = ?", (pid, g.user["username"])):
        raise ApiError("Playlist not found.", 404)
    db.execute("DELETE FROM playlist_tracks WHERE id = ? AND playlist_id = ?", (tid, pid))
    return jsonify({"message": "Removed."})


# ================================================================ forum
FORUM_STATUS = ("open", "planned", "done", "declined")


def _post_view(r, me, users):
    votes = db.query("SELECT COUNT(*) AS n FROM forum_votes WHERE post_id = ?", (r["id"],))[0]["n"]
    mine = bool(db.query("SELECT 1 AS x FROM forum_votes WHERE post_id = ? AND username = ?", (r["id"], me)))
    comments = db.query("SELECT COUNT(*) AS n FROM forum_comments WHERE post_id = ?", (r["id"],))[0]["n"]
    return {"id": r["id"], "title": r["title"], "body": r["body"], "created": r["created"], "status": r["status"],
            "pinned": bool(r["pinned"]), "author": (find_user(users, r["author"]) or {}).get("display_name", "Deleted user"),
            "author_username": r["author"], "votes": votes, "voted": mine, "comments": comments}


@bp.get("/forum")
@perm_required("tabs.forum")
def forum_list():
    rows = db.query("SELECT * FROM forum_posts ORDER BY pinned DESC, id DESC LIMIT 100")
    users = storage.read("users")
    return jsonify([_post_view(r, g.user["username"], users) for r in rows])


@bp.post("/forum")
@perm_required("tabs.forum")
def forum_create():
    data = json_body()
    title = clean_text(data.get("title"), "Title", 120)
    body = clean_text(data.get("body"), "Text", 3000, required=False)
    if db.query("SELECT COUNT(*) AS n FROM forum_posts WHERE author = ? AND created > ?", (g.user["username"], time.time() - 3600))[0]["n"] >= 5:
        raise ApiError("Please wait a little before posting again.", 429)
    pid = db.query("INSERT INTO forum_posts (author, title, body, created) VALUES (?, ?, ?, ?) RETURNING id",
                   (g.user["username"], title, body, time.time()))[0]["id"]
    return jsonify({"id": pid}), 201


@bp.post("/forum/<int:pid>/vote")
@perm_required("tabs.forum")
def forum_vote(pid):
    if not db.query("SELECT 1 AS x FROM forum_posts WHERE id = ?", (pid,)):
        raise ApiError("Post not found.", 404)
    me = g.user["username"]
    if db.execute("DELETE FROM forum_votes WHERE post_id = ? AND username = ?", (pid, me)):
        return jsonify({"voted": False})
    db.execute("INSERT INTO forum_votes (post_id, username) VALUES (?, ?) ON CONFLICT DO NOTHING", (pid, me))
    return jsonify({"voted": True})


@bp.get("/forum/<int:pid>/comments")
@perm_required("tabs.forum")
def forum_comments(pid):
    users = storage.read("users")
    rows = db.query("SELECT * FROM forum_comments WHERE post_id = ? ORDER BY id LIMIT 300", (pid,))
    return jsonify([{"id": r["id"], "body": r["body"], "created": r["created"], "author_username": r["author"],
                     "author": (find_user(users, r["author"]) or {}).get("display_name", "Deleted user")} for r in rows])


@bp.post("/forum/<int:pid>/comments")
@perm_required("tabs.forum")
def forum_comment(pid):
    if not db.query("SELECT 1 AS x FROM forum_posts WHERE id = ?", (pid,)):
        raise ApiError("Post not found.", 404)
    body = clean_text(json_body().get("body"), "Comment", 1000)
    db.execute("INSERT INTO forum_comments (post_id, author, body, created) VALUES (?, ?, ?, ?)", (pid, g.user["username"], body, time.time()))
    return jsonify({"message": "Posted."}), 201


@bp.patch("/forum/<int:pid>")
@perm_required("tabs.forum")
def forum_moderate(pid):
    need(g.user, "chat.moderate")
    data = json_body()
    if "status" in data:
        if data["status"] not in FORUM_STATUS:
            raise ApiError("Unknown status.")
        db.execute("UPDATE forum_posts SET status = ? WHERE id = ?", (data["status"], pid))
    if "pinned" in data:
        db.execute("UPDATE forum_posts SET pinned = ? WHERE id = ?", (1 if data["pinned"] is True else 0, pid))
    return jsonify({"message": "Saved."})


@bp.delete("/forum/<int:pid>")
@perm_required("tabs.forum")
def forum_delete(pid):
    rows = db.query("SELECT author FROM forum_posts WHERE id = ?", (pid,))
    if not rows:
        raise ApiError("Post not found.", 404)
    if rows[0]["author"] != g.user["username"]:
        need(g.user, "chat.moderate")
    for table, col in (("forum_comments", "post_id"), ("forum_votes", "post_id")):
        db.execute(f"DELETE FROM {table} WHERE {col} = ?", (pid,))
    db.execute("DELETE FROM forum_posts WHERE id = ?", (pid,))
    return jsonify({"message": "Deleted."})


@bp.delete("/forum/<int:pid>/comments/<int:cid>")
@perm_required("tabs.forum")
def forum_delete_comment(pid, cid):
    rows = db.query("SELECT author FROM forum_comments WHERE id = ? AND post_id = ?", (cid, pid))
    if not rows:
        raise ApiError("Comment not found.", 404)
    if rows[0]["author"] != g.user["username"]:
        need(g.user, "chat.moderate")
    db.execute("DELETE FROM forum_comments WHERE id = ?", (cid,))
    return jsonify({"message": "Deleted."})


# ================================================================ custom tabs
URL_LINE = re.compile(r"^(.{1,80})\s*\|\s*(https://\S{3,300})$")


def _custom_input(data):
    title = clean_text(data.get("title"), "Title", 30)
    kind = data.get("kind", "text")
    if kind not in ("text", "links"):
        raise ApiError("Type must be 'text' or 'links'.")
    content = clean_text(data.get("content"), "Content", 5000, required=False)
    if kind == "links":
        for line in filter(None, (l.strip() for l in content.splitlines())):
            if not URL_LINE.match(line):
                raise ApiError("Every line must look like:  Name | https://address")
    return title, kind, content


@bp.get("/custom-tabs")
@perm_required("tabs.custom")
def custom_list():
    rows = db.query("SELECT id, title, kind, content FROM custom_tabs WHERE username = ? ORDER BY id", (g.user["username"],))
    return jsonify(rows)


@bp.post("/custom-tabs")
@perm_required("tabs.custom")
def custom_create():
    title, kind, content = _custom_input(json_body())
    if db.query("SELECT COUNT(*) AS n FROM custom_tabs WHERE username = ?", (g.user["username"],))[0]["n"] >= 10:
        raise ApiError("You can have at most 10 custom tabs.", 409)
    tid = db.query("INSERT INTO custom_tabs (username, title, kind, content, created) VALUES (?, ?, ?, ?, ?) RETURNING id",
                   (g.user["username"], title, kind, content, time.time()))[0]["id"]
    return jsonify({"id": tid}), 201


@bp.put("/custom-tabs/<int:tid>")
@perm_required("tabs.custom")
def custom_update(tid):
    title, kind, content = _custom_input(json_body())
    if not db.execute("UPDATE custom_tabs SET title = ?, kind = ?, content = ? WHERE id = ? AND username = ?",
                      (title, kind, content, tid, g.user["username"])):
        raise ApiError("Tab not found.", 404)
    return jsonify({"message": "Saved."})


@bp.delete("/custom-tabs/<int:tid>")
@perm_required("tabs.custom")
def custom_delete(tid):
    if not db.execute("DELETE FROM custom_tabs WHERE id = ? AND username = ?", (tid, g.user["username"])):
        raise ApiError("Tab not found.", 404)
    return jsonify({"message": "Deleted."})
