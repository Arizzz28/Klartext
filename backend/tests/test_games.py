"""Tests for games: unlock order, matches against the computer, invitations, Elo, score limits."""
import json

import db
import gamelogic
import games


def J(r):
    return r.get_json()


def _open_all(owner_client=None):
    import appsettings
    appsettings.save({"games": {"sequential": False}})


def test_first_game_open_next_locked(client, make_user, owner):
    import perms
    h = make_user("g1")
    lst = J(client.get("/api/games", headers=h))["games"]
    by = {x["id"]: x for x in lst}
    assert by["tictactoe"]["unlocked"]
    assert by["tictactoe"]["allowed"]


def test_score_limits(client, make_user):
    h = make_user("g2")
    _open_all()
    assert client.post("/api/games/reaction/score", headers=h, json={"score": 5}).status_code == 400    # 5 ms is impossible
    assert client.post("/api/games/reaction/score", headers=h, json={"score": 300}).status_code == 200
    assert client.post("/api/games/reaction/score", headers=h, json={"score": "x"}).status_code == 400


def test_tictactoe_vs_bot_to_the_end(client, make_user):
    h = make_user("g3")
    _open_all()
    m = J(client.post("/api/matches", headers=h, json={"game": "tictactoe", "opponent": "bot", "level": "easy"}))
    mid = m["id"]
    for _ in range(9):
        cur = J(client.get(f"/api/matches/{mid}", headers=h))
        if cur["status"] == "done":
            break
        free = [i for i, c in enumerate(cur["state"]["board"]) if c is None]
        r = client.post(f"/api/matches/{mid}/move", headers=h, json={"move": {"cell": free[0]}})
        assert r.status_code == 200, J(r)
    assert J(client.get(f"/api/matches/{mid}", headers=h))["status"] == "done"
    pts = db.query("SELECT points FROM game_points WHERE username = 'g3' AND game = 'tictactoe'")
    assert pts and pts[0]["points"] >= 1


def test_invite_accept_move_and_elo(client, make_user):
    a, b = make_user("ga"), make_user("gb")
    _open_all()
    m = J(client.post("/api/matches", headers=a, json={"game": "tictactoe", "opponent": "gb"}))
    mid = m["id"]
    assert m["status"] == "invited"
    assert client.post(f"/api/matches/{mid}/move", headers=a, json={"move": {"cell": 0}}).status_code == 400   # not started
    assert client.post(f"/api/matches/{mid}/accept", headers=a).status_code == 400                           # only the invited one
    assert client.post(f"/api/matches/{mid}/accept", headers=b).status_code == 200
    seq = [(a, 0), (b, 3), (a, 1), (b, 4), (a, 2)]
    for h, cell in seq:
        r = client.post(f"/api/matches/{mid}/move", headers=h, json={"move": {"cell": cell}})
        assert r.status_code == 200, J(r)
    done = J(client.get(f"/api/matches/{mid}", headers=a))
    assert done["status"] == "done" and done["winner"] == "ga"
    ra = db.query("SELECT rating FROM elo WHERE game = 'tictactoe' AND username = 'ga'")[0]["rating"]
    rb = db.query("SELECT rating FROM elo WHERE game = 'tictactoe' AND username = 'gb'")[0]["rating"]
    assert ra > 1000 > rb


def test_cannot_move_for_somebody_else_or_out_of_turn(client, make_user):
    a, b, c = make_user("gx"), make_user("gy"), make_user("gz")
    _open_all()
    mid = J(client.post("/api/matches", headers=a, json={"game": "tictactoe", "opponent": "gy"}))["id"]
    client.post(f"/api/matches/{mid}/accept", headers=b)
    assert client.post(f"/api/matches/{mid}/move", headers=b, json={"move": {"cell": 0}}).status_code == 400    # a starts
    assert client.post(f"/api/matches/{mid}/move", headers=c, json={"move": {"cell": 0}}).status_code == 403
    assert client.get(f"/api/matches/{mid}", headers=c).status_code == 403


def test_hidden_info_not_leaked(client, make_user):
    h = make_user("gw", rank="pro")
    _open_all()
    m = J(client.post("/api/matches", headers=h, json={"game": "wordle", "opponent": "bot", "level": "hard"}))
    assert "secret" not in m["state"]


