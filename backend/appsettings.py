"""Global settings that admins can change in the app (stored in the "settings" data set)."""
import copy
import re

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
    "start_page": "chats",                  # where people land after logging in (they can choose their own in Settings)
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
    # ---- Version 3: these are decided by the Owner (permission owner.config) ----
    "default_rank": "basic",                # rank of new accounts
    "offers": {"enabled": True, "rules": "Offer something you are willing to give or do (for example help, an idea, a favour). "
                                          "Nothing is paid. Admins read your offer and may reward you with a rank for some time."},
    "stats": {"enabled": ["users", "messages", "messages_24h", "groups", "files", "open_reports"]},
    "ai": {"enabled": False, "daily_limit": 20, "max_context_messages": 30},
    "ads": {"enabled": False, "every_n_visits": 5},
    "visitors": {"enabled": True, "keep_days": 30},
    "shop": {"enabled": True, "max_days": 7, "gift_max_days": 7, "items": [
        {"rank_id": "pro", "price": 200, "days": 1}, {"rank_id": "pro_plus", "price": 500, "days": 1}]},
    "coins": {"admin_daily_gift_cap": 500, "start_coins": 0, "user_daily_send_cap": 200},
    # Games (decided by ADMINS): are games on, are they unlocked one after the other, in which order, how many points each needs
    "pc": {"enabled": False},                   # the Owner's PC may take over the work while it is online (see pc.py)
    "windows": {"max_open": 4},               # desktop mode: how many windows a person may have open at once
    "games": {"enabled": True, "sequential": True, "order": [], "unlock": {}, "disabled": []},
    "plans": {"support_enabled": True,
              "support_text": "If you voluntarily give the Owner money, it will be used to make the servers better. "
                              "Nothing is paid inside this app and nobody has to pay for anything."},
    "missions": {"enabled": True, "mode": "random", "slots_hourly": 0, "slots_daily": 3, "slots_weekly": 2,
                 "w_common": 60, "w_uncommon": 25, "w_rare": 10, "w_super_rare": 4, "w_impossible": 1},
    "legal": {"operator_name": "", "operator_address": "", "operator_email": "", "operator_phone": "",
              "min_age": "", "note": ""},
}

STAT_KEYS = ("users", "pending", "ranks", "messages", "messages_24h", "groups", "files", "storage_mb", "open_reports",
             "offers_open", "coins_total", "notes", "tasks", "forum_posts", "logins_24h")
OWNER_KEYS = ("default_rank", "offers", "stats", "ai", "ads", "visitors", "shop", "coins", "missions", "plans", "legal", "pc")

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


_V3_RULES = {
    "offers": {"enabled": (bool,), "rules": (str, 1000)},
    "ai": {"enabled": (bool,), "daily_limit": (int, 1, 500), "max_context_messages": (int, 0, 100)},
    "ads": {"enabled": (bool,), "every_n_visits": (int, 1, 100)},
    "visitors": {"enabled": (bool,), "keep_days": (int, 1, 365)},
    "coins": {"admin_daily_gift_cap": (int, 0, 1_000_000), "start_coins": (int, 0, 1_000_000), "user_daily_send_cap": (int, 0, 1_000_000)},
    "plans": {"support_enabled": (bool,), "support_text": (str, 500)},
    "pc": {"enabled": (bool,)},
    "missions": {"enabled": (bool,), "mode": (str, ("all", "random")), "slots_hourly": (int, 0, 10), "slots_daily": (int, 0, 20),
                 "slots_weekly": (int, 0, 20), "w_common": (int, 0, 1000), "w_uncommon": (int, 0, 1000), "w_rare": (int, 0, 1000),
                 "w_super_rare": (int, 0, 1000), "w_impossible": (int, 0, 1000)},
    "legal": {"operator_name": (str, 120), "operator_address": (str, 300), "operator_email": (str, 120),
              "operator_phone": (str, 60), "min_age": (str, 60), "note": (str, 1500)},
}


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


TAB_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,29}$")


