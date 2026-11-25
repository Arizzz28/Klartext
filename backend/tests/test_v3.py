"""Permission and feature tests for Chatisfying 3.0.  Run:  cd backend && python -m pytest tests -q"""
import time

import pytest

import config
import notify
import perms
import storage
import legalconf


def J(res):
    return res.get_json()


# ------------------------------------------------------------------ legal consent
def test_register_needs_checkbox_on_server(client):
    base = {"username": "newbie", "email": "newbie@example.com"}
    r = client.post("/api/auth/register/start", json=base)
    assert r.status_code == 400 and "accept" in J(r)["error"].lower()
    r = client.post("/api/auth/register/start", json={**base, "accept_terms": True, "terms_version": "old", "privacy_version": "old"})
    assert r.status_code == 409
    r = client.post("/api/auth/register/start", json={**base, "accept_terms": "yes", "terms_version": legalconf.TERMS_VERSION,
                                                      "privacy_version": legalconf.PRIVACY_VERSION})
    assert r.status_code == 400                       # only the real boolean true counts


def test_registration_stores_consent_version_and_time(client):
    with storage.transaction("users") as db:            # other test files may already have created the Owner account
        db["users"].pop("boss", None)
    ok = {"username": "Boss", "email": "boss@example.com", "accept_terms": True,
          "terms_version": legalconf.TERMS_VERSION, "privacy_version": legalconf.PRIVACY_VERSION}
    assert client.post("/api/auth/register/start", json=ok).status_code == 200
    rec = storage.read("verification")["boss"]
    assert rec["consent"]["terms"] == legalconf.TERMS_VERSION and rec["consent"]["at"] > 0
    # complete the registration by faking the verified state (the code goes to e-mail)
    with storage.transaction("verification") as db:
        db["verification"]["boss"]["verified"] = True
    r = client.post("/api/auth/register/complete", json={"username": "Boss", "password": "password123"})
    assert r.status_code == 201
    u = storage.read("users")["boss"]
    assert u["consent"]["terms"] == legalconf.TERMS_VERSION and u["rank"] == "owner" and u["status"] == "active"
    r = client.post("/api/auth/login", json={"username": "Boss", "password": "password123"})
    assert r.status_code == 200 and J(r)["user"]["is_owner"] and J(r)["user"]["consent_ok"]


def test_consent_gate_blocks_everything_until_accepted(client, make_user):
    h = make_user("oldtimer", consent=False)
    r = client.get("/api/users", headers=h)
    assert r.status_code == 403 and J(r)["code"] == "consent_required"
    assert client.get("/api/me", headers=h).status_code == 200            # needed to show the dialog
    assert client.get("/api/legal").status_code == 200
    bad = client.post("/api/me/consent", headers=h, json={"terms": True, "privacy": False,
                                                          "terms_version": legalconf.TERMS_VERSION, "privacy_version": legalconf.PRIVACY_VERSION})
    assert bad.status_code == 400
    stale = client.post("/api/me/consent", headers=h, json={"terms": True, "privacy": True, "terms_version": "x", "privacy_version": "y"})
    assert stale.status_code == 409
    ok = client.post("/api/me/consent", headers=h, json={"terms": True, "privacy": True,
                                                         "terms_version": legalconf.TERMS_VERSION, "privacy_version": legalconf.PRIVACY_VERSION})
    assert ok.status_code == 200 and J(ok)["consent_ok"]
    assert client.get("/api/users", headers=h).status_code == 200


def test_new_version_of_terms_requires_new_consent(client, make_user, monkeypatch):
    h = make_user("reconsent")
    assert client.get("/api/users", headers=h).status_code == 200
    monkeypatch.setattr(legalconf, "TERMS_VERSION", "2099-01-01")
    assert client.get("/api/users", headers=h).status_code == 403


# ------------------------------------------------------------------ ranks and permissions
def test_default_ranks_exist_and_owner_has_everything(client, owner):
    me = J(client.get("/api/me", headers=owner))
    assert me["rank"]["id"] == "owner" and set(me["perms"]) == perms.all_keys()
    names = [r["name"] for r in J(client.get("/api/admin/ranks", headers=owner))["ranks"]]
    assert names == ["Basic", "Pro", "Pro+", "Pro++", "Pro+++", "Mod", "Admin", "Owner"]


def test_basic_cannot_use_admin_or_pro_features(client, make_user):
    h = make_user("plain")
    for method, path in [("get", "/api/admin/users"), ("get", "/api/admin/settings"), ("get", "/api/admin/audit"),
                         ("get", "/api/admin/stats"), ("get", "/api/mod/reports"), ("get", "/api/ai/status"),
                         ("get", "/api/custom-tabs"), ("get", "/api/admin/offers"), ("post", "/api/ranks/gift"),
                         ("post", "/api/coins/gift"), ("get", "/api/missions/manage")]:
        r = getattr(client, method)(path, headers=h)
        assert r.status_code == 403, path
        assert J(r).get("code") == "permission_denied", path


def test_basic_can_chat_and_basic_features(client, make_user):
    a, b = make_user("ann"), make_user("ben")
    r = client.post("/api/chats/dm/ben/messages", headers=a, json={"text": "hello"})
    assert r.status_code == 201
    assert client.get("/api/notes", headers=a).status_code == 200
    assert client.get("/api/missions", headers=a).status_code == 200


