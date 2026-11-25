"""Calendar events and tasks, optionally shared with other people."""
import time

from flask import Blueprint, g, jsonify, request

import db
import notify
import storage
from security import ApiError, clean_text, find_user, json_body, perm_required

bp = Blueprint("planner", __name__, url_prefix="/api")


def _ts(value, field, required=True):
    if value in (None, ""):
        if required:
            raise ApiError(f"'{field}' is missing.")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < 4_102_444_800:
        raise ApiError(f"'{field}' is not a valid time.")
    return float(value)


def _share_list(data, me):
    names = data.get("share_with") or []
    if not isinstance(names, list) or len(names) > 20:
        raise ApiError("Share with at most 20 people.")
    users = storage.read("users")
    out = []
    for n in names:
        u = find_user(users, n)
        if not u or u["status"] != "active":
            raise ApiError(f"User '{n}' not found.", 404)
        if u["username"] != me and u["username"] not in out:
            out.append(u["username"])
    return out


def _shares(table, key, ids):
    out = {}
    if ids:
        for r in db.query(f"SELECT {key}, username FROM {table} WHERE {key} IN ({db.placeholders(ids)})", ids):
            out.setdefault(r[key], []).append(r["username"])
    return out


# ---------------------------------------------------------------- calendar
def _event_view(r, shares, me):
    return {"id": r["id"], "title": r["title"], "note": r["note"], "start": r["start_ts"], "end": r["end_ts"],
            "owner": r["owner"], "mine": r["owner"] == me, "shared_with": shares.get(r["id"], []) if r["owner"] == me else []}


@bp.get("/events")
@perm_required("tabs.calendar")
def list_events():
    me = g.user["username"]
    start = request.args.get("from", type=float) or 0
    end = request.args.get("to", type=float) or 4_102_444_800
    rows = db.query("SELECT * FROM events WHERE (owner = ? OR id IN (SELECT event_id FROM event_shares WHERE username = ?)) "
                    "AND start_ts >= ? AND start_ts <= ? ORDER BY start_ts LIMIT 500", (me, me, start, end))
    shares = _shares("event_shares", "event_id", [r["id"] for r in rows])
    return jsonify([_event_view(r, shares, me) for r in rows])


@bp.post("/events")
@perm_required("tabs.calendar")
def create_event():
    data = json_body()
    me = g.user["username"]
    title = clean_text(data.get("title"), "Title", 120)
    note = clean_text(data.get("note"), "Note", 1000, required=False)
    start, end = _ts(data.get("start"), "start"), _ts(data.get("end"), "end", False)
    if end is not None and end < start:
        raise ApiError("The end is before the start.")
    share = _share_list(data, me)
    if db.query("SELECT COUNT(*) AS n FROM events WHERE owner = ?", (me,))[0]["n"] >= 1000:
        raise ApiError("You have too many events.", 409)
    eid = db.query("INSERT INTO events (owner, title, note, start_ts, end_ts, created) VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
                   (me, title, note, start, end, time.time()))[0]["id"]
    for n in share:
        db.execute("INSERT INTO event_shares (event_id, username) VALUES (?, ?) ON CONFLICT DO NOTHING", (eid, n))
        notify.notify(n, "event", f"{g.user['display_name']} shared the event '{title}' with you.", "#/calendar")
    return jsonify({"id": eid}), 201


@bp.put("/events/<int:eid>")
@perm_required("tabs.calendar")
def update_event(eid):
    data = json_body()
    me = g.user["username"]
    title = clean_text(data.get("title"), "Title", 120)
    note = clean_text(data.get("note"), "Note", 1000, required=False)
    start, end = _ts(data.get("start"), "start"), _ts(data.get("end"), "end", False)
    if end is not None and end < start:
        raise ApiError("The end is before the start.")
    share = _share_list(data, me)
    if not db.execute("UPDATE events SET title = ?, note = ?, start_ts = ?, end_ts = ? WHERE id = ? AND owner = ?",
                      (title, note, start, end, eid, me)):
        raise ApiError("Event not found.", 404)
    old = {r["username"] for r in db.query("SELECT username FROM event_shares WHERE event_id = ?", (eid,))}
    db.execute("DELETE FROM event_shares WHERE event_id = ?", (eid,))
    for n in share:
        db.execute("INSERT INTO event_shares (event_id, username) VALUES (?, ?)", (eid, n))
        if n not in old:
            notify.notify(n, "event", f"{g.user['display_name']} shared the event '{title}' with you.", "#/calendar")
    return jsonify({"message": "Saved."})


