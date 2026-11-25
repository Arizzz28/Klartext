
"""Registration (username -> email code -> password -> admin approval), login and logout."""

import hmac
import secrets
import time

from flask import Blueprint, g, jsonify, request

import appsettings
import config
import db
import legalconf
import mailer
import perms
import storage
from security import (
    ApiError,
    check_password,
    create_token,
    DUMMY_HASH,
    find_user,
    hash_code,
    hash_password,
    json_body,
    login_required,
    me_view,
    rate_limit,
    valid_email,
    valid_password,
    valid_username,
)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _is_allowed(username, whitelist):
    name = username.lower()
    return name in (config.ADMIN_USERNAME.lower(), config.OWNER_USERNAME.lower()) or name in whitelist


@bp.post("/register/start")
def register_start():
    print("[AUTH] Registration started", flush=True)

    data = json_body()
    username = valid_username(data.get("username"))
    email = valid_email(data.get("email"))
    # The checkbox is checked on the SERVER too (not only in the browser), and the version is stored.
    if data.get("accept_terms") is not True:
        raise ApiError("Please accept the Terms of Service and the Privacy Policy to create an account.")
    if data.get("terms_version") != legalconf.TERMS_VERSION or data.get("privacy_version") != legalconf.PRIVACY_VERSION:
        raise ApiError("The legal texts were updated. Please reload the page and read them again.", 409)

    print("[AUTH] Validation successful", flush=True)

    rate_limit(f"reg:{request.remote_addr}", 10, 600)

    key = username.lower()
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = time.time()

    print("[AUTH] Verification code generated", flush=True)

    with storage.transaction("users", "whitelist", "verification") as db:
        if key in db["users"]:
            raise ApiError("That username is already taken.", 409)

        # Registration mode is set by the admins: whitelist | open_approval | closed
        mode = appsettings.get()["registration_mode"]
        is_main_admin = key in (config.ADMIN_USERNAME.lower(), config.OWNER_USERNAME.lower())
        if mode == "closed" and not is_main_admin:
            raise ApiError("Registration is closed at the moment.", 403)
        if mode == "whitelist" and not _is_allowed(username, db["whitelist"]):
            raise ApiError(
                "That username is not on the whitelist. Ask an admin to add it.",
                403
            )

        if any(
            u["email"].lower() == email.lower()
            for u in db["users"].values()
        ):
            raise ApiError("That email address is already registered.", 409)

        db["verification"] = {
            k: v for k, v in db["verification"].items()
            if v["expires"] > now
        }

        db["verification"][key] = {
            "email": email,
            "code_hash": hash_code(code),
            "expires": now + config.CODE_TTL,
            "attempts": 0,
            "verified": False,
            "consent": legalconf.consent_record(),
        }

    print("[AUTH] Verification code saved", flush=True)
    print("[AUTH] Calling mailer", flush=True)

    try:
        mailer.send_verification_code(email, code)
    except Exception as e:
        print(f"[AUTH] Mailer exception: {type(e).__name__}", flush=True)
        raise ApiError(
            "Could not send the email. Please try again later.",
            502
        )

    print("[AUTH] Registration completed", flush=True)

    return jsonify({
        "message": "We sent a 6-digit code to your email."
    })


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

            if hmac.compare_digest(
                rec["code_hash"],
                hash_code(code)
            ):
                rec["verified"] = True
                rec["expires"] = time.time() + config.CODE_TTL
            else:
                error = ("That code is not correct.", 400)

    if error:
        raise ApiError(*error)

    return jsonify({"message": "Email verified."})


@bp.post("/register/complete")
def register_complete():
    data = json_body()

    username = valid_username(data.get("username"))
    password = valid_password(data.get("password"))

    key = username.lower()
    now = time.time()

    is_admin = key == config.OWNER_USERNAME.lower()

    with storage.transaction("users", "verification", "ranks") as db:
        rec = db["verification"].get(key)

        if not rec or not rec["verified"] or rec["expires"] < now:
            raise ApiError("Please verify your email first.", 400)

        if key in db["users"]:
            raise ApiError("That username is already taken.", 409)

        db["users"][key] = {
            "username": username,
            "email": rec["email"],
            "password_hash": hash_password(password),
            "display_name": username,
            "avatar": "",
            "rank": perms.owner_rank_id(db["ranks"]) if is_admin else perms.default_rank_id(),
            "consent": rec.get("consent") or legalconf.consent_record(),
            "status": "active" if is_admin else "pending",
            "token_version": 0,
            "created": now,
        }

        del db["verification"][key]

    message = (
        "Account created. You can log in now."
        if is_admin
        else "Account created. An admin has to approve it before you can log in."
    )

    return jsonify({
        "message": message,
        "pending": not is_admin
    }), 201


@bp.post("/login")
def login():
    data = json_body()

    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    rate_limit(
        f"login:{request.remote_addr}:{username.lower()}",
        10,
        300
    )

    user = find_user(storage.read("users"), username)

    ok = check_password(
        user["password_hash"] if user else DUMMY_HASH,
        password
    )

    if not user or not ok:
        if user:
            db.execute("INSERT INTO login_log (username, ts, ok) VALUES (?, ?, 0)", (user["username"], time.time()))
        raise ApiError("Wrong username or password.", 401)

    if user["status"] == "pending":
        raise ApiError(
            "Your account is waiting for admin approval.",
            403
        )

    if user["status"] != "active":
        raise ApiError("This account has been suspended.", 403)

    db.execute("INSERT INTO login_log (username, ts, ok) VALUES (?, ?, 1)", (user["username"], time.time()))
    return jsonify({
        "token": create_token(user),
        "user": me_view(user)
    })


@bp.post("/logout")
@login_required
def logout():
    # Raising the token version makes every old token invalid.
    with storage.transaction("users") as db:
        db["users"][g.user["username"].lower()]["token_version"] += 1

    return jsonify({"message": "Logged out."})