def test_permission_is_checked_per_feature(client, make_user, owner):
    """Take one permission away from a rank: exactly that feature stops working."""
    rid = J(client.post("/api/admin/ranks", headers=owner, json={
        "name": "Tester", "level": 15, "color": "#112233", "perms": ["chat.write", "chat.react"], "designs": ["classic"]}))["id"]
    h = make_user("tess", rank=rid)
    make_user("target1")
    assert client.post("/api/chats/dm/target1/messages", headers=h, json={"text": "x"}).status_code == 201
    assert client.post("/api/groups", headers=h, json={"name": "G", "join_mode": "open"}).status_code == 403   # groups.create missing
    assert client.get("/api/notes", headers=h).status_code == 403
    # add the permission to the rank -> works immediately
    rank = next(r for r in J(client.get("/api/admin/ranks", headers=owner))["ranks"] if r["id"] == rid)
    rank["perms"] = rank["perms"] + ["groups.create"]
    assert client.put(f"/api/admin/ranks/{rid}", headers=owner, json=rank).status_code == 200
    assert client.post("/api/groups", headers=h, json={"name": "G", "join_mode": "open"}).status_code == 201


def test_only_owner_manages_ranks(client, make_user, owner):
    adm = make_user("admy", rank="admin")
    body = {"name": "Hack", "level": 20, "color": "#000000", "perms": ["chat.write"], "designs": ["classic"]}
    assert client.post("/api/admin/ranks", headers=adm, json=body).status_code == 403
    assert client.delete("/api/admin/ranks/basic", headers=adm).status_code == 403
    assert client.post("/api/admin/ranks", headers=owner, json=body).status_code == 201
    assert client.post("/api/admin/ranks", headers=owner, json=body).status_code == 409     # name taken
    assert client.post("/api/admin/ranks", headers=owner, json={**body, "name": "X", "perms": ["nonsense"]}).status_code == 400


def test_owner_rank_cannot_be_deleted_or_assigned(client, make_user, owner):
    assert client.delete("/api/admin/ranks/owner", headers=owner).status_code == 403
    adm = make_user("admz", rank="admin")
    make_user("victim1")
    r = client.patch("/api/admin/users/victim1", headers=adm, json={"rank": "owner"})
    assert r.status_code == 400


def test_delete_rank_moves_accounts_to_default(client, make_user, owner):
    rid = J(client.post("/api/admin/ranks", headers=owner, json={"name": "Temp", "level": 12, "color": "#abcdef",
                                                                 "perms": ["chat.write"], "designs": ["classic"]}))["id"]
    make_user("tempuser", rank=rid)
    r = client.delete(f"/api/admin/ranks/{rid}", headers=owner)
    assert r.status_code == 200
    assert storage.read("users")["tempuser"]["rank"] == "basic"


def test_admin_hierarchy(client, make_user, owner):
    adm, other_adm, mod = make_user("adm1", rank="admin"), make_user("adm2", rank="admin"), make_user("mod1", rank="mod")
    make_user("basicguy")
    # admin can promote a basic user to pro, but not to admin (own level) and cannot touch another admin or the owner
    assert client.patch("/api/admin/users/basicguy", headers=adm, json={"rank": "pro"}).status_code == 200
    assert client.patch("/api/admin/users/basicguy", headers=adm, json={"rank": "admin"}).status_code == 403
    assert client.patch("/api/admin/users/adm2", headers=adm, json={"rank": "basic"}).status_code == 403
    assert client.post("/api/admin/users/Boss/suspend", headers=adm).status_code == 403
    assert client.post("/api/admin/users/adm2/suspend", headers=adm).status_code == 403
    assert client.post("/api/admin/users/adm1/suspend", headers=adm).status_code == 400            # not yourself
    # a mod has no admin rights at all
    assert client.get("/api/admin/users", headers=mod).status_code == 403
    # the owner can do everything except touch himself
    assert client.patch("/api/admin/users/adm2", headers=owner, json={"rank": "basic"}).status_code == 200
    assert client.post("/api/admin/users/Boss/suspend", headers=owner).status_code == 400
    assert client.post("/api/admin/users/Boss/delete", headers=adm, json={"confirm": "Boss"}).status_code == 403


def test_owner_cannot_be_demoted_even_if_data_says_so(client, owner):
    with storage.transaction("users") as db:
        db["users"]["boss"]["rank"] = "basic"
    assert J(client.get("/api/me", headers=owner))["rank"]["id"] == "owner"
    assert client.get("/api/admin/users", headers=owner).status_code == 200


def test_permission_request_flow(client, make_user, owner):
    adm = make_user("reqadmin", rank="admin")
    assert client.post("/api/admin/requests", headers=adm, json={"perm": "owner.ranks", "text": "I need to edit ranks"}).status_code == 201
    assert client.post("/api/admin/requests", headers=adm, json={"perm": "owner.ranks", "text": "again"}).status_code == 409
    assert client.post("/api/admin/requests", headers=adm, json={"perm": "bogus", "text": "x"}).status_code == 400
    # the owner got a notification, the admin cannot decide
    notes = J(client.get("/api/notifications", headers=owner))
    assert any(n["kind"] == "request" for n in notes["items"])
    rid = J(client.get("/api/admin/requests", headers=owner))[0]["id"]
    assert client.post(f"/api/admin/requests/{rid}/decide", headers=adm, json={"approve": True}).status_code == 403
    assert client.post(f"/api/admin/requests/{rid}/decide", headers=owner, json={"approve": True, "answer": "ok"}).status_code == 200
    assert "owner.ranks" in J(client.get("/api/me", headers=adm))["perms"]


def test_basic_cannot_send_requests(client, make_user):
    assert client.post("/api/admin/requests", headers=make_user("nope1"), json={"perm": "tabs.ai", "text": "pls"}).status_code == 403


# ------------------------------------------------------------------ designs and layout prefs
def test_designs_follow_rank(client, make_user, owner):
    basic = make_user("dbasic")
    assert J(client.get("/api/me", headers=basic))["allowed_designs"] == ["classic"]
    assert client.put("/api/me/prefs", headers=basic, json={"design": "neon"}).status_code == 403
    assert client.put("/api/me/prefs", headers=basic, json={"design": "classic"}).status_code == 200
    p3 = make_user("dpppp", rank="pro_ppp")
    assert client.put("/api/me/prefs", headers=p3, json={"design": "neon"}).status_code == 200
    assert J(client.get("/api/me", headers=p3))["design"] == "neon"
    # the owner takes neon away from that rank -> the effective design falls back
    ranks = J(client.get("/api/admin/ranks", headers=owner))["ranks"]
    r = next(x for x in ranks if x["id"] == "pro_ppp")
    r["designs"] = ["classic", "paper"]
    assert client.put("/api/admin/ranks/pro_ppp", headers=owner, json=r).status_code == 200
    assert J(client.get("/api/me", headers=p3))["design"] == "classic"
    r["designs"] = list(perms.DESIGNS)
    client.put("/api/admin/ranks/pro_ppp", headers=owner, json=r)