@bp.delete("/events/<int:eid>")
@perm_required("tabs.calendar")
def delete_event(eid):
    if not db.execute("DELETE FROM events WHERE id = ? AND owner = ?", (eid, g.user["username"])):
        raise ApiError("Event not found.", 404)
    db.execute("DELETE FROM event_shares WHERE event_id = ?", (eid,))
    return jsonify({"message": "Deleted."})


# ---------------------------------------------------------------- tasks
def _task_view(r, shares, me):
    return {"id": r["id"], "title": r["title"], "done": bool(r["done"]), "due": r["due"], "owner": r["owner"],
            "mine": r["owner"] == me, "shared_with": shares.get(r["id"], []) if r["owner"] == me else []}


@bp.get("/tasks")
@perm_required("tabs.tasks")
def list_tasks():
    me = g.user["username"]
    rows = db.query("SELECT * FROM tasks WHERE owner = ? OR id IN (SELECT task_id FROM task_shares WHERE username = ?) "
                    "ORDER BY done, COALESCE(due, 9999999999), id DESC LIMIT 500", (me, me))
    shares = _shares("task_shares", "task_id", [r["id"] for r in rows])
    return jsonify([_task_view(r, shares, me) for r in rows])


@bp.post("/tasks")
@perm_required("tabs.tasks")
def create_task():
    data = json_body()
    me = g.user["username"]
    title = clean_text(data.get("title"), "Task", 200)
    due = _ts(data.get("due"), "due", False)
    share = _share_list(data, me)
    if db.query("SELECT COUNT(*) AS n FROM tasks WHERE owner = ?", (me,))[0]["n"] >= 1000:
        raise ApiError("You have too many tasks.", 409)
    tid = db.query("INSERT INTO tasks (owner, title, due, created) VALUES (?, ?, ?, ?) RETURNING id", (me, title, due, time.time()))[0]["id"]
    for n in share:
        db.execute("INSERT INTO task_shares (task_id, username) VALUES (?, ?) ON CONFLICT DO NOTHING", (tid, n))
        notify.notify(n, "task", f"{g.user['display_name']} shared the task '{title}' with you.", "#/tasks")
    return jsonify({"id": tid}), 201


@bp.put("/tasks/<int:tid>")
@perm_required("tabs.tasks")
def update_task(tid):
    data = json_body()
    me = g.user["username"]
    rows = db.query("SELECT * FROM tasks WHERE id = ? AND (owner = ? OR id IN (SELECT task_id FROM task_shares WHERE username = ?))", (tid, me, me))
    if not rows:
        raise ApiError("Task not found.", 404)
    task = rows[0]
    done = task["done"]
    if "done" in data:
        if not isinstance(data["done"], bool):
            raise ApiError("'done' must be true or false.")
        done = 1 if data["done"] else 0
    if task["owner"] == me:          # only the owner can rename, reschedule or re-share; everybody can tick it off
        title = clean_text(data.get("title", task["title"]), "Task", 200)
        due = _ts(data["due"], "due", False) if "due" in data else task["due"]
        db.execute("UPDATE tasks SET title = ?, due = ?, done = ? WHERE id = ?", (title, due, done, tid))
        if "share_with" in data:
            old = {r["username"] for r in db.query("SELECT username FROM task_shares WHERE task_id = ?", (tid,))}
            share = _share_list(data, me)
            db.execute("DELETE FROM task_shares WHERE task_id = ?", (tid,))
            for n in share:
                db.execute("INSERT INTO task_shares (task_id, username) VALUES (?, ?)", (tid, n))
                if n not in old:
                    notify.notify(n, "task", f"{g.user['display_name']} shared the task '{title}' with you.", "#/tasks")
    else:
        db.execute("UPDATE tasks SET done = ? WHERE id = ?", (done, tid))
    return jsonify({"message": "Saved."})


@bp.delete("/tasks/<int:tid>")
@perm_required("tabs.tasks")
def delete_task(tid):
    if not db.execute("DELETE FROM tasks WHERE id = ? AND owner = ?", (tid, g.user["username"])):
        raise ApiError("Task not found.", 404)
    db.execute("DELETE FROM task_shares WHERE task_id = ?", (tid,))
    return jsonify({"message": "Deleted."})
