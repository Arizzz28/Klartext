"""Audit log: every admin or moderator action is written here. Nobody can edit it through the app."""
import time

import db


def log(actor, action, target="", details=""):
    db.execute("INSERT INTO audit_log (ts, actor, action, target, details) VALUES (?, ?, ?, ?, ?)",
               (time.time(), actor, action, str(target)[:200], str(details)[:500]))
    print(f"[AUDIT] {actor} {action} {target}", flush=True)


def recent(limit=100, before=None):
    if before:
        return db.query("SELECT * FROM audit_log WHERE id < ? ORDER BY id DESC LIMIT ?", (before, limit))
    return db.query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