def test_bubble_tabs_layout_need_permissions(client, make_user):
    basic, pro = make_user("lbasic"), make_user("lpro", rank="pro")
    assert client.put("/api/me/prefs", headers=basic, json={"bubble": {"on": True, "pos": {"x": 0.5, "y": 0.5}}}).status_code == 403
    assert client.put("/api/me/prefs", headers=basic, json={"tabs": ["chats"]}).status_code == 403
    assert client.put("/api/me/prefs", headers=basic, json={"layout": {"side": "right", "list_width": 300}}).status_code == 403
    assert client.put("/api/me/prefs", headers=pro, json={"bubble": {"on": True, "pos": {"x": 0.5, "y": 0.5}}}).status_code == 200
    assert client.put("/api/me/prefs", headers=pro, json={"tabs": ["chats", "tasks"]}).status_code == 200
    assert client.put("/api/me/prefs", headers=pro, json={"tabs": ["chats", "Evil Tab!"]}).status_code == 400
    assert client.put("/api/me/prefs", headers=pro, json={"layout": {"side": "right", "list_width": 5000}}).status_code == 400
    assert client.put("/api/me/prefs", headers=pro, json={"layout": {"side": "right", "list_width": 300}}).status_code == 200


# ------------------------------------------------------------------ unread counters
def test_unread_counts_work_across_devices(client, make_user):
    a, b = make_user("ua"), make_user("ub")
    for i in range(3):
        client.post("/api/chats/dm/ub/messages", headers=a, json={"text": f"m{i}"})
    assert J(client.get("/api/unread", headers=b))["dm"] == {"ua": 3}
    assert J(client.get("/api/unread", headers=a))["chats"] == 0                  # own messages are never unread
    # "device 2" is just the same account: the state lives on the server
    assert client.post("/api/chats/dm/ua/read", headers=b).status_code == 200
    assert J(client.get("/api/unread", headers=b))["chats"] == 0
    client.post("/api/chats/dm/ub/messages", headers=a, json={"text": "again"})
    assert J(client.get("/api/unread", headers=b))["dm"] == {"ua": 1}


def test_unread_group_and_cleared_chat(client, make_user):
    a, b = make_user("ga"), make_user("gb")
    gid = J(client.post("/api/groups", headers=a, json={"name": "Unread", "join_mode": "open"}))["id"]
    client.post(f"/api/groups/{gid}/join", headers=b)
    client.post(f"/api/chats/group/{gid}/messages", headers=a, json={"text": "hi"})
    assert J(client.get("/api/unread", headers=b))["group"] == {gid: 1}
    client.post(f"/api/chats/group/{gid}/clear", headers=b, json={"scope": "me"})
    assert J(client.get("/api/unread", headers=b))["groups"] == 0


# ------------------------------------------------------------------ push
def test_push_subscribe_and_send(client, make_user, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "_webpush_send", lambda sub, payload: sent.append((sub["endpoint"], payload)))
    a, b = make_user("pa"), make_user("pb")
    sub = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": "k" * 20, "auth": "a" * 10}}
    assert client.post("/api/push/subscribe", headers=b, json=sub).status_code == 201
    assert client.post("/api/push/subscribe", headers=b, json={**sub, "endpoint": "http://insecure"}).status_code == 400
    monkeypatch.setattr(notify, "push_to", lambda names, title, body, url="", sync=False: notify._deliver(list(names), {"title": title, "body": body, "url": url}))
    client.post("/api/chats/dm/pb/messages", headers=a, json={"text": "secret text"})
    assert len(sent) == 1 and sent[0][0] == sub["endpoint"]
    assert "secret text" not in sent[0][1]                         # no message text unless the receiver switched the preview on
    client.put("/api/me/prefs", headers=b, json={"push_preview": True})
    client.post("/api/chats/dm/pb/messages", headers=a, json={"text": "now visible"})
    assert "now visible" in sent[-1][1]
    # the sender is never notified about their own message
    client.post("/api/push/subscribe", headers=a, json={**sub, "endpoint": "https://fcm.googleapis.com/fcm/send/mine"})
    n = len(sent)
    client.post("/api/chats/dm/pb/messages", headers=a, json={"text": "third"})
    assert all(s[0] != "https://fcm.googleapis.com/fcm/send/mine" for s in sent[n:])


def test_push_removes_dead_subscriptions(client, make_user, monkeypatch):
    class Gone(Exception):
        response = type("R", (), {"status_code": 410})()
    def boom(sub, payload):
        raise Gone()
    monkeypatch.setattr(notify, "_webpush_send", boom)
    h = make_user("pdead")
    client.post("/api/push/subscribe", headers=h, json={"endpoint": "https://fcm.googleapis.com/fcm/send/dead", "keys": {"p256dh": "k" * 20, "auth": "a" * 10}})
    notify._deliver(["pdead"], {"title": "x"})
    import db
    assert db.query("SELECT 1 AS x FROM push_subscriptions WHERE endpoint = ?", ("https://fcm.googleapis.com/fcm/send/dead",)) == []


