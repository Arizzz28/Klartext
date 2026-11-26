"""The Plans tab: which ranks exist, what each one offers, what it costs in coins, and the place to send an offer.
Nothing here takes real money. The ranks shown are the ones the Owner marked as "offered"."""
from flask import Blueprint, g, jsonify

import appsettings
import perms
from security import perm_required

bp = Blueprint("plans", __name__, url_prefix="/api/plans")

SHOWN_GROUPS = ("Chat", "Features", "Layout", "Games")


@bp.get("")
@perm_required("tabs.plans")
def plans():
    ranks = perms.all_ranks()
    cfg = appsettings.get()
    shop = {i["rank_id"]: i for i in cfg["shop"]["items"]} if cfg["shop"]["enabled"] else {}
    labels = {k: (label, group) for k, label, group in perms.registry()}
    mine = perms.rank_of(g.user, ranks)
    out, previous = [], set()
    for r in sorted(ranks.values(), key=lambda x: x["level"]):
        if r.get("is_owner") or r["level"] >= 60 or not r.get("offered", True):
            continue
        feats = [labels[k][0] for k in sorted(r.get("perms", [])) if k in labels and labels[k][1] in SHOWN_GROUPS]
        new = [labels[k][0] for k in sorted(set(r.get("perms", [])) - previous) if k in labels and labels[k][1] in SHOWN_GROUPS]
        previous |= set(r.get("perms", []))
        item = shop.get(r["id"])
        out.append({"id": r["id"], "name": r["name"], "color": r.get("color", "#888888"), "level": r["level"],
                    "features": feats, "new_features": new, "designs": len(r.get("designs", [])),
                    "perks_text": r.get("perks_text", ""), "price": item["price"] if item else None, "days": item["days"] if item else None,
                    "is_mine": r["id"] == mine["id"]})
    plans_cfg = cfg["plans"]
    return jsonify({"ranks": out, "my_rank": perms.rank_public(mine), "offers_enabled": cfg["offers"]["enabled"],
                    "offers_rules": cfg["offers"]["rules"], "can_offer": perms.has_perm(g.user, "offers.create"),
                    "support": plans_cfg["support_text"] if plans_cfg["support_enabled"] else ""})
