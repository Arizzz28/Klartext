"""Tests for Chatisfying 4.0: random missions, free missions, translations, coin transfers, ...  Run: python -m pytest tests -q"""
import pytest

import appsettings
import db


def J(res):
    return res.get_json()


@pytest.fixture
def random_missions():
    appsettings.save({"missions": {"mode": "random", "slots_hourly": 0, "slots_daily": 2, "slots_weekly": 1}})
    yield


def _mission(client, owner, **kw):
    body = {"title": "Test mission", "kind": "none", "target": 1, "period": "daily", "reward": 7, "rarity": "common", **kw}
    r = client.post("/api/missions", headers=owner, json=body)
    assert r.status_code == 201, r.get_json()
    return max(m["id"] for m in db.query("SELECT id FROM missions"))


def test_each_person_gets_only_their_slots(client, make_user, owner, random_missions):
    h = make_user("rnd1")
    got = J(client.get("/api/missions", headers=h))["missions"]
    assert sum(m["period"] == "daily" for m in got) <= 2
    assert sum(m["period"] == "weekly" for m in got) <= 1
    again = J(client.get("/api/missions", headers=h))["missions"]
    assert [m["id"] for m in got] == [m["id"] for m in again]               # the draw is kept for the whole period


def test_a_mission_that_was_not_drawn_can_not_be_collected(client, make_user, owner, random_missions):
    h = make_user("rnd2")
    for i in range(6):
        _mission(client, owner, title=f"Extra free {i}", kind="none")
    shown = {m["id"] for m in J(client.get("/api/missions", headers=h))["missions"]}
    hidden = [r["id"] for r in db.query("SELECT id FROM missions WHERE active = 1 AND kind = 'none' AND period = 'daily'") if r["id"] not in shown]
    assert hidden, "with 2 slots and many free missions some must stay hidden"
    assert client.post(f"/api/missions/{hidden[0]}/claim", headers=h).status_code == 404


def test_free_mission_pays_once_per_period(client, make_user, owner):
    appsettings.save({"missions": {"mode": "all"}})
    h = make_user("free1")
    mid = _mission(client, owner, title="Free gift", reward=11)
    assert client.post(f"/api/missions/{mid}/claim", headers=h).status_code == 200
    assert client.post(f"/api/missions/{mid}/claim", headers=h).status_code == 409
    assert J(client.get("/api/coins", headers=h))["coins"] >= 11
    appsettings.save({"missions": {"mode": "random"}})


def test_rarity_weight_zero_is_never_drawn(client, make_user, owner):
    appsettings.save({"missions": {"mode": "random", "slots_daily": 1, "w_common": 0, "w_rare": 1000}})
    try:
        keep = db.query("SELECT id FROM missions WHERE period = 'daily' AND active = 1")
        db.execute("UPDATE missions SET active = 0 WHERE period = 'daily'")
        a = _mission(client, owner, title="Common one", rarity="common")
        b = _mission(client, owner, title="Rare one", rarity="rare")
        for i in range(15):
            shown = [m["id"] for m in J(client.get("/api/missions", headers=make_user(f"w{i}")))["missions"] if m["period"] == "daily"]
            assert shown == [b]
    finally:
        db.execute("UPDATE missions SET active = 0 WHERE id IN (?, ?)", (a, b))
        for r in keep:
            db.execute("UPDATE missions SET active = 1 WHERE id = ?", (r["id"],))
        appsettings.save({"missions": {"mode": "random", "slots_daily": 2, "w_common": 60, "w_rare": 10}})


def test_bad_mission_input_is_refused(client, owner):
    base = {"title": "Bad one", "kind": "none", "target": 1, "period": "daily", "reward": 5}
    assert client.post("/api/missions", headers=owner, json={**base, "rarity": "godlike"}).status_code == 400
    assert client.post("/api/missions", headers=owner, json={**base, "period": "yearly"}).status_code == 400
    assert client.post("/api/missions", headers=owner, json={**base, "period": "hourly"}).status_code == 201