# ------------------------------------------------------------------ missions, coins, shop
def test_mission_progress_and_single_payout(client, make_user, owner):
    h, other = make_user("miss1"), make_user("miss2")
    mid = next(m["id"] for m in J(client.get("/api/missions", headers=h))["missions"] if m["kind"] == "messages" and m["period"] == "daily")
    assert client.post(f"/api/missions/{mid}/claim", headers=h).status_code == 400            # not finished
    for i in range(10):
        client.post("/api/chats/dm/miss2/messages", headers=h, json={"text": f"x{i}"})
    m = next(m for m in J(client.get("/api/missions", headers=h))["missions"] if m["id"] == mid)
    assert m["progress"] == 10 and m["claimable"]
    r = client.post(f"/api/missions/{mid}/claim", headers=h)
    assert r.status_code == 200 and J(r)["coins"] == J(r)["reward"]
    assert client.post(f"/api/missions/{mid}/claim", headers=h).status_code == 409            # no second payout
    assert J(client.get("/api/coins", headers=h))["coins"] == J(r)["reward"]


def test_other_peoples_messages_do_not_count(client, make_user):
    h = make_user("miss3")
    mid = next(m["id"] for m in J(client.get("/api/missions", headers=h))["missions"] if m["kind"] == "messages" and m["period"] == "daily")
    other = make_user("miss4")
    for i in range(12):
        client.post("/api/chats/dm/miss3/messages", headers=other, json={"text": f"x{i}"})
    assert client.post(f"/api/missions/{mid}/claim", headers=h).status_code == 400


def test_mission_management_needs_permission(client, make_user, owner):
    body = {"title": "Send 3 files", "kind": "uploads", "target": 3, "period": "weekly", "reward": 50}
    assert client.post("/api/missions", headers=make_user("mm1"), json=body).status_code == 403
    assert client.post("/api/missions", headers=make_user("mm2", rank="admin"), json=body).status_code == 201
    assert client.post("/api/missions", headers=owner, json={**body, "kind": "bogus"}).status_code == 400
    assert client.post("/api/missions", headers=owner, json={**body, "reward": -5}).status_code == 400


def _give_coins(client, owner, name, n):
    return client.post("/api/coins/gift", headers=owner, json={"username": name, "amount": n})


def test_shop_rent_pay_and_cap(client, make_user, owner):
    h = make_user("shopper")
    assert client.post("/api/shop/rent", headers=h, json={"rank_id": "pro"}).status_code == 402          # no coins
    assert _give_coins(client, owner, "shopper", 5000).status_code == 200
    r = client.post("/api/shop/rent", headers=h, json={"rank_id": "pro"})
    assert r.status_code == 200
    me = J(client.get("/api/me", headers=h))
    assert me["rank"]["id"] == "pro" and me["lease"]["rank"]["id"] == "pro" and "tabs.custom" in me["perms"]
    assert me["design"] and "paper" in me["allowed_designs"]
    for _ in range(10):                                                                                 # keep renting: capped at max_days (7)
        client.post("/api/shop/rent", headers=h, json={"rank_id": "pro"})
    me = J(client.get("/api/me", headers=h))
    assert me["lease"]["until"] <= time.time() + 7 * 86400 + 5
    assert client.post("/api/shop/rent", headers=h, json={"rank_id": "pro"}).status_code == 409        # already at the maximum
    spent = J(client.get("/api/coins", headers=h))["coins"]
    assert spent >= 5000 - 7 * 200                                                                      # never charged for days it didn't give


def test_shop_only_listed_low_ranks(client, make_user, owner):
    h = make_user("shopper2")
    _give_coins(client, owner, "shopper2", 100000)
    assert client.post("/api/shop/rent", headers=h, json={"rank_id": "admin"}).status_code == 404
    assert client.post("/api/shop/rent", headers=h, json={"rank_id": "owner"}).status_code == 404
    bad = client.put("/api/admin/settings", headers=owner, json={"shop": {"items": [{"rank_id": "admin", "price": 1, "days": 1}]}})
    assert bad.status_code == 400                                                                         # owner can't list staff ranks either
    ok = client.put("/api/admin/settings", headers=owner, json={"shop": {"items": [{"rank_id": "pro_pp", "price": 77, "days": 2}], "max_days": 3}})
    assert ok.status_code == 200
    assert client.post("/api/shop/rent", headers=h, json={"rank_id": "pro_pp"}).status_code == 200
    until = J(client.get("/api/me", headers=h))["lease"]["until"]
    assert until <= time.time() + 2 * 86400 + 5
    client.put("/api/admin/settings", headers=owner, json={"shop": {"items": [{"rank_id": "pro", "price": 200, "days": 1},
                                                                              {"rank_id": "pro_plus", "price": 500, "days": 1}], "max_days": 7}})


def test_lease_expires(client, make_user):
    h = make_user("expiring", lease={"rank": "pro", "until": time.time() - 10})
    me = J(client.get("/api/me", headers=h))
    assert me["rank"]["id"] == "basic" and me["lease"] is None and "tabs.custom" not in me["perms"]


def test_lease_never_lowers_a_rank(client, make_user):
    h = make_user("highrank", rank="pro_pp", lease={"rank": "pro", "until": time.time() + 9999})
    assert J(client.get("/api/me", headers=h))["rank"]["id"] == "pro_pp"


def test_gifts_and_daily_cap(client, make_user, owner):
    adm = make_user("giftadmin", rank="admin")
    make_user("giftee")
    assert client.post("/api/coins/gift", headers=adm, json={"username": "giftee", "amount": 300}).status_code == 200
    assert client.post("/api/coins/gift", headers=adm, json={"username": "giftee", "amount": 300}).status_code == 403    # cap 500/day
    assert client.post("/api/coins/gift", headers=owner, json={"username": "giftee", "amount": 99999}).status_code == 200   # owner: no cap
    assert client.post("/api/coins/gift", headers=adm, json={"username": "giftee", "amount": -5}).status_code == 400
    # rank gifts: admin only below own level, limited days
    assert client.post("/api/ranks/gift", headers=adm, json={"username": "giftee", "rank_id": "admin", "days": 1}).status_code == 403
    assert client.post("/api/ranks/gift", headers=adm, json={"username": "giftee", "rank_id": "pro", "days": 30}).status_code == 403
    assert client.post("/api/ranks/gift", headers=adm, json={"username": "giftee", "rank_id": "pro", "days": 3}).status_code == 200
    assert client.post("/api/ranks/gift", headers=owner, json={"username": "giftee", "rank_id": "pro_ppp", "days": 30}).status_code == 200
    kinds = [n["kind"] for n in J(client.get("/api/notifications", headers=make_user("giftee")))["items"]]
    assert "gift" in kinds