def test_games_off_and_disabled(client, make_user, owner):
    import appsettings
    h = make_user("gd")
    appsettings.save({"games": {"enabled": False}})
    assert client.post("/api/matches", headers=h, json={"game": "tictactoe", "opponent": "bot"}).status_code == 403
    appsettings.save({"games": {"enabled": True, "sequential": False, "disabled": ["tictactoe"]}})
    assert client.post("/api/matches", headers=h, json={"game": "tictactoe", "opponent": "bot"}).status_code == 403
    appsettings.save({"games": {"enabled": True, "sequential": False, "disabled": []}})                 # back to normal for the other tests


def test_admin_game_settings_validation(client, owner):
    r = client.put("/api/admin/settings", headers=owner, json={"games": {"order": ["nope"]}})
    assert r.status_code == 400


def test_memory_solo_can_be_finished(client, make_user):
    h = make_user("gm", rank="pro_plus")
    _open_all()
    import appsettings
    from gamelogic import GAMES
    mid = J(client.post("/api/matches", headers=h, json={"game": "memory", "opponent": "solo", "level": "easy"}))["id"]
    row = db.query("SELECT state FROM matches WHERE id = ?", (mid,))[0]
    deck = json.loads(row["state"])["deck"]
    pairs = {}
    for i, sym in enumerate(deck):
        pairs.setdefault(sym, []).append(i)
    for a, b in pairs.values():
        assert client.post(f"/api/matches/{mid}/move", headers=h, json={"move": {"card": a}}).status_code == 200
        assert client.post(f"/api/matches/{mid}/move", headers=h, json={"move": {"card": b}}).status_code == 200
    assert J(client.get(f"/api/matches/{mid}", headers=h))["status"] == "done"


def test_admin_can_save_game_order_and_points(client, owner, make_user):
    import appsettings
    body = {"games": {"enabled": True, "sequential": True, "order": ["aim", "tictactoe"], "unlock": {"tictactoe": 5}, "disabled": []}}
    r = client.put("/api/admin/settings", headers=owner, json=body)
    assert r.status_code == 200, J(r)
    c = games.cfg()
    assert c["order"][:2] == ["aim", "tictactoe"] and c["unlock"]["tictactoe"] == 5
    h = make_user("gq")                       # aim is now first and open; tictactoe needs 5 points in aim
    by = {x["id"]: x for x in J(client.get("/api/games", headers=h))["games"]}
    assert by["aim"]["unlocked"] and not by["tictactoe"]["unlocked"]
    appsettings.save({"games": {"sequential": False, "order": []}})


def test_prank_only_with_opt_in(client, make_user):
    a = make_user("pa", rank="pro_plus")
    b = make_user("pb", rank="pro")
    assert client.post("/api/prank/send", headers=a, json={"to": "pb", "kind": "confetti"}).status_code == 403     # pb did not allow it
    assert client.put("/api/prank/optin", headers=b, json={"enabled": True}).status_code == 200
    assert J(client.get("/api/prank/targets", headers=a)) == [{"username": "pb", "display_name": "pb"}]
    assert client.post("/api/prank/send", headers=a, json={"to": "pb", "kind": "evil"}).status_code == 400
    assert client.post("/api/prank/send", headers=a, json={"to": "pb", "kind": "confetti"}).status_code == 200
    assert client.post("/api/prank/send", headers=a, json={"to": "pb", "kind": "shake"}).status_code == 429       # too fast
    assert J(client.get("/api/prank/inbox", headers=b))["prank"]["kind"] == "confetti"
    assert J(client.get("/api/prank/inbox", headers=b))["prank"] is None                                          # only once
    client.put("/api/prank/optin", headers=b, json={"enabled": False})
    assert client.post("/api/prank/send", headers=a, json={"to": "pb", "kind": "message"}).status_code == 403
    basic = make_user("pc")
    assert client.post("/api/prank/send", headers=basic, json={"to": "pb", "kind": "message"}).status_code == 403


