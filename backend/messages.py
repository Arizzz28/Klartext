"""Private messages. Only the two people in a conversation can read it."""
import time

from flask import Blueprint, g, jsonify, request

import config
import storage
from security import (ApiError, clean_text, find_user, json_body, login_required, public_user)

bp = Blueprint("messages", __name__, url_prefix="/api/messages")


def _partner(users, username):
    other = find_user(users, username)
    if not other or other["status"] != "active" or other["username"] == g.user["username"]:
        raise ApiError("User not found.", 404)
    return other


@bp.get("/conversations")
@login_required
def conversations():
    me = g.user["username"]
    users = storage.read("users")
    last = {}
    for m in storage.read("messages"):          # oldest first, so the last one wins
        if me in (m["from"], m["to"]):
            partner = m["to"] if m["from"] == me else m["from"]
            last[partner] = m
    result = []
    for partner, m in last.items():
        user = find_user(users, partner)
        if user and user["status"] == "active":
            result.append({"user": public_user(user), "last": {"text": m["text"], "ts": m["ts"], "from": m["from"]}})
    result.sort(key=lambda c: c["last"]["ts"], reverse=True)
    return jsonify(result)


@bp.get("/<username>")
@login_required
def get_chat(username):
    other = _partner(storage.read("users"), username)
    me, them = g.user["username"], other["username"]
    after = request.args.get("after", 0, type=int)
    msgs = [m for m in storage.read("messages")
            if m["id"] > after and {m["from"], m["to"]} == {me, them}]
    return jsonify([{"id": m["id"], "from": m["from"], "text": m["text"], "ts": m["ts"]} for m in msgs])


@bp.post("/<username>")
@login_required
def send_message(username):
    text = clean_text(json_body().get("text"), "Message", config.MAX_MESSAGE_LENGTH)
    with storage.transaction("users", "messages") as db:
        other = _partner(db["users"], username)
        msg = {"id": storage.next_id(db["messages"]), "from": g.user["username"],
               "to": other["username"], "text": text, "ts": time.time()}
        db["messages"].append(msg)
    return jsonify({"id": msg["id"], "from": msg["from"], "text": msg["text"], "ts": msg["ts"]}), 201
