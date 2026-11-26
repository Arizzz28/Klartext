"""The Owner's PC as an extra server ("PC backend").

How it works (details and security notes: README, section "PC server"):
- The PC runs THE SAME program (this backend) with the SAME database and file storage settings. Nothing is stored on the PC:
  it only does the computing. Data stays in Neon (database) and Backblaze (files). If the PC is switched off, nothing is lost.
- The PC reports "I am online" to the normal server every 30 seconds (heartbeat) and tells it its public address (a tunnel such as
  cloudflared, because a home PC has no public address). The secret PC_SECRET (in both .env files) proves it is really the PC.
- A person is sent to the PC only if: the Owner switched "PC server" on (Admin -> Settings), the PC reported in within the last
  90 seconds, and the person's rank has the permission "pc.backend" AND the person switched it on for themselves.
  Otherwise the normal server (Render) is used. If the PC goes away while somebody uses it, the browser falls back to the normal server
  and shows a message.
"""
import hmac
import time

from flask import Blueprint, g, jsonify, request

import appsettings
import config
import db
import perms
from security import ApiError, json_body, login_required, perm_required

bp = Blueprint("pc", __name__, url_prefix="/api/pc")
FRESH_SECONDS = 90


def _status():
    rows = db.query("SELECT url, ts FROM pc_status WHERE id = 1")
    return rows[0] if rows else {"url": "", "ts": 0}


def online():
    s = _status()
    return bool(s["url"]) and time.time() - s["ts"] < FRESH_SECONDS


@bp.post("/heartbeat")
def heartbeat():
    """Called by the PC. No login: the shared secret is the proof."""
    if not config.PC_SECRET:
        raise ApiError("The PC feature is not set up.", 404)
    sent = request.headers.get("X-PC-Secret", "")
    if not hmac.compare_digest(sent.encode(), config.PC_SECRET.encode()):
        raise ApiError("Wrong secret.", 403)
    url = str(json_body().get("url", "")).strip().rstrip("/")
    if url and not (url.startswith("https://") and len(url) < 200 and " " not in url):
        raise ApiError("The address must start with https://.")
    now = time.time()
    db.execute("INSERT INTO pc_status (id, url, ts) VALUES (1, ?, ?) ON CONFLICT (id) DO UPDATE SET url = ?, ts = ?", (url, now, url, now))
    return jsonify({"ok": True})


@bp.get("/route")
@login_required
def route():
    """Where should this person's browser send its requests? The answer is a hint; the PC checks the login token itself."""
    s = appsettings.get()["pc"]
    if not config.PC_SECRET or not s["enabled"]:
        return jsonify({"url": None, "reason": "off"})
    if not perms.has_perm(g.user, "pc.backend"):
        return jsonify({"url": None, "reason": "rank"})
    if not g.user.get("prefs", {}).get("use_pc"):
        return jsonify({"url": None, "reason": "personal_off"})
    if not online():
        return jsonify({"url": None, "reason": "pc_offline", "message": "The PC server is switched off right now. The normal server is used."})
    return jsonify({"url": _status()["url"], "reason": "ok"})


@bp.get("/status")
@perm_required("admin.settings")
def status():
    s = _status()
    return jsonify({"configured": bool(config.PC_SECRET), "enabled": appsettings.get()["pc"]["enabled"], "online": online(),
                    "last_seen": s["ts"] or None, "url": s["url"] or None})