def valid_tab_id(value):
    """The name of a page/tab, e.g. "chats" or "calendar". Which names really exist is decided in the frontend
    (frontend/tabs.js), so a new page needs no change here. An unknown name just falls back to "chats"."""
    if not isinstance(value, str) or not TAB_ID_RE.match(value):
        raise ApiError("That is not a valid page name.")
    return value


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
        elif key in _V3_RULES and isinstance(value, dict):
            clean[key] = {k: _check(f"{key}.{k}", v, _V3_RULES[key][k]) for k, v in value.items() if k in _V3_RULES[key]}
        elif key == "windows" and isinstance(value, dict):
            clean["windows"] = {"max_open": _check("windows.max_open", value.get("max_open", 4), (int, 1, 12))}
        elif key == "games" and isinstance(value, dict):
            clean["games"] = _check_games(value)
        elif key == "start_page":
            clean[key] = valid_tab_id(value)
        elif key == "default_rank":
            if not isinstance(value, str) or len(value) > 40:
                raise ApiError("Invalid rank.")
            clean[key] = value
        elif key == "stats" and isinstance(value, dict):
            enabled = value.get("enabled", [])
            if not isinstance(enabled, list) or any(e not in STAT_KEYS for e in enabled):
                raise ApiError("Unknown statistic.")
            clean["stats"] = {"enabled": [e for e in STAT_KEYS if e in enabled]}
        elif key == "shop" and isinstance(value, dict):
            clean["shop"] = _check_shop(value)
        elif key in _RULES:
            clean[key] = _check(key, value, _RULES[key])
    return clean


def _check_games(value):
    import games
    out = {}
    for k in ("enabled", "sequential"):
        if k in value:
            out[k] = _check(f"games.{k}", value[k], (bool,))
    if "order" in value:
        order = value["order"]
        if not isinstance(order, list) or any(i not in games.BY_ID for i in order) or len(set(order)) != len(order):
            raise ApiError("The game order contains an unknown or repeated game.")
        out["order"] = order
    if "disabled" in value:
        dis = value["disabled"]
        if not isinstance(dis, list) or any(i not in games.BY_ID for i in dis):
            raise ApiError("Unknown game in the list of switched-off games.")
        out["disabled"] = sorted(set(dis))
    if "unlock" in value:
        un = value["unlock"]
        if not isinstance(un, dict) or any(k not in games.BY_ID for k in un):
            raise ApiError("Unknown game in the unlock points.")
        out["unlock"] = {k: _check(f"unlock.{k}", v, (int, 0, 100000)) for k, v in un.items()}
    return out


def _check_shop(value):
    out = {}
    if "enabled" in value:
        out["enabled"] = _check("shop.enabled", value["enabled"], (bool,))
    if "max_days" in value:
        out["max_days"] = _check("shop.max_days", value["max_days"], (int, 1, 30))
    if "gift_max_days" in value:
        out["gift_max_days"] = _check("shop.gift_max_days", value["gift_max_days"], (int, 1, 365))
    if "items" in value:
        import perms
        ranks = perms.all_ranks()
        items = value["items"]
        if not isinstance(items, list) or len(items) > 20:
            raise ApiError("The shop can have up to 20 items.")
        clean_items, seen = [], set()
        for item in items:
            if not isinstance(item, dict):
                raise ApiError("Invalid shop item.")
            rid = item.get("rank_id")
            rank = ranks.get(rid)
            if not rank or rank.get("is_owner") or rank["level"] >= 60:
                raise ApiError("Only ranks below the Mod level can be rented.")
            if rid in seen:
                raise ApiError("Every rank can be in the shop only once.")
            seen.add(rid)
            price = _check("price", item.get("price"), (int, 1, 1_000_000))
            days = _check("days", item.get("days", 1), (int, 1, 30))
            clean_items.append({"rank_id": rid, "price": price, "days": days})
        out["items"] = clean_items
    return out


def save(clean):
    with storage.transaction("settings") as db:
        db["settings"] = _merge(db["settings"], clean)
    return get()


PRESET_BACKGROUNDS = ("ocean", "forest", "sunset", "night", "paper", "graphite")