def test_translation_flow_with_admin_check(client, make_user, owner):
    appsettings.save({"missions": {"mode": "all"}})
    h, admin = make_user("tr1"), make_user("tradmin", rank="admin")
    mid = _mission(client, owner, title="Translate two", kind="translate", target=2, reward=40, period="weekly")
    m = next(x for x in J(client.get("/api/missions", headers=h))["missions"] if x["id"] == mid)
    assert len(m["tasks"]) == 2 and not m["claimable"]
    assert client.post(f"/api/missions/{mid}/claim", headers=h).status_code == 400
    r = client.post(f"/api/missions/{mid}/translate", headers=h, json={"answers": {str(t["id"]): "Deutsch " + str(t["id"]) for t in m["tasks"]}})
    assert J(r)["sent"] == 2
    # nobody can approve their own work, normal users can not review at all
    queue = J(client.get("/api/translations/review", headers=admin))["items"]
    mine = [q for q in queue if q["username"] == "tr1"]
    assert len(mine) == 2
    assert client.get("/api/translations/review", headers=h).status_code == 403
    assert client.post(f"/api/translations/{mine[0]['id']}/review", headers=h, json={"approve": True}).status_code == 403
    assert client.post(f"/api/translations/{mine[0]['id']}/review", headers=admin, json={"approve": True}).status_code == 200
    assert client.post(f"/api/missions/{mid}/claim", headers=h).status_code == 400          # only 1 of 2 approved
    assert client.post(f"/api/translations/{mine[1]['id']}/review", headers=admin, json={"approve": False, "note": "check the verb"}).status_code == 200
    m = next(x for x in J(client.get("/api/missions", headers=h))["missions"] if x["id"] == mid)
    assert any(t["status"] == "open" and t["note"] == "check the verb" for t in m["tasks"])   # sent back with a note
    retry = next(t for t in m["tasks"] if t["status"] == "open")
    client.post(f"/api/missions/{mid}/translate", headers=h, json={"answers": {str(retry["id"]): "Besser"}})
    assert client.post(f"/api/translations/{retry['id']}/review", headers=admin, json={"approve": True}).status_code == 200
    assert client.post(f"/api/missions/{mid}/claim", headers=h).status_code == 200
    appsettings.save({"missions": {"mode": "random"}})


def test_someone_elses_translation_tasks_can_not_be_changed(client, make_user, owner):
    appsettings.save({"missions": {"mode": "all"}})
    a, b = make_user("tr2"), make_user("tr3")
    mid = _mission(client, owner, title="Translate one", kind="translate", target=1, period="weekly")
    ta = next(x for x in J(client.get("/api/missions", headers=a))["missions"] if x["id"] == mid)["tasks"][0]
    client.get("/api/missions", headers=b)
    r = client.post(f"/api/missions/{mid}/translate", headers=b, json={"answers": {str(ta["id"]): "stolen"}})
    assert J(r)["sent"] == 0
    appsettings.save({"missions": {"mode": "random"}})


def test_coin_transfer(client, make_user, owner):
    a, b = make_user("send1"), make_user("send2")
    client.post("/api/coins/gift", headers=owner, json={"username": "send1", "amount": 500})
    assert client.post("/api/coins/send", headers=a, json={"username": "send2", "amount": 50}).status_code == 200
    assert J(client.get("/api/coins", headers=b))["coins"] == 50
    assert J(client.get("/api/coins", headers=a))["coins"] == 450
    assert client.post("/api/coins/send", headers=a, json={"username": "send1", "amount": 5}).status_code == 400      # not to yourself
    assert client.post("/api/coins/send", headers=a, json={"username": "send2", "amount": -5}).status_code == 400    # no negative trick
    assert client.post("/api/coins/send", headers=a, json={"username": "send2", "amount": 10 ** 6}).status_code in (402, 403)
    assert client.post("/api/coins/send", headers=a, json={"username": "send2", "amount": 160}).status_code == 403    # over the daily limit (200)
    assert J(client.get("/api/coins", headers=a))["coins"] == 450


def test_storage_check_is_for_admins_only(client, make_user, owner):
    assert client.get("/api/admin/storage-check", headers=make_user("diag1")).status_code == 403
    r = client.get("/api/admin/storage-check", headers=owner)
    assert r.status_code == 200 and r.get_json()["steps"][0]["ok"] is False        # no storage configured in tests
