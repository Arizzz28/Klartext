"""Ranks and permissions.

A RANK is a named bundle of permissions (Basic, Pro, ..., Admin, Owner). Every single feature is its OWN
permission key, and the server checks that key on every request (security.perm_required / security.need).
The frontend only hides buttons - it is never the protection.

Where things live:
- the list of all permission keys:  BUILTIN below (plus one key per game, see games.py)
- the ranks:                         storage data set "ranks" (the Owner can create, rename, edit, delete them)
- which rank a person has:           user["rank"]  (a rank id)
- a rented / gifted rank:            user["lease"] = {"rank": id, "until": timestamp}   (temporary, see economy.py)
- extra permissions for one person:  user["extra_perms"] = [keys]   (granted by the Owner after a request)

The Owner (the account named in OWNER_USERNAME) always has every permission and the top rank. That cannot be changed.
"""
import time

import config
import storage

# (key, label, group)
BUILTIN = [
    # --- chatting
    ("chat.write", "Write, edit and delete own messages", "Chat"),
    ("chat.react", "React to messages", "Chat"),
    ("chat.report", "Report messages", "Chat"),
    ("groups.create", "Create groups", "Chat"),
    ("uploads.use", "Upload files, pictures and videos", "Chat"),
    ("chat.moderate", "Delete other people's messages, clear chats for everybody", "Moderation"),
    ("chat.inspect", "Read private chats (with a reason, logged, visible to both people)", "Moderation"),
    ("mod.reports", "Handle reports", "Moderation"),
    ("mod.mute", "Mute people", "Moderation"),
    # --- administration
    ("admin.access", "See the admin area", "Admin"),
    ("admin.users", "Approve, suspend and create users, reset passwords", "Admin"),
    ("admin.delete_users", "Delete user accounts completely", "Admin"),
    ("admin.whitelist", "Edit the registration whitelist", "Admin"),
    ("admin.groups", "Read and manage all groups", "Admin"),
    ("admin.settings", "Change global settings (uploads, loading screen, ...)", "Admin"),
    ("admin.audit", "Read the audit log", "Admin"),
    ("admin.stats", "See statistics (which ones the Owner decides)", "Admin"),
    ("admin.manage_ranks", "Give ranks to people below their own rank", "Admin"),
    ("admin.offers", "See and answer Pro offers", "Admin"),
    ("admin.request", "Send permission requests to the Owner", "Admin"),
    ("admin.notes", "Look at other people's notes (logged)", "Admin"),
    ("admin.ads", "Manage ads and videos", "Admin"),
    ("admin.releases", "Publish What's New entries", "Admin"),
    ("coins.gift", "Gift coins", "Coins"),
    ("ranks.gift", "Gift temporary ranks", "Coins"),
    ("missions.manage", "Create and edit missions", "Coins"),
    ("owner.ranks", "Create, edit and delete ranks (Owner)", "Owner"),
    ("owner.requests", "Decide permission requests (Owner)", "Owner"),
    ("owner.config", "Owner settings: designs, shop, stats, AI, ads (Owner)", "Owner"),
    # --- tabs and features
    ("offers.create", "Send a Pro offer", "Features"),
    ("missions.use", "Missions", "Features"),
    ("shop.use", "Rent ranks with coins", "Features"),
    ("tabs.calendar", "Calendar", "Features"),
    ("tabs.tasks", "Tasks", "Features"),
    ("tabs.widgets", "Widgets", "Features"),
    ("tabs.search", "Global search", "Features"),
    ("tabs.music", "Music links and playlists", "Features"),
    ("tabs.voice", "Group voice channels (not built yet)", "Features"),
    ("tabs.visitors", "Profile visitors", "Features"),
    ("tabs.custom", "Own custom tabs", "Features"),
    ("tabs.notes", "Notes", "Features"),
    ("tabs.games", "Games tab", "Features"),
    ("tabs.forum", "Forum / suggestions", "Features"),
    ("tabs.ai", "AI tab", "Features"),
    ("tabs.bubble", "Floating tab bubble", "Layout"),
    ("tabs.editor", "Edit which tabs are shown and in what order", "Layout"),
    ("design.change", "Change the design mode", "Layout"),
    ("layout.move", "Move the sidebars", "Layout"),
    ("push.use", "Push notifications", "Features"),
]
# Features that are not finished are listed here, so the admin screen can say so honestly.
NOT_BUILT = {"tabs.voice"}