def test_pc_routing_and_heartbeat(client, make_user, owner, monkeypatch):
    import config
    import appsettings
    h = make_user("pcu", rank="pro_ppp")
    assert J(client.get("/api/pc/route", headers=h))["url"] is None                                        # feature off
    monkeypatch.setattr(config, "PC_SECRET", "s3cret")
    assert client.post("/api/pc/heartbeat", json={"url": "https://x.trycloudflare.com"}).status_code == 403      # no secret
    ok = client.post("/api/pc/heartbeat", headers={"X-PC-Secret": "s3cret"}, json={"url": "http://insecure.example"})
    assert ok.status_code == 400                                                                            # must be https
    assert client.post("/api/pc/heartbeat", headers={"X-PC-Secret": "s3cret"}, json={"url": "https://x.trycloudflare.com"}).status_code == 200
    appsettings.save({"pc": {"enabled": True}})
    assert J(client.get("/api/pc/route", headers=h))["reason"] == "personal_off"
    client.put("/api/me/prefs", headers=h, json={"use_pc": True})
    r = J(client.get("/api/pc/route", headers=h))
    assert r["url"] == "https://x.trycloudflare.com"
    basic = make_user("pcb")
    assert J(client.get("/api/pc/route", headers=basic))["reason"] == "rank"                                 # rank has no permission
    db.execute("UPDATE pc_status SET ts = ? WHERE id = 1", (1.0,))                                         # PC went away
    r = J(client.get("/api/pc/route", headers=h))
    assert r["url"] is None and r["reason"] == "pc_offline" and r["message"]
    appsettings.save({"pc": {"enabled": False}})


def test_streak_badges_polls(client, make_user):
    a, b = make_user("fa", rank="pro"), make_user("fb")
    r = client.post("/api/fun/streak", headers=a)
    assert r.status_code == 200 and J(r)["streak"] == 1
    assert client.post("/api/fun/streak", headers=a).status_code == 400                                     # once a day
    o = J(client.get("/api/fun", headers=a))
    assert o["claimed_today"] and not next(x for x in o["badges"] if x["id"] == "streak7")["earned"]
    assert client.post("/api/fun/polls", headers=b, json={"question": "Pizza or pasta?", "options": ["Pizza", "Pasta"]}).status_code == 403
    assert client.post("/api/fun/polls", headers=a, json={"question": "Pizza or pasta?", "options": ["Pizza", "Pizza"]}).status_code == 400
    assert client.post("/api/fun/polls", headers=a, json={"question": "Pizza or pasta?", "options": ["Pizza", "Pasta"]}).status_code == 201
    pid = J(client.get("/api/fun/polls", headers=b))["polls"][0]["id"]
    assert client.post(f"/api/fun/polls/{pid}/vote", headers=b, json={"choice": 5}).status_code == 400
    assert client.post(f"/api/fun/polls/{pid}/vote", headers=b, json={"choice": 1}).status_code == 200
    assert client.post(f"/api/fun/polls/{pid}/vote", headers=b, json={"choice": 0}).status_code == 400    # only once
    assert client.post(f"/api/fun/polls/{pid}/close", headers=b).status_code == 403
    assert client.post(f"/api/fun/polls/{pid}/close", headers=a).status_code == 200
    assert client.post(f"/api/fun/polls/{pid}/vote", headers=a, json={"choice": 0}).status_code == 404


def test_translations_only_approved_are_used(client, owner, make_user):
    import i18n
    i18n.seed()
    langs = J(client.get("/api/i18n/languages"))
    de = next(x for x in langs if x["code"] == "de")
    assert not de["complete"]                                                       # not every text is approved -> "partly translated"
    assert client.get("/api/i18n/xx").status_code == 404
    assert client.post("/api/admin/i18n/source", headers=owner, json={"source": "Hello test text"}).status_code == 201
    basic = make_user("tr1")
    assert client.put("/api/admin/i18n", headers=basic, json={"lang": "de", "source": "Hello test text", "text": "x"}).status_code == 403
    assert client.put("/api/admin/i18n", headers=owner, json={"lang": "de", "source": "Hello test text", "text": "Hallo Testtext"}).status_code == 200
    assert "Hello test text" not in J(client.get("/api/i18n/de"))["texts"]            # a draft is not used yet
    assert client.put("/api/admin/i18n", headers=owner, json={"lang": "de", "source": "Hello test text", "text": "Hallo Testtext", "approved": True}).status_code == 200
    assert J(client.get("/api/i18n/de"))["texts"]["Hello test text"] == "Hallo Testtext"
    assert client.put("/api/me/prefs", headers=basic, json={"lang": "de"}).status_code == 200
    assert client.put("/api/me/prefs", headers=basic, json={"lang": "fr"}).status_code == 400