def test_negative_balance_impossible(client, make_user):
    import db
    import economy
    make_user("poor")
    with pytest.raises(Exception):
        with db.transaction() as tx:
            economy.add_coins(tx, "poor", -1, "test")
    assert economy.balance("poor") == 0


# ------------------------------------------------------------------ offers
def test_pro_offers(client, make_user, owner):
    h, adm = make_user("offerer"), make_user("offadmin", rank="admin")
    assert client.post("/api/offers", headers=h, json={"text": "short"}).status_code == 400
    assert client.post("/api/offers", headers=h, json={"text": "I can help translate the app into English"}).status_code == 201
    assert client.post("/api/offers", headers=h, json={"text": "A second one while the first is open"}).status_code == 409
    assert any(n["kind"] == "offer" for n in J(client.get("/api/notifications", headers=adm))["items"])
    assert client.get("/api/admin/offers", headers=h).status_code == 403
    oid = J(client.get("/api/admin/offers", headers=adm))[0]["id"]
    r = client.post(f"/api/admin/offers/{oid}/decide", headers=adm, json={"accept": True, "answer": "thanks!", "rank_id": "pro", "days": 2})
    assert r.status_code == 200
    assert J(client.get("/api/me", headers=h))["rank"]["id"] == "pro"
    assert any(n["kind"] == "offer" for n in J(client.get("/api/notifications", headers=h))["items"])


def test_offer_reward_limits_for_admin(client, make_user):
    h, adm = make_user("offerer2"), make_user("offadmin2", rank="admin")
    client.post("/api/offers", headers=h, json={"text": "I can design a logo for the app please"})
    oid = next(o["id"] for o in J(client.get("/api/admin/offers", headers=adm)) if o["username"] == "offerer2")
    assert client.post(f"/api/admin/offers/{oid}/decide", headers=adm, json={"accept": True, "rank_id": "admin", "days": 1}).status_code == 403
    assert client.post(f"/api/admin/offers/{oid}/decide", headers=adm, json={"accept": True, "rank_id": "pro", "days": 99}).status_code == 403


# ------------------------------------------------------------------ notes, planner, search
def test_notes_private_and_admin_access_is_logged(client, make_user, owner):
    a, b = make_user("noter"), make_user("snoop")
    adm = make_user("noteadmin", rank="admin")
    assert client.get("/api/notes/of/noter", headers=adm).status_code == 403          # Admin does NOT have admin.notes by default
    adm = make_user("noteadmin", rank="admin", extra_perms=["admin.notes"])          # ... the Owner has to grant it
    nid = J(client.post("/api/notes", headers=a, json={"title": "Diary", "body": "dear diary"}))["id"]
    assert client.put(f"/api/notes/{nid}", headers=b, json={"title": "x", "body": "y"}).status_code == 404
    assert client.delete(f"/api/notes/{nid}", headers=b).status_code == 404
    assert client.get("/api/notes/of/noter", headers=b).status_code == 403
    r = client.get("/api/notes/of/noter", headers=adm)
    assert r.status_code == 200 and J(r)["notes"][0]["body"] == "dear diary"
    assert any("looked at your notes" in n["text"] for n in J(client.get("/api/notifications", headers=a))["items"])
    log = J(client.get("/api/admin/audit", headers=owner))
    assert any(e["action"] == "view_notes" and e["target"] == "noter" for e in log)
    # an admin cannot read another admin's or the owner's notes
    other = make_user("noteadmin2", rank="admin")
    client.post("/api/notes", headers=other, json={"body": "mine"})
    assert client.get("/api/notes/of/noteadmin2", headers=adm).status_code == 403
    assert client.get("/api/notes/of/Boss", headers=adm).status_code == 403


def test_calendar_and_tasks_sharing(client, make_user):
    a, b, c = make_user("pla"), make_user("plb"), make_user("plc")
    now = time.time() + 3600
    eid = J(client.post("/api/events", headers=a, json={"title": "Party", "start": now, "share_with": ["plb"]}))["id"]
    assert [e["title"] for e in J(client.get("/api/events", headers=b))] == ["Party"]
    assert J(client.get("/api/events", headers=c)) == []
    assert client.put(f"/api/events/{eid}", headers=b, json={"title": "x", "start": now}).status_code == 404       # shared people can't edit
    assert client.delete(f"/api/events/{eid}", headers=b).status_code == 404
    assert client.post("/api/events", headers=a, json={"title": "Bad", "start": now, "end": now - 5}).status_code == 400
    assert client.post("/api/events", headers=a, json={"title": "Ghost", "start": now, "share_with": ["nobody_here"]}).status_code == 404
    tid = J(client.post("/api/tasks", headers=a, json={"title": "Buy cake", "share_with": ["plb"]}))["id"]
    assert client.put(f"/api/tasks/{tid}", headers=b, json={"done": True}).status_code == 200                   # shared: may tick off
    assert client.put(f"/api/tasks/{tid}", headers=b, json={"title": "renamed"}).status_code == 200              # ...but not rename
    assert J(client.get("/api/tasks", headers=a))[0]["title"] == "Buy cake" and J(client.get("/api/tasks", headers=a))[0]["done"]
    assert client.put(f"/api/tasks/{tid}", headers=c, json={"done": False}).status_code == 404
    assert client.delete(f"/api/tasks/{tid}", headers=b).status_code == 404