DESIGNS = ("classic", "glass", "paper", "midnight", "neon")
DESIGN_LABELS = {"classic": "Classic", "glass": "Glass", "paper": "Paper", "midnight": "Midnight", "neon": "Neon"}


def game_keys():
    import games
    return [(f"games.{g['id']}", f"Game: {g['name']}", "Games") for g in games.GAMES]


def registry():
    return BUILTIN + game_keys()


def all_keys():
    return {k for k, _, _ in registry()}


def _keys(*prefixes, exact=()):
    return [k for k in sorted(all_keys()) if k in exact or any(k.startswith(p) for p in prefixes)]


_BASIC = ["chat.write", "chat.react", "chat.report", "groups.create", "uploads.use", "offers.create",
          "missions.use", "shop.use", "tabs.notes", "tabs.tasks", "tabs.calendar", "tabs.forum", "tabs.visitors",
          "tabs.search", "tabs.widgets", "tabs.music", "tabs.games", "design.change", "push.use", "games.tictactoe"]
_PRO = _BASIC + ["tabs.custom", "tabs.bubble", "tabs.editor", "layout.move", "games.guess"]
_PRO_PLUS = _PRO + ["games.memory"]
_PRO_PP = _PRO_PLUS + ["tabs.ai"]
_PRO_PPP = _PRO_PP


def _default_ranks():
    everything = sorted(all_keys())
    staff_mod = _PRO_PPP + ["chat.moderate", "mod.reports", "mod.mute", "admin.access", "admin.request"]
    staff_admin = staff_mod + ["admin.users", "admin.whitelist", "admin.groups", "admin.settings", "admin.audit",
                               "admin.stats", "admin.manage_ranks", "admin.offers", "admin.request", "coins.gift",
                               "ranks.gift", "missions.manage", "admin.ads", "admin.releases", "chat.inspect"]
    return {
        "basic": {"name": "Basic", "level": 10, "color": "#6b7b78", "perms": _BASIC, "designs": ["classic"]},
        "pro": {"name": "Pro", "level": 20, "color": "#0e8a96", "perms": _PRO, "designs": ["classic", "paper"]},
        "pro_plus": {"name": "Pro+", "level": 30, "color": "#2a9d5c", "perms": _PRO_PLUS,
                     "designs": ["classic", "paper", "glass"]},
        "pro_pp": {"name": "Pro++", "level": 40, "color": "#c98a00", "perms": _PRO_PP,
                   "designs": ["classic", "paper", "glass", "midnight"]},
        "pro_ppp": {"name": "Pro+++", "level": 50, "color": "#d0572f", "perms": _PRO_PPP, "designs": list(DESIGNS)},
        "mod": {"name": "Mod", "level": 60, "color": "#7c4dcc", "perms": staff_mod, "designs": list(DESIGNS)},
        "admin": {"name": "Admin", "level": 70, "color": "#c93d57", "perms": staff_admin, "designs": list(DESIGNS)},
        "owner": {"name": "Owner", "level": 100, "color": "#e0a100", "perms": everything, "designs": list(DESIGNS),
                  "is_owner": True},
    }


def ensure_defaults():
    """Creates the standard ranks on the very first start. Never overwrites ranks the Owner edited."""
    with storage.transaction("ranks") as db:
        if not db["ranks"]:
            for rid, r in _default_ranks().items():
                db["ranks"][rid] = {"id": rid, **r}


