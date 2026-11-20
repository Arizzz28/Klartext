"""Registration (username -> email code -> password -> admin approval), login and logout."""
import hmac
import secrets
import time

from flask import Blueprint, g, jsonify, request

import config
import mailer
import storage
from security import (ApiError, check_password, create_token, DUMMY_HASH, find_user, hash_code,
                      hash_password, json_body, login_required, me_view, rate_limit,
                      valid_email, valid_password, valid_username)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _is_allowed(username, whitelist):
    name = username.lower()
    return name == config.ADMIN_USERNAME.lower() or name in whitelist


@bp.post("/register/start")
def register_start():
    data = json_body()
    username = valid_username(data.get("username"))
    email = valid_email(data.get("email"))
    rate_limit(f"reg:{request.remote_addr}", 10, 600)
    key = username.lower()
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = time.time()

    with storage.transaction("users", "whitelist", "verification") as db:
        if key in db["users"]:
            raise ApiError("That username is already taken.", 409)
        if not _is_allowed(username, db["whitelist"]):
            raise ApiError("That username is not on the whitelist. Ask an admin to add it.", 403)
        if any(u["email"].lower() == email.lower() for u in db["users"].values()):
            raise ApiError("That email address is already registered.", 409)
        db["verification"] = {k: v for k, v in db["verification"].items() if v["expires"] > now}
        db["verification"][key] = {
            "email": email, "code_hash": hash_code(code),
            "expires": now + config.CODE_TTL, "attempts": 0, "verified": False,
        }
    try:
        mailer.send_verification_code(email, code)
    except Exception:
        raise ApiError("Could not send the email. Please try again later.", 502)
    return jsonify({"message": "We sent a 6-digit code to your email."})


@bp.post("/register/verify")
def register_verify():
    data = json_body()
    key = valid_username(data.get("username")).lower()
    code = str(data.get("code", "")).strip()
    error = None
    with storage.transaction("verification") as db:
        rec = db["verification"].get(key)
        if not rec or rec["expires"] < time.time():
            error = ("This code has expired. Please start again.", 400)
        elif rec["attempts"] >= config.MAX_CODE_ATTEMPTS:
            error = ("Too many wrong codes. Please start again.", 429)
        else:
            rec["attempts"] += 1
            if hmac.compare_digest(rec["code_hash"], hash_code(code)):
                rec["verified"] = True
                rec["expires"] = time.time() + config.CODE_TTL
            else:
                error = ("That code is not correct.", 400)
    if error:  # raised AFTER the block, so the attempt counter is still saved
        raise ApiError(*error)
    return jsonify({"message": "Email verified."})


@bp.post("/register/complete")
def register_complete():
    data = json_body()
    username = valid_username(data.get("username"))
    password = valid_password(data.get("password"))
    key = username.lower()
    now = time.time()
    is_admin = key == config.ADMIN_USERNAME.lower()

    with storage.transaction("users", "verification") as db:
        rec = db["verification"].get(key)
        if not rec or not rec["verified"] or rec["expires"] < now:
            raise ApiError("Please verify your email first.", 400)
        if key in db["users"]:
            raise ApiError("That username is already taken.", 409)
        db["users"][key] = {
            "username": username, "email": rec["email"], "password_hash": hash_password(password),
            "display_name": username, "avatar": "", "is_admin": is_admin,
            "status": "active" if is_admin else "pending",   # normal users wait for an admin
            "token_version": 0, "created": now,
        }
        del db["verification"][key]
    message = ("Account created. You can log in now." if is_admin
               else "Account created. An admin has to approve it before you can log in.")
    return jsonify({"message": message, "pending": not is_admin}), 201


@bp.post("/login")
def login():
    data = json_body()
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    rate_limit(f"login:{request.remote_addr}:{username.lower()}", 10, 300)

    user = find_user(storage.read("users"), username)
    ok = check_password(user["password_hash"] if user else DUMMY_HASH, password)
    if not user or not ok:
        raise ApiError("Wrong username or password.", 401)
    if user["status"] == "pending":
        raise ApiError("Your account is waiting for admin approval.", 403)
    if user["status"] != "active":
        raise ApiError("This account has been suspended.", 403)
    return jsonify({"token": create_token(user), "user": me_view(user)})


@bp.post("/logout")
@login_required
def logout():
    # Raising the token version makes every old token of this user invalid.
    with storage.transaction("users") as db:
        db["users"][g.user["username"].lower()]["token_version"] += 1
    return jsonify({"message": "Logged out."})