def test_search_only_finds_own_content(client, make_user):
    a, b, c = make_user("sa"), make_user("sb"), make_user("sc")
    client.post("/api/chats/dm/sb/messages", headers=a, json={"text": "the zebracake secret"})
    client.post("/api/notes", headers=a, json={"title": "zebracake note", "body": ""})
    client.post("/api/notes", headers=c, json={"title": "zebracake other", "body": ""})
    ra, rb, rc = (J(client.get("/api/search?q=zebracake", headers=x)) for x in (a, b, c))
    assert len(ra["messages"]) == 1 and len(ra["notes"]) == 1
    assert len(rb["messages"]) == 1 and rb["notes"] == []
    assert rc["messages"] == [] and len(rc["notes"]) == 1                      # sc is not part of the chat and sees only their note
    assert J(client.get("/api/search?q=%25", headers=a))["messages"] == []     # '%' is not a wildcard
    assert J(client.get("/api/search?q=z", headers=a))["messages"] == []       # too short


# ------------------------------------------------------------------ music, forum, custom tabs
def test_music_links_allow_list(client, make_user):
    h = make_user("dj")
    pid = J(client.post("/api/playlists", headers=h, json={"name": "Mix", "visibility": "everyone"}))["id"]
    ok = client.post(f"/api/playlists/{pid}/tracks", headers=h, json={"title": "Song", "url": "https://www.youtube.com/watch?v=abc"})
    assert ok.status_code == 201
    for bad in ("http://youtube.com/x", "https://evil.com/x.mp3", "javascript:alert(1)", "https://youtube.com.evil.com/x", "https://evil.com/?u=youtube.com"):
        assert client.post(f"/api/playlists/{pid}/tracks", headers=h, json={"title": "Bad", "url": bad}).status_code == 400, bad
    other = make_user("dj2")
    assert [p["name"] for p in J(client.get("/api/playlists", headers=other))] == ["Mix"]
    assert client.post(f"/api/playlists/{pid}/tracks", headers=other, json={"title": "Mine", "url": "https://soundcloud.com/a"}).status_code == 404


def test_forum(client, make_user, owner):
    a, b = make_user("fa"), make_user("fb")
    mod = make_user("fmod", rank="mod")
    pid = J(client.post("/api/forum", headers=a, json={"title": "Dark mode?", "body": "please"}))["id"]
    assert J(client.post(f"/api/forum/{pid}/vote", headers=b))["voted"] is True
    assert J(client.post(f"/api/forum/{pid}/vote", headers=b))["voted"] is False
    client.post(f"/api/forum/{pid}/vote", headers=b)
    post = J(client.get("/api/forum", headers=a))[0]
    assert post["votes"] == 1 and post["author"] == "fa"
    assert client.patch(f"/api/forum/{pid}", headers=b, json={"status": "done"}).status_code == 403
    assert client.patch(f"/api/forum/{pid}", headers=mod, json={"status": "planned", "pinned": True}).status_code == 200
    assert client.delete(f"/api/forum/{pid}", headers=b).status_code == 403
    assert client.delete(f"/api/forum/{pid}", headers=a).status_code == 200


def test_custom_tabs(client, make_user):
    basic, pro = make_user("ctb"), make_user("ctp", rank="pro")
    assert client.post("/api/custom-tabs", headers=basic, json={"title": "X", "content": ""}).status_code == 403
    assert client.post("/api/custom-tabs", headers=pro, json={"title": "Links", "kind": "links", "content": "Wiki | https://wikipedia.org"}).status_code == 201
    assert client.post("/api/custom-tabs", headers=pro, json={"title": "Bad", "kind": "links", "content": "Evil | javascript:alert(1)"}).status_code == 400
    assert client.post("/api/custom-tabs", headers=pro, json={"title": "Bad", "kind": "links", "content": "no link here"}).status_code == 400


# ------------------------------------------------------------------ games, widgets
def test_games_have_own_permissions(client, make_user, owner):
    basic = make_user("gamer1")
    assert client.post("/api/games/tictactoe/score", headers=basic, json={"score": 3}).status_code == 200
    assert client.post("/api/games/memory/score", headers=basic, json={"score": 20}).status_code == 403           # not in Basic
    assert client.get("/api/games/memory/leaderboard", headers=basic).status_code == 403
    pp = make_user("gamer2", rank="pro_plus")
    assert client.post("/api/games/memory/score", headers=pp, json={"score": 20}).status_code == 200
    assert client.post("/api/games/memory/score", headers=pp, json={"score": 12}).status_code == 200
    assert J(client.post("/api/games/memory/score", headers=pp, json={"score": 30}))["best"] == 12                 # lower is better
    assert client.post("/api/games/memory/score", headers=pp, json={"score": -1}).status_code == 400
    assert any(g["id"] == "memory" and not g["allowed"] for g in J(client.get("/api/games", headers=basic)))


def test_profile_visitors(client, make_user):
    a, b = make_user("va"), make_user("vb")
    client.get("/api/users/vb", headers=a)
    client.get("/api/users/vb", headers=a)                                 # same hour: counted once
    visitors = J(client.get("/api/me/visitors", headers=b))["visitors"]
    assert [v["username"] for v in visitors] == ["va"]
    client.get("/api/users/va", headers=a) if False else None
    assert J(client.get("/api/me/visitors", headers=a))["visitors"] == []


# ------------------------------------------------------------------ what's new, ads
def test_whats_new_seen_tracking(client, make_user):
    h = make_user("newsreader")
    assert J(client.get("/api/unread", headers=h))["whatsnew"] >= 1
    assert any(not r["seen"] for r in J(client.get("/api/releases", headers=h)))
    client.post("/api/releases/seen", headers=h)
    assert J(client.get("/api/unread", headers=h))["whatsnew"] == 0
    adm = make_user("relAdmin", rank="admin")
    assert client.post("/api/releases", headers=h, json={"id": "9.9", "title": "x"}).status_code == 403
    assert client.post("/api/releases", headers=adm, json={"id": "3.1.0", "title": "More", "body": "text"}).status_code == 201
    assert client.post("/api/releases", headers=adm, json={"id": "3.1.0", "title": "More"}).status_code == 409
    assert J(client.get("/api/unread", headers=h))["whatsnew"] == 1                     # the new entry is unseen again, per person
    assert client.post("/api/releases", headers=adm, json={"id": "bad id!", "title": "x"}).status_code == 400


