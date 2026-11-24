"""Global settings that admins can change in the app (stored in the "settings" data set)."""
import copy

import config
import storage
from security import ApiError

DEFAULTS = {
    "registration_mode": "whitelist",       # whitelist | open_approval | closed
    "announcement": "",                     # banner text for everybody, empty = no banner
    "uploads_enabled": True,
    "max_image_mb": 10,
    "max_video_mb": 100,
    "max_file_mb": 50,
    "user_quota_mb": 500,                   # how much one user may store in total
    "blocked_extensions": [".exe", ".bat", ".cmd", ".com", ".scr", ".msi", ".js", ".vbs", ".ps1",
                           ".jar", ".html", ".htm", ".svg", ".apk", ".dll", ".sh"],
    "messages_per_minute": 30,
    "loading": {
        "title": "Chatisfying",
        "image_asset": "",                  # id of an uploaded picture
        "music_asset": "",                  # id of an uploaded sound file
        "music_volume": 0.5,
        "allow_user_image": True,
        "allow_user_music": True,
        "allow_user_mute": True,
        "max_image_mb": 3,
        "max_music_mb": 8,
    },
    "background": {
        "default": "",                      # a preset key such as "ocean", empty = none
        "allow_custom": True,
    },
}

# What an admin may send, with limits. (type, min, max) or (type, allowed values).
_RULES = {
    "registration_mode": (str, ("whitelist", "open_approval", "closed")),
    "announcement": (str, 300),
    "uploads_enabled": (bool,),
    "max_image_mb": (int, 1, config.HARD_MAX_UPLOAD_MB),
    "max_video_mb": (int, 1, config.HARD_MAX_UPLOAD_MB),
    "max_file_mb": (int, 1, config.HARD_MAX_UPLOAD_MB),
    "user_quota_mb": (int, 10, 100000),
    "messages_per_minute": (int, 1, 600),
    "blocked_extensions": (list,),
}
_LOADING_RULES = {
    "title": (str, 40), "image_asset": (str, 64), "music_asset": (str, 64),
    "music_volume": (float, 0.0, 1.0), "allow_user_image": (bool,), "allow_user_music": (bool,),
    "allow_user_mute": (bool,), "max_image_mb": (int, 1, 20), "max_music_mb": (int, 1, 50),
}
_BG_RULES = {"default": (str, 40), "allow_custom": (bool,)}


def _merge(base, extra):
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(out.get(key), dict) and isinstance(value, dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def get():
    return _merge(DEFAULTS, storage.read("settings"))


def _check(key, value, rule):
    kind = rule[0]
    if kind is bool:
        if not isinstance(value, bool):
            raise ApiError(f"'{key}' must be true or false.")
    elif kind is int:
        if isinstance(value, bool) or not isinstance(value, int) or not rule[1] <= value <= rule[2]:
            raise ApiError(f"'{key}' must be a whole number between {rule[1]} and {rule[2]}.")
    elif kind is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not rule[1] <= value <= rule[2]:
            raise ApiError(f"'{key}' must be between {rule[1]} and {rule[2]}.")
        value = float(value)
    elif kind is str:
        if not isinstance(value, str):
            raise ApiError(f"'{key}' must be text.")
        if isinstance(rule[1], tuple):
            if value not in rule[1]:
                raise ApiError(f"'{key}' must be one of: {', '.join(rule[1])}.")
        elif len(value) > rule[1]:
            raise ApiError(f"'{key}' is too long (max {rule[1]} characters).")
    elif kind is list:
        if not isinstance(value, list) or len(value) > 50 or not all(isinstance(v, str) and 1 <= len(v) <= 12 for v in value):
            raise ApiError(f"'{key}' must be a short list of file endings.")
        value = sorted({v.lower() if v.startswith(".") else "." + v.lower() for v in value})
    return value


def validate(changes):
    """Returns only the known, valid parts of what an admin sent. Raises ApiError otherwise."""
    if not isinstance(changes, dict):
        raise ApiError("Invalid settings.")
    clean = {}
    for key, value in changes.items():
        if key == "loading" and isinstance(value, dict):
            clean["loading"] = {k: _check(f"loading.{k}", v, _LOADING_RULES[k]) for k, v in value.items() if k in _LOADING_RULES}
        elif key == "background" and isinstance(value, dict):
            clean["background"] = {k: _check(f"background.{k}", v, _BG_RULES[k]) for k, v in value.items() if k in _BG_RULES}
        elif key in _RULES:
            clean[key] = _check(key, value, _RULES[key])
    return clean


def save(clean):
    with storage.transaction("settings") as db:
        db["settings"] = _merge(db["settings"], clean)
    return get()


PRESET_BACKGROUNDS = ("ocean", "forest", "sunset", "night", "paper", "graphite")