def all_ranks():
    return storage.read("ranks")


def default_rank_id():
    import appsettings
    ranks = all_ranks()
    rid = appsettings.get().get("default_rank", "basic")
    if rid in ranks and not ranks[rid].get("is_owner"):
        return rid
    candidates = sorted((r for r in ranks.values() if not r.get("is_owner")), key=lambda r: r["level"])
    return candidates[0]["id"] if candidates else "basic"


def owner_rank_id(ranks=None):
    for r in (ranks or all_ranks()).values():
        if r.get("is_owner"):
            return r["id"]
    return "owner"


def is_owner(user):
    return bool(user) and user["username"].lower() == config.OWNER_USERNAME.lower()


def base_rank_of(user, ranks=None):
    ranks = ranks or all_ranks()
    if is_owner(user):
        return ranks.get(owner_rank_id(ranks)) or _default_ranks()["owner"] | {"id": "owner"}
    rank = ranks.get(user.get("rank", ""))
    if rank and rank.get("is_owner"):          # nobody but the real Owner may hold the Owner rank
        rank = None
    return rank or ranks.get(default_rank_id()) or {"id": "basic", "name": "Basic", "level": 10, "perms": [], "designs": ["classic"]}


def lease_of(user, ranks=None, now=None):
    lease = user.get("lease")
    if not lease or lease.get("until", 0) <= (now or time.time()):
        return None
    rank = (ranks or all_ranks()).get(lease.get("rank"))
    return rank if rank and not rank.get("is_owner") else None


def rank_of(user, ranks=None):
    """The rank that counts right now: the higher of the permanent rank and a running lease."""
    ranks = ranks or all_ranks()
    base = base_rank_of(user, ranks)
    leased = lease_of(user, ranks)
    return leased if leased and leased["level"] > base["level"] else base


def effective_perms(user, ranks=None):
    if is_owner(user):
        return all_keys()
    rank = rank_of(user, ranks)
    if rank.get("is_owner"):
        return all_keys()
    return (set(rank.get("perms", [])) | set(user.get("extra_perms", []))) & all_keys()


def has_perm(user, key, ranks=None):
    return is_owner(user) or key in effective_perms(user, ranks)


def level_of(user, ranks=None):
    return 1000 if is_owner(user) else rank_of(user, ranks)["level"]


def can_manage(actor, target, ranks=None):
    """May `actor` change `target` (rank, suspension, deletion, ...)? Only people BELOW the actor's level."""
    if actor["username"] == target["username"]:
        return False
    if is_owner(target):
        return False
    ranks = ranks or all_ranks()
    return level_of(actor, ranks) > level_of(target, ranks)


def allowed_designs(user, ranks=None):
    if is_owner(user):
        return list(DESIGNS)
    rank = rank_of(user, ranks)
    out = [d for d in DESIGNS if d in rank.get("designs", [])]
    return out or ["classic"]


def effective_design(user):
    allowed = allowed_designs(user)
    chosen = user.get("prefs", {}).get("design")
    if chosen in allowed and has_perm(user, "design.change"):
        return chosen
    return allowed[0]


def rank_public(rank):
    return {"id": rank["id"], "name": rank["name"], "level": rank["level"], "color": rank.get("color", "#888888")}


def migrate_users():
    """Version 3 start: everybody without a rank becomes Basic. Existing accounts and data stay as they are."""
    ranks = all_ranks()
    changed = 0
    with storage.transaction("users") as db:
        for user in db["users"].values():
            if is_owner(user):
                user["rank"] = owner_rank_id(ranks)
            elif user.get("rank") not in ranks or ranks[user["rank"]].get("is_owner"):
                user["rank"] = default_rank_id()
                changed += 1
    if changed:
        print(f"[MIGRATION] {changed} account(s) were given the standard rank", flush=True)
    return changed
