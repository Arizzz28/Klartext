"""Security helpers: errors, validation, password hashing, login tokens, permissions."""
import collections
import hashlib
import hmac
import re
import time
from functools import wraps

from flask import g, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

import config
import storage


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


# ---------- validation ----------
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
AVATAR_RE = re.compile(r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$")


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Invalid request body.")
    return data


def valid_username(value):
    value = str(value or "").strip()
    if not USERNAME_RE.match(value):
        raise ApiError("Username must be 3-20 characters: letters, numbers and underscore only.")
    return value


def valid_email(value):
    value = str(value or "").strip()
    if len(value) > 254 or not EMAIL_RE.match(value):
        raise ApiError("Please enter a valid email address.")
    return value


def valid_password(value):
    if not isinstance(value, str) or not (8 <= len(value) <= 128):
        raise ApiError("Password must be 8-128 characters long.")
    return value


def clean_text(value, field, max_len, required=True):
    value = str(value or "").strip()
    if required and not value:
        raise ApiError(f"{field} must not be empty.")
    if len(value) > max_len:
        raise ApiError(f"{field} is too long (max {max_len} characters).")
    return value


def clean_avatar(value):
    if not value:
        return ""
    if not isinstance(value, str) or len(value) > 150_000 or not AVATAR_RE.match(value):
        raise ApiError("Image must be a small PNG, JPEG or WebP.")
    return value


# ---------- passwords, codes, tokens ----------
DUMMY_HASH = generate_password_hash("dummy-password")  # keeps login timing similar for unknown users


def hash_password(password):
    return generate_password_hash(password)


def check_password(pw_hash, password):
    return check_password_hash(pw_hash, password)


def hash_code(code):
    return hmac.new(config.SECRET_KEY.encode(), code.encode(), hashlib.sha256).hexdigest()


_serializer = URLSafeTimedSerializer(config.SECRET_KEY, salt="chatisfying-auth")


def create_token(user):
    return _serializer.dumps({"u": user["username"], "v": user.get("token_version", 0)})


# ---------- users ----------
def find_user(users, username):
    return users.get(str(username or "").lower())


def public_user(u):
    return {"username": u["username"], "display_name": u["display_name"], "avatar": u.get("avatar", "")}


def me_view(u):
    return {**public_user(u), "email": u["email"], "is_admin": u.get("is_admin", False)}


# ---------- permissions ----------
def _user_from_request():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise ApiError("Please log in.", 401)
    try:
        payload = _serializer.loads(header[7:], max_age=config.TOKEN_TTL)
    except BadSignature:  # also covers expired tokens
        raise ApiError("Your session expired. Please log in again.", 401)
    user = find_user(storage.read("users"), payload.get("u"))
    if not user or user.get("token_version", 0) != payload.get("v"):
        raise ApiError("Your session expired. Please log in again.", 401)
    if user["status"] != "active":
        raise ApiError("This account is not active.", 403)
    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        g.user = _user_from_request()
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        g.user = _user_from_request()
        if not g.user.get("is_admin"):
            raise ApiError("Admins only.", 403)
        return fn(*args, **kwargs)
    return wrapper


# ---------- simple rate limit (in memory) ----------
_hits = collections.defaultdict(list)


def rate_limit(key, limit, window):
    now = time.time()
    hits = [t for t in _hits[key] if now - t < window]
    if len(hits) >= limit:
        _hits[key] = hits
        raise ApiError("Too many attempts. Please wait a moment.", 429)
    hits.append(now)
    _hits[key] = hits