def test_ads_are_off_by_default_and_owner_controlled(client, make_user, owner):
    h = make_user("adviewer")
    assert J(client.get("/api/ads", headers=h))["enabled"] is False
    assert client.post("/api/ads", headers=h, json={"title": "x", "url": "https://a.b"}).status_code == 403
    assert client.post("/api/ads", headers=owner, json={"title": "Ad", "url": "javascript:alert(1)"}).status_code == 400
    assert client.post("/api/ads", headers=owner, json={"title": "Ad", "url": "https://example.com", "kind": "video"}).status_code == 201
    assert J(client.get("/api/ads", headers=h))["items"] == []
    adm = make_user("adadmin", rank="admin")
    assert client.put("/api/admin/settings", headers=adm, json={"ads": {"enabled": True}}).status_code == 403          # owner setting
    assert client.put("/api/admin/settings", headers=owner, json={"ads": {"enabled": True}}).status_code == 200
    assert len(J(client.get("/api/ads", headers=h))["items"]) == 1
    client.put("/api/admin/settings", headers=owner, json={"ads": {"enabled": False}})


# ------------------------------------------------------------------ statistics (owner decides)
def test_stats_selectable_by_owner(client, make_user, owner):
    adm = make_user("statadmin", rank="admin")
    base = J(client.get("/api/admin/stats", headers=adm))
    assert set(base["values"]) == {"users", "messages", "messages_24h", "groups", "files", "open_reports"}
    assert client.put("/api/admin/settings", headers=adm, json={"stats": {"enabled": ["coins_total"]}}).status_code == 403
    assert client.put("/api/admin/settings", headers=owner, json={"stats": {"enabled": ["coins_total", "ranks"]}}).status_code == 200
    seen = J(client.get("/api/admin/stats", headers=adm))
    assert set(seen["values"]) == {"coins_total", "ranks"} and seen["all_keys"] is None
    assert set(J(client.get("/api/admin/stats", headers=owner))["values"]) >= {"users", "coins_total", "ranks"}
    assert client.put("/api/admin/settings", headers=owner, json={"stats": {"enabled": ["passwords"]}}).status_code == 400
    client.put("/api/admin/settings", headers=owner, json={"stats": {"enabled": ["users", "messages", "messages_24h", "groups", "files", "open_reports"]}})


# ------------------------------------------------------------------ private chat access
def test_private_chat_access_is_transparent_and_rank_limited(client, make_user, owner):
    a, b = make_user("pc1"), make_user("pc2")
    client.post("/api/chats/dm/pc2/messages", headers=a, json={"text": "private words"})
    adm = make_user("pcadmin", rank="admin")
    r = client.post("/api/admin/private-chats/access", headers=adm, json={"user_a": "pc1", "user_b": "pc2", "reason": "short"})
    assert r.status_code == 400
    r = client.post("/api/admin/private-chats/access", headers=adm, json={"user_a": "pc1", "user_b": "pc2", "reason": "Report about harassment in this chat"})
    assert r.status_code == 200 and any(m["text"] == "private words" for m in J(r)["messages"])
    texts = [m["text"] for m in J(client.get("/api/chats/dm/pc1/messages", headers=b))["messages"]]
    assert any("viewed this chat" in t for t in texts)                            # both people are told
    assert any(e["action"] == "private_chat_access" for e in J(client.get("/api/admin/audit", headers=owner)))
    other_admin = make_user("pcadmin2", rank="admin")
    r = client.post("/api/admin/private-chats/access", headers=adm, json={"user_a": "pcadmin2", "user_b": "pc2", "reason": "Reason that is long enough"})
    assert r.status_code == 403                                                   # can't open the chat of an equal rank
    assert client.get("/api/admin/chat-overview", headers=make_user("pcmod", rank="mod")).status_code == 403
    ov = J(client.get("/api/admin/chat-overview", headers=adm))
    assert all("text" not in row for row in ov)                                   # metadata only


# ------------------------------------------------------------------ AI
def test_ai_disabled_by_default_and_needs_consent_and_rank(client, make_user, owner, monkeypatch):
    import ai
    basic, p3 = make_user("aib"), make_user("aip", rank="pro_pp")
    assert client.get("/api/ai/status", headers=basic).status_code == 403                    # not in Basic
    assert client.post("/api/ai/ask", headers=p3, json={"prompt": "hi"}).status_code == 503   # switched off
    assert client.put("/api/admin/settings", headers=owner, json={"ai": {"enabled": True, "daily_limit": 3}}).status_code == 200
    assert client.post("/api/ai/ask", headers=p3, json={"prompt": "hi"}).status_code == 403   # no consent yet
    assert client.post("/api/ai/consent", headers=p3, json={"adult": True}).status_code == 400
    assert client.post("/api/ai/consent", headers=p3, json={"adult": True, "understood": True}).status_code == 200
    calls = []
    monkeypatch.setattr(ai, "_call_gemini", lambda contents: calls.append(contents) or "Hello from the fake AI")
    monkeypatch.setattr("security.rate_limit", lambda *a, **k: None) if False else None
    r = client.post("/api/ai/ask", headers=p3, json={"prompt": "What is 2+2?"})
    assert r.status_code == 200 and J(r)["answer"] == "Hello from the fake AI" and J(r)["context_sent"] is False
    assert "<chat>" not in str(calls[0])                                                     # no chat data unless chosen


