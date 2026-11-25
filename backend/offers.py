"""Pro offers: instead of paying, a person offers something (help, an idea, a favour). No real money is involved.
Admins are notified, read the offer and may reward it with a temporary rank. The Owner sets the rules text."""
import time

from flask import Blueprint, g, jsonify

import appsettings
import db
import notify
from security import ApiError, clean_text, json_body, perm_required

bp = Blueprint("offers", __name__, url_prefix="/api/offers")


@bp.get("")
@perm_required("offers.create")
def mine():
    cfg = appsettings.get()["offers"]
    rows = db.query("SELECT id, text, created, status, answer, reward FROM offers WHERE username = ? ORDER BY id DESC LIMIT 20",
                    (g.user["username"],))
    return jsonify({"enabled": cfg["enabled"], "rules": cfg["rules"], "offers": rows})


@bp.post("")
@perm_required("offers.create")
def create():
    cfg = appsettings.get()["offers"]
    if not cfg["enabled"]:
        raise ApiError("Pro offers are switched off at the moment.", 403)
    text = clean_text(json_body().get("text"), "Offer", 600)
    if len(text) < 10:
        raise ApiError("Please describe your offer in a few words (at least 10 characters).")
    if db.query("SELECT 1 AS x FROM offers WHERE username = ? AND status = 'open'", (g.user["username"],)):
        raise ApiError("You already have an open offer. Please wait for the answer.", 409)
    if db.query("SELECT COUNT(*) AS n FROM offers WHERE username = ? AND created > ?", (g.user["username"], time.time() - 86400))[0]["n"] >= 3:
        raise ApiError("You can send at most 3 offers per day.", 429)
    db.execute("INSERT INTO offers (username, text, created) VALUES (?, ?, ?)", (g.user["username"], text, time.time()))
    notify.notify_perm("admin.offers", "offer", f"New Pro offer from {g.user['display_name']}.", "#/admin")
    return jsonify({"message": "Thank you! The admins will have a look."}), 201