def test_ai_context_rules_and_limit(client, make_user, owner, monkeypatch):
    import ai
    p3 = make_user("aip2", rank="pro_pp")
    friend = make_user("aifriend")
    client.post("/api/ai/consent", headers=p3, json={"adult": True, "understood": True})
    client.post("/api/chats/dm/aip2/messages", headers=friend, json={"text": "my private plan"})
    gid = J(client.post("/api/groups", headers=p3, json={"name": "AI group", "join_mode": "open"}))["id"]
    client.post(f"/api/chats/group/{gid}/messages", headers=p3, json={"text": "group talk"})
    calls = []
    monkeypatch.setattr(ai, "_call_gemini", lambda contents: calls.append(contents) or "ok")
    # a private chat is refused without the extra confirmation
    r = client.post("/api/ai/ask", headers=p3, json={"prompt": "summarize", "context_chats": [{"type": "dm", "key": "aifriend"}]})
    assert r.status_code == 403 and not calls
    # a group chat works; a chat you are not part of never does
    r = client.post("/api/ai/ask", headers=p3, json={"prompt": "summarize", "context_chats": [{"type": "group", "key": gid}]})
    assert r.status_code == 200 and "group talk" in str(calls[-1]) and J(r)["context_sent"]
    gid2 = J(client.post("/api/groups", headers=friend, json={"name": "Not mine", "join_mode": "invite_only"}))["id"]
    assert client.post("/api/ai/ask", headers=p3, json={"prompt": "x", "context_chats": [{"type": "group", "key": gid2}]}).status_code == 403
    r = client.post("/api/ai/ask", headers=p3, json={"prompt": "summarize", "private_ok": True, "context_chats": [{"type": "dm", "key": "aifriend"}]})
    assert r.status_code == 200 and "my private plan" in str(calls[-1])
    # daily limit (set to 3 by the previous test); a failed Gemini call does not count
    from security import ApiError
    def fail(contents):
        raise ApiError("down", 502)
    monkeypatch.setattr(ai, "_call_gemini", fail)
    used = J(client.get("/api/ai/status", headers=p3))["used_today"]
    assert client.post("/api/ai/ask", headers=p3, json={"prompt": "x"}).status_code in (502, 429)
    assert J(client.get("/api/ai/status", headers=p3))["used_today"] == used
    monkeypatch.setattr(ai, "_call_gemini", lambda c: "fine")
    time.sleep(0.01)
    while J(client.get("/api/ai/status", headers=p3))["used_today"] < 3:
        assert client.post("/api/ai/ask", headers=p3, json={"prompt": "again"}).status_code == 200
    assert client.post("/api/ai/ask", headers=p3, json={"prompt": "one more"}).status_code == 429


def test_ai_key_never_leaves_the_server(client, make_user, owner):
    p3 = make_user("aip3", rank="pro_pp")
    for path in ("/api/ai/status", "/api/config", "/api/me", "/api/admin/settings"):
        assert config.GEMINI_API_KEY not in client.get(path, headers=owner).get_data(as_text=True)


# ------------------------------------------------------------------ settings and misc
def test_default_rank_setting_for_new_accounts(client, owner):
    assert client.put("/api/admin/settings", headers=owner, json={"default_rank": "admin"}).status_code == 400
    assert client.put("/api/admin/settings", headers=owner, json={"default_rank": "pro"}).status_code == 200
    assert perms.default_rank_id() == "pro"
    client.put("/api/admin/settings", headers=owner, json={"default_rank": "basic"})


def test_legal_operator_data_is_owner_only(client, make_user, owner):
    adm = make_user("legaladmin", rank="admin")
    assert client.put("/api/admin/settings", headers=adm, json={"legal": {"operator_name": "X"}}).status_code == 403
    assert client.put("/api/admin/settings", headers=owner, json={"legal": {"operator_name": "Test Operator"}}).status_code == 200
    assert J(client.get("/api/legal"))["operator"]["operator_name"] == "Test Operator"
    client.put("/api/admin/settings", headers=owner, json={"legal": {"operator_name": ""}})


def test_every_route_needs_login_or_is_public(client):
    """No API route (except the few public ones) may answer without a login."""
    import app as app_module
    public = {"/api/health", "/api/legal", "/api/config", "/api/loading", "/debug", "/api/auth/login", "/api/auth/register/start",
              "/api/auth/register/verify", "/api/auth/register/complete"}
    for rule in app_module.app.url_map.iter_rules():
        if not rule.rule.startswith("/api") or rule.rule in public:
            continue
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            path = rule.rule
            for arg in rule.arguments:
                path = path.replace(f"<int:{arg}>", "1").replace(f"<{arg}>", "x")
            res = client.open(path, method=method, json={})
            assert res.status_code == 401, f"{method} {rule.rule} answered {res.status_code} without login"


def test_account_deletion_removes_v3_personal_data(client, make_user, owner):
    import db as db_
    victim = make_user("leaver")
    make_user("stayer")
    client.post("/api/notes", headers=victim, json={"title": "secret", "body": "x"})
    client.post("/api/tasks", headers=victim, json={"title": "do it"})
    client.post("/api/forum", headers=victim, json={"title": "idea", "body": "hello"})
    db_.execute("INSERT INTO wallets (username, coins) VALUES (?, ?)", ("leaver", 5))
    db_.execute("INSERT INTO login_log (username, ts, ok) VALUES (?, ?, 1)", ("leaver", time.time()))
    db_.execute("INSERT INTO profile_visits (visited, visitor, ts) VALUES (?, ?, ?)", ("stayer", "leaver", time.time()))
    assert client.post("/api/admin/users/leaver/delete", headers=owner, json={"confirm": "leaver"}).status_code == 200
    for table, col in (("notes", "username"), ("tasks", "owner"), ("forum_posts", "author"), ("wallets", "username"),
                       ("login_log", "username"), ("profile_visits", "visitor")):
        assert not db_.query(f"SELECT 1 AS x FROM {table} WHERE {col} = ?", ("leaver",)), table
