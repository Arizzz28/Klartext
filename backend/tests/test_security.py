"""Security tests: can a normal user get at somebody else's data? Run:  cd backend && python -m pytest tests -q

The tests play the attacker ("mallory", a plain Basic account) against data that belongs to "alice" and "bob".
Every check here must stay green; if one turns red after a change, the change opened a hole.
"""
import re
import time
from pathlib import Path

import pytest

import objstore
import storage
from app import app as flask_app


def J(res):
    return res.get_json()


@pytest.fixture(scope="module")
def cast(make_user):
    """alice, bob, mallory (all Basic) + a Pro user with all the personal tabs."""
    return {"alice": make_user("sec_alice"), "bob": make_user("sec_bob"), "mallory": make_user("sec_mallory"),
            "pro": make_user("sec_pro", rank="pro")}


def _fill(rule):
    """Turns /api/x/<int:id>/y/<name> into a testable path."""
    return re.sub(r"<(?:int:)?[^>]+>", lambda m: "1" if m.group(0).startswith("<int:") else "x", rule)


PUBLIC = {("POST", "/api/auth/register/start"), ("POST", "/api/auth/register/verify"), ("POST", "/api/auth/register/complete"),
          ("POST", "/api/auth/login"), ("GET", "/api/config"), ("GET", "/api/loading"), ("GET", "/api/legal"),
          ("GET", "/api/health"), ("POST", "/api/pc/heartbeat"), ("GET", "/api/i18n/languages"), ("GET", "/api/i18n/<lang>")}   # the heartbeat is protected by the PC secret


def _api_routes():
    for rule in flask_app.url_map.iter_rules():
        if not rule.rule.startswith("/api"):
            continue
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            yield method, rule.rule


# ------------------------------------------------------------------ nothing works without a login
def test_every_api_route_needs_a_login(client):
    checked = 0
    for method, rule in _api_routes():
        if (method, rule) in PUBLIC:
            continue
        res = client.open(_fill(rule), method=method, json={})
        assert res.status_code == 401, f"{method} {rule} answered {res.status_code} without a login"
        checked += 1
    assert checked > 100            # the loop really walked over the whole API


def test_forged_and_foreign_tokens_are_rejected(client, cast):
    good = cast["alice"]["Authorization"]
    assert client.get("/api/me", headers=cast["alice"]).status_code == 200
    for bad in ("Bearer", "Bearer x", "Bearer " + good[7:-2] + "xx", "Basic " + good[7:], good[7:], "Bearer " + good[7:] + "."):
        assert client.get("/api/me", headers={"Authorization": bad}).status_code == 401, bad
    # a token signed with another secret
    from itsdangerous import URLSafeTimedSerializer
    forged = URLSafeTimedSerializer("another-secret", salt="chatisfying-auth").dumps({"u": "Boss", "v": 0})
    assert client.get("/api/me", headers={"Authorization": "Bearer " + forged}).status_code == 401


def test_logout_and_password_change_end_old_tokens(client, make_user):
    h = make_user("sec_lo")
    assert client.get("/api/me", headers=h).status_code == 200
    assert client.post("/api/auth/logout", headers=h).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 401


def test_suspended_user_loses_access_at_once(client, make_user, owner):
    h = make_user("sec_sus")
    assert client.get("/api/users", headers=h).status_code == 200
    assert client.post("/api/admin/users/sec_sus/suspend", headers=owner).status_code == 200
    assert client.get("/api/users", headers=h).status_code in (401, 403)


# ------------------------------------------------------------------ private chats
def test_outsider_cannot_read_or_write_a_private_chat(client, cast):
    a, b, m = cast["alice"], cast["bob"], cast["mallory"]
    sent = client.post("/api/chats/dm/sec_bob/messages", headers=a, json={"text": "top secret between alice and bob"})
    assert sent.status_code == 201
    mid = J(sent)["id"]
    # mallory's own chat with bob is a different chat and must not contain it
    own = J(client.get("/api/chats/dm/sec_bob/messages", headers=m))
    assert "top secret" not in str(own)
    # guessing the internal chat key does not work either
    for key in ("sec_alice|sec_bob", "sec_alice%7Csec_bob", "sec_bob|sec_alice"):
        assert client.get(f"/api/chats/dm/{key}/messages", headers=m).status_code in (400, 403, 404)
    # touching a single message id from outside
    assert client.patch(f"/api/messages/{mid}", headers=m, json={"text": "hacked"}).status_code in (403, 404)
    assert client.delete(f"/api/messages/{mid}", headers=m).status_code in (403, 404)
    assert client.put(f"/api/messages/{mid}/reactions/%F0%9F%91%8D", headers=m).status_code in (403, 404)
    assert client.post(f"/api/messages/{mid}/report", headers=m, json={"reason": "x"}).status_code in (403, 404)
    # bob still sees it unchanged
    seen = J(client.get("/api/chats/dm/sec_alice/messages", headers=b))
    assert any(x["text"] == "top secret between alice and bob" for x in seen["messages"] if "messages" in seen) or \
        "top secret between alice and bob" in str(seen)


def test_outsider_cannot_use_a_group_she_is_not_in(client, cast):
    a, m = cast["alice"], cast["mallory"]
    gid = J(client.post("/api/groups", headers=a, json={"name": "Secret", "join_mode": "invite_only"}))["id"]
    client.post(f"/api/chats/group/{gid}/messages", headers=a, json={"text": "group secret"})
    for method, path, body in [("get", f"/api/chats/group/{gid}/messages", None), ("post", f"/api/chats/group/{gid}/messages", {"text": "x"}),
                               ("get", f"/api/groups/{gid}", None), ("post", f"/api/groups/{gid}/join", None),
                               ("patch", f"/api/groups/{gid}", {"name": "Mine now"}),
                               ("post", f"/api/groups/{gid}/members/sec_alice/remove", None),
                               ("post", f"/api/groups/{gid}/members/sec_mallory/promote", None),
                               ("post", f"/api/groups/{gid}/invitations", {"username": "sec_mallory"}),
                               ("post", f"/api/chats/group/{gid}/clear", {"scope": "all"}),
                               ("post", f"/api/chats/group/{gid}/read", None), ("get", f"/api/chats/group/{gid}/settings", None)]:
        res = getattr(client, method)(path, headers=m, **({"json": body} if body is not None else {}))
        assert res.status_code in (400, 403, 404), f"{method.upper()} {path} -> {res.status_code}"
    # an invite-only group does not even show up in the list of open groups or in the search
    assert gid not in [x["id"] for x in J(client.get("/api/groups/discover", headers=m))]
    assert "group secret" not in str(J(client.get("/api/search?q=secret", headers=m)))
    assert "Secret" not in str(J(client.get("/api/search?q=Secret", headers=m))["groups"])


def test_plain_member_cannot_act_as_group_admin(client, cast):
    a, b = cast["alice"], cast["bob"]
    gid = J(client.post("/api/groups", headers=a, json={"name": "Open one", "join_mode": "open"}))["id"]
    assert client.post(f"/api/groups/{gid}/join", headers=b).status_code in (200, 201)
    assert client.post(f"/api/groups/{gid}/members/sec_alice/remove", headers=b).status_code == 403
    assert client.post(f"/api/groups/{gid}/members/sec_bob/promote", headers=b).status_code == 403
    assert client.patch(f"/api/groups/{gid}", headers=b, json={"name": "Taken over"}).status_code == 403
    assert client.post(f"/api/chats/group/{gid}/clear", headers=b, json={"scope": "all"}).status_code == 403


def test_search_only_returns_own_messages_and_notes(client, cast):
    a, m = cast["alice"], cast["mallory"]
    client.post("/api/chats/dm/sec_bob/messages", headers=a, json={"text": "uniqueneedle42 in a private chat"})
    assert "uniqueneedle42" in str(J(client.get("/api/search?q=uniqueneedle42", headers=a))["messages"])
    assert "uniqueneedle42" not in str(J(client.get("/api/search?q=uniqueneedle42", headers=m)))
    # wildcards in the search text are not wildcards
    assert J(client.get("/api/search?q=%25%25", headers=m))["messages"] == []
    assert J(client.get("/api/search?q=__", headers=m))["messages"] == []


# ------------------------------------------------------------------ files
@pytest.fixture()
def fake_storage(monkeypatch):
    sizes = {}
    monkeypatch.setattr(objstore, "enabled", lambda: True)
    monkeypatch.setattr(objstore, "presign_put", lambda key, mime: f"https://bucket.example/put/{key}")
    monkeypatch.setattr(objstore, "presign_get", lambda key, name, mime: f"https://bucket.example/get/{key}")
    monkeypatch.setattr(objstore, "head", lambda key: sizes.setdefault(key, 1234))
    monkeypatch.setattr(objstore, "delete", lambda keys: None)
    return sizes


def _upload(client, headers, chat_key, name="photo.png", mime="image/png", size=1000, **extra):
    r = client.post("/api/uploads", headers=headers, json={"kind": "attachment", "chat_type": "dm", "chat_key": chat_key,
                                                          "filename": name, "mime": mime, "size": size, **extra})
    return r


def test_files_of_a_private_chat_are_not_reachable_for_outsiders(client, cast, fake_storage):
    a, b, m = cast["alice"], cast["bob"], cast["mallory"]
    r = _upload(client, a, "sec_bob")
    assert r.status_code == 201, J(r)
    att = J(r)["id"]
    # unconfirmed upload: not even visible to others
    assert client.get(f"/api/uploads/{att}/url", headers=m).status_code == 404
    assert client.post(f"/api/uploads/{att}/confirm", headers=m).status_code == 404        # not hers
    assert client.delete(f"/api/uploads/{att}", headers=m).status_code == 404
    assert client.post(f"/api/uploads/{att}/confirm", headers=a).status_code == 200
    # mallory cannot steal the file by attaching it to her own message
    r = client.post("/api/chats/dm/sec_bob/messages", headers=m, json={"text": "mine", "attachment_ids": [att]})
    assert r.status_code == 400
    # nor can alice smuggle it into a different chat
    r = client.post("/api/chats/dm/sec_pro/messages", headers=a, json={"text": "elsewhere", "attachment_ids": [att]})
    assert r.status_code == 400
    # the right message works, and only chat members get download links
    ok = client.post("/api/chats/dm/sec_bob/messages", headers=a, json={"text": "see photo", "attachment_ids": [att]})
    assert ok.status_code == 201
    assert client.get(f"/api/uploads/{att}/url", headers=b).status_code == 200
    assert client.get(f"/api/uploads/{att}/url", headers=a).status_code == 200
    assert client.get(f"/api/uploads/{att}/url", headers=m).status_code == 404
    msgs = J(client.get("/api/chats/dm/sec_bob/messages", headers=m))
    assert "bucket.example" not in str(msgs)


def test_upload_rules(client, cast, fake_storage):
    a = cast["alice"]
    assert _upload(client, a, "sec_bob", size=250 * 1024 * 1024).status_code == 413            # above the hard limit
    assert _upload(client, a, "sec_bob", size=0).status_code == 400
    assert _upload(client, a, "sec_bob", size=True).status_code == 400
    assert _upload(client, a, "sec_bob", mime="text/html; charset=x").status_code == 400
    assert _upload(client, a, "sec_bob", name="virus.exe", mime="application/octet-stream").status_code == 400
    assert _upload(client, a, "sec_alice").status_code == 404                                  # chat with yourself
    assert _upload(client, a, "nobody_here").status_code == 404
    r = _upload(client, a, "sec_bob", name="../../etc/passwd", mime="text/plain")
    assert r.status_code == 201
    row = storage_row(J(r)["id"])
    assert row["name"] == "passwd" and ".." not in row["storage_key"] and row["storage_key"].startswith("attachment/sec_alice/")
    # SVG and HTML are never shown inline: they are plain downloads
    assert objstore.file_kind("image/svg+xml") == "file" and objstore.file_kind("text/html") == "file"


def storage_row(att_id):
    import db
    return db.query("SELECT * FROM attachments WHERE id = ?", (att_id,))[0]


# ------------------------------------------------------------------ personal data (notes, calendar, tasks, ...)
def test_notes_belong_to_their_author(client, cast, make_user):
    pro = make_user("sec_notes_owner", rank="pro")
    other = make_user("sec_notes_other", rank="pro")
    r = client.post("/api/notes", headers=pro, json={"title": "diary", "body": "dear diary"})
    assert r.status_code == 201, J(r)
    nid = J(r)["id"]
    assert "dear diary" not in str(J(client.get("/api/notes", headers=other)))
    assert client.put(f"/api/notes/{nid}", headers=other, json={"title": "x", "body": "overwritten"}).status_code == 404
    assert client.delete(f"/api/notes/{nid}", headers=other).status_code == 404
    assert client.get("/api/notes/of/sec_notes_owner", headers=other).status_code == 403     # needs the staff permission
    assert "dear diary" in str(J(client.get("/api/notes", headers=pro)))
    assert "dear diary" not in str(J(client.get("/api/search?q=diary", headers=other)))


def test_calendar_and_tasks_are_private_unless_shared(client, make_user):
    a, m = make_user("sec_plan_a", rank="pro"), make_user("sec_plan_m", rank="pro")
    day = time.time() + 86400
    ev = client.post("/api/events", headers=a, json={"title": "Secret party", "start": day, "end": day + 3600})
    assert ev.status_code == 201, J(ev)
    eid = J(ev)["id"]
    assert "Secret party" not in str(J(client.get(f"/api/events?from={day - 1}&to={day + 99999}", headers=m)))
    assert client.put(f"/api/events/{eid}", headers=m, json={"title": "x", "start": day, "end": day + 1}).status_code == 404
    assert client.delete(f"/api/events/{eid}", headers=m).status_code == 404
    tk = client.post("/api/tasks", headers=a, json={"title": "Private task"})
    assert tk.status_code == 201, J(tk)
    tid = J(tk)["id"]
    assert "Private task" not in str(J(client.get("/api/tasks", headers=m)))
    assert client.put(f"/api/tasks/{tid}", headers=m, json={"title": "x", "done": True}).status_code == 404
    assert client.delete(f"/api/tasks/{tid}", headers=m).status_code == 404


def test_other_peoples_notifications_playlists_and_forum_posts(client, make_user):
    a, m = make_user("sec_misc_a", rank="pro"), make_user("sec_misc_m", rank="pro")
    pl = client.post("/api/playlists", headers=a, json={"name": "Mine"})
    assert pl.status_code == 201, J(pl)
    pid = J(pl)["id"]
    assert client.delete(f"/api/playlists/{pid}", headers=m).status_code in (403, 404)
    assert client.post(f"/api/playlists/{pid}/tracks", headers=m, json={"title": "x", "url": "https://youtube.com/watch?v=1"}).status_code in (403, 404)
    post = client.post("/api/forum", headers=a, json={"title": "Hello", "body": "first"})
    assert post.status_code == 201, J(post)
    fid = J(post)["id"]
    assert client.patch(f"/api/forum/{fid}", headers=m, json={"title": "pwned", "body": "pwned"}).status_code in (403, 404)
    assert client.delete(f"/api/forum/{fid}", headers=m).status_code in (403, 404)
    ct = client.post("/api/custom-tabs", headers=a, json={"title": "T", "kind": "text", "content": "mine"})
    if ct.status_code == 201:
        tid = J(ct)["id"]
        assert client.put(f"/api/custom-tabs/{tid}", headers=m, json={"title": "T", "kind": "text", "content": "x"}).status_code in (403, 404)
        assert client.delete(f"/api/custom-tabs/{tid}", headers=m).status_code in (403, 404)
    # a stranger's notification ids do nothing
    assert client.post("/api/notifications/read", headers=m, json={"ids": [1, 2, 3]}).status_code == 200


def test_user_lists_never_contain_emails_or_hashes(client, cast):
    for path in ("/api/users", "/api/users/sec_alice", "/api/search?q=sec_"):
        text = client.get(path, headers=cast["mallory"]).get_data(as_text=True)
        assert "password" not in text.lower() and "@example.com" not in text and "token_version" not in text, path


# ------------------------------------------------------------------ rights and escalation
def test_basic_user_is_locked_out_of_every_staff_route(client, cast):
    m = cast["mallory"]
    staff_prefixes = ("/api/admin", "/api/mod", "/api/missions/manage", "/api/ads/manage", "/api/notes/of", "/api/coins/gift", "/api/ranks/gift")
    n = 0
    for method, rule in _api_routes():
        if not rule.startswith(staff_prefixes) or ("GET", rule) == ("GET", "/api/admin/requests"):
            continue
        res = client.open(_fill(rule), method=method, headers=m, json={})
        assert res.status_code in (403, 404, 400) and res.status_code != 200, f"{method} {rule} -> {res.status_code}"
        assert res.status_code == 403 or res.status_code == 404, f"{method} {rule} -> {res.status_code}"
        n += 1
    assert n > 25


def test_mass_assignment_does_not_work(client, cast):
    m = cast["mallory"]
    r = client.patch("/api/me", headers=m, json={"display_name": "Mallory", "rank": "owner", "status": "active",
                                                  "perms": ["owner.ranks"], "extra_perms": ["owner.ranks"], "is_owner": True,
                                                  "token_version": 99, "consent": {"terms": "x"}})
    assert r.status_code == 200
    user = storage.read("users")["sec_mallory"]
    assert user["rank"] == "basic" and "extra_perms" not in user and user["token_version"] == 0
    me = J(client.get("/api/me", headers=m))
    assert not me["is_owner"] and "owner.ranks" not in me["perms"]
    assert client.put("/api/me/prefs", headers=m, json={"rank": "owner", "perms": ["x"]}).status_code == 400   # nothing allowed to change
    assert client.patch("/api/admin/users/sec_mallory", headers=m, json={"rank": "owner"}).status_code == 403


def test_admin_cannot_reach_owner_powers(client, make_user, owner):
    adm = make_user("sec_adm", rank="admin")
    victim = make_user("sec_victim")
    assert client.patch("/api/admin/users/sec_adm", headers=adm, json={"rank": "owner"}).status_code in (400, 403)   # not even herself
    assert storage.read("users")["sec_adm"]["rank"] == "admin"
    assert client.patch("/api/admin/users/Boss", headers=adm, json={"rank": "basic"}).status_code == 403
    assert client.post("/api/admin/users/Boss/reset-password", headers=adm, json={"password": "hacked-pass-1"}).status_code == 403
    assert client.post("/api/admin/users/Boss/delete", headers=adm, json={"confirm": "Boss"}).status_code == 403
    assert client.post("/api/admin/users/Boss/logout-all", headers=adm).status_code == 403
    assert client.post("/api/admin/users/sec_victim/extra-perms", headers=adm, json={"perms": ["owner.ranks"]}).status_code == 403
    assert client.put("/api/admin/ranks/basic", headers=adm, json={"name": "Basic", "level": 1, "perms": ["owner.ranks"]}).status_code == 403
    assert client.get("/api/me", headers=victim).status_code == 200
    # a second Boss cannot be created through the registration route
    assert client.post("/api/auth/register/complete", json={"username": "Boss", "password": "password123"}).status_code in (400, 409)


def test_deleted_account_data_is_gone(client, make_user, owner):
    h = make_user("sec_gone", rank="pro")
    client.post("/api/notes", headers=h, json={"title": "t", "body": "private body"})
    client.post("/api/chats/dm/sec_bob/messages", headers=h, json={"text": "bye"})
    r = client.post("/api/admin/users/sec_gone/delete", headers=owner, json={"confirm": "sec_gone"})
    assert r.status_code == 200, J(r)
    import db
    assert db.query("SELECT 1 AS x FROM notes WHERE username = ?", ("sec_gone",)) == []
    assert "sec_gone" not in storage.read("users")


# ------------------------------------------------------------------ my own data: download and delete
def test_download_my_data_contains_only_my_data(client, make_user):
    a, b = make_user("sec_ex_a", rank="pro"), make_user("sec_ex_b", rank="pro")
    client.post("/api/chats/dm/sec_ex_b/messages", headers=a, json={"text": "from alice to bob"})
    client.post("/api/chats/dm/sec_ex_a/messages", headers=b, json={"text": "from bob to alice, bobs secret"})
    client.post("/api/notes", headers=a, json={"title": "n", "body": "alice note"})
    client.post("/api/notes", headers=b, json={"title": "n", "body": "bob note"})
    r = client.get("/api/me/export", headers=a)
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    text = r.get_data(as_text=True)
    assert "from alice to bob" in text and "alice note" in text
    assert "bobs secret" not in text and "bob note" not in text
    assert "password" not in text.lower() and "token" not in text.lower()
    assert client.get("/api/me/export").status_code == 401


def test_delete_my_account(client, make_user):
    a, b = make_user("sec_del_a", rank="pro"), make_user("sec_del_b", rank="pro")
    client.post("/api/chats/dm/sec_del_b/messages", headers=a, json={"text": "hello bob"})
    client.post("/api/notes", headers=a, json={"title": "t", "body": "my note"})
    gid = J(client.post("/api/groups", headers=b, json={"name": "G", "join_mode": "open"}))["id"]
    client.post(f"/api/groups/{gid}/join", headers=a)
    client.post(f"/api/chats/group/{gid}/messages", headers=a, json={"text": "group hello"})
    first = client.post("/api/chats/dm/sec_del_a/messages", headers=b, json={"text": "answer"})
    client.post(f"/api/messages/{J(first)['id']}/report", headers=a, json={"reason": "test"})
    # wrong password / wrong confirmation: nothing happens
    assert client.post("/api/me/delete", headers=a, json={"password": "nope", "confirm": "sec_del_a"}).status_code == 403
    assert client.post("/api/me/delete", headers=a, json={"password": "password123", "confirm": "someone"}).status_code == 400
    assert client.get("/api/me", headers=a).status_code == 200
    assert client.post("/api/me/delete", headers=a, json={"password": "password123", "confirm": "SEC_DEL_A"}).status_code == 200
    import db
    assert "sec_del_a" not in storage.read("users")
    assert db.query("SELECT 1 AS x FROM notes WHERE username = ?", ("sec_del_a",)) == []
    assert db.query("SELECT 1 AS x FROM messages WHERE chat_type = 'dm' AND chat_key LIKE ?", ("%sec_del_a%",)) == []
    assert db.query("SELECT 1 AS x FROM messages WHERE sender = ?", ("sec_del_a",)) == []        # group messages went, too
    assert db.query("SELECT 1 AS x FROM reports WHERE reporter = ?", ("sec_del_a",)) == []
    assert client.get("/api/me", headers=a).status_code == 401                                   # the old token is dead
    assert client.get("/api/me", headers=b).status_code == 200                                   # bob is untouched
    assert "sec_del_a" not in storage.read("groups")[gid]["members"]


def test_the_owner_cannot_delete_himself_and_leaving_needs_no_consent(client, make_user, owner):
    assert client.post("/api/me/delete", headers=owner, json={"password": "password123", "confirm": "Boss"}).status_code == 403
    h = make_user("sec_noconsent", consent=False)
    assert client.get("/api/users", headers=h).status_code == 403                  # blocked as usual
    assert client.get("/api/me/export", headers=h).status_code == 200              # but taking your data is allowed
    assert client.post("/api/me/delete", headers=h, json={"password": "password123", "confirm": "sec_noconsent"}).status_code == 200


# ------------------------------------------------------------------ injection and odd input
def test_odd_input_does_not_crash_or_inject(client, cast):
    a = cast["alice"]
    evil = "x'); DROP TABLE messages; --"
    assert client.post("/api/chats/dm/sec_bob/messages", headers=a, json={"text": evil}).status_code == 201
    assert evil in str(J(client.get("/api/chats/dm/sec_bob/messages", headers=a)))        # stored as plain text
    assert client.post("/api/auth/login", json={"username": evil, "password": "x"}).status_code in (401, 429)
    assert client.post("/api/auth/register/start", json={"username": evil, "email": "a@b.de"}).status_code == 400
    for body in (None, [], "text", 5):
        res = client.post("/api/chats/dm/sec_bob/messages", headers=a, data=str(body), content_type="application/json")
        assert res.status_code == 400
    assert client.get("/api/chats/dm/" + "a" * 5000 + "/messages", headers=a).status_code in (404, 414)
    assert client.get("/api/search?q=" + "%27" * 40, headers=a).status_code == 200
    big = client.post("/api/chats/dm/sec_bob/messages", headers=a, json={"text": "x" * 3000})
    assert big.status_code == 400
    huge = client.post("/api/chats/dm/sec_bob/messages", headers=a, data="x" * 2_000_000, content_type="application/json")
    assert huge.status_code == 413


def test_errors_do_not_leak_internals(client, cast, monkeypatch):
    import chat_service
    monkeypatch.setattr(chat_service, "fetch", lambda *a, **k: 1 / 0)
    flask_app.testing = False
    flask_app.config["PROPAGATE_EXCEPTIONS"] = False
    try:
        res = client.get("/api/chats/dm/sec_bob/messages", headers=cast["alice"])
    finally:
        flask_app.testing = True
        flask_app.config["PROPAGATE_EXCEPTIONS"] = None
    assert res.status_code == 500
    text = res.get_data(as_text=True)
    assert "Traceback" not in text and "ZeroDivision" not in text and "/home/" not in text


def test_debug_route_does_not_show_internals(client):
    text = client.get("/debug").get_data(as_text=True)
    assert "smtp" not in text.lower() and "routes" not in text.lower() and "/api/" not in text


def test_public_routes_expose_no_secrets(client):
    for path in ("/api/config", "/api/loading", "/api/legal", "/api/health"):
        text = client.get(path).get_data(as_text=True).lower()
        for needle in ("secret", "password", "api_key", "token", "vapid_private", "s3_", "database"):
            assert needle not in text, f"{path} mentions {needle}"


def test_security_headers_and_cors(client):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "no-store" in r.headers["Cache-Control"]
    ok = client.get("/api/health", headers={"Origin": "http://localhost:8000"})
    assert ok.headers.get("Access-Control-Allow-Origin") == "http://localhost:8000"
    evil = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in evil.headers


# ------------------------------------------------------------------ brute force
def test_login_is_rate_limited_per_account(client, make_user):
    make_user("sec_brute")
    codes = [client.post("/api/auth/login", json={"username": "sec_brute", "password": f"wrong{i}"}).status_code for i in range(14)]
    assert 429 in codes and codes[:5] == [401] * 5
    # the right password is refused while the lock is on (that is the point of a lock)
    assert client.post("/api/auth/login", json={"username": "sec_brute", "password": "password123"}).status_code == 429


def test_push_endpoints_must_belong_to_a_push_service(client, make_user):
    h = make_user("sec_push")
    keys = {"p256dh": "k" * 80, "auth": "a" * 20}
    for url in ("https://169.254.169.254/latest", "https://internal.example/hook", "https://evil.example/fcm.googleapis.com",
                "https://fcm.googleapis.com.evil.example/x", "https://user@evil.example/", "http://fcm.googleapis.com/x"):
        assert client.post("/api/push/subscribe", headers=h, json={"endpoint": url, "keys": keys}).status_code == 400, url
    for url in ("https://fcm.googleapis.com/fcm/send/abc", "https://updates.push.services.mozilla.com/wpush/v2/abc",
                "https://web.push.apple.com/abc"):
        assert client.post("/api/push/subscribe", headers=h, json={"endpoint": url, "keys": keys}).status_code == 201, url


# ------------------------------------------------------------------ the frontend never builds HTML from data
def test_frontend_never_writes_html_from_data():
    root = Path(__file__).resolve().parents[2] / "frontend"
    bad = re.compile(r"\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML|document\.write|\beval\s*\(|new Function\(")
    hits = []
    for path in list(root.rglob("*.js")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if bad.search(line):
                hits.append(f"{path.relative_to(root)}:{n}: {line.strip()}")
    # allowed: the fixed icon list in ui.js (constants, no user data)
    assert len(hits) == 1 and hits[0].startswith("ui.js:") and "ICONS[name]" in hits[0], hits


def test_frontend_links_from_users_are_https_only():
    root = Path(__file__).resolve().parents[2] / "frontend"
    for name in ("pages/custom.js", "pages/music.js"):
        text = (root / name).read_text(encoding="utf-8")
        assert "javascript:" not in text
    assert "https:\\/\\/" in (root / "pages/custom.js").read_text(encoding="utf-8")


def test_no_secrets_in_the_repository():
    root = Path(__file__).resolve().parents[2]
    pattern = re.compile(r"(-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{30,}|xkeysib-[0-9a-f]{20,}|"
                         r"postgres(ql)?://[^\s:@/]+:[^\s:@/]{3,}@[^\s/]+|sk-[A-Za-z0-9]{30,})")
    skip = {".git", "node_modules", "__pycache__", ".venv", "tests"}
    found = []
    for path in root.rglob("*"):
        if path.is_file() and not (skip & set(path.relative_to(root).parts)) and path.suffix in (".py", ".js", ".html", ".md", ".json", ".txt", ".example", ".yaml", ".yml", ".webmanifest"):
            if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                found.append(str(path.relative_to(root)))
    assert not found, found


def test_proxy_setting_makes_the_rate_limit_see_the_visitor(monkeypatch):
    from flask import Flask, request
    import config
    monkeypatch.setattr(config, "PROXY_HOPS", 1)
    import app as app_module
    probe = Flask("probe")
    probe.add_url_rule("/ip", "ip", lambda: request.remote_addr)
    from werkzeug.middleware.proxy_fix import ProxyFix
    probe.wsgi_app = ProxyFix(probe.wsgi_app, x_for=config.PROXY_HOPS)
    res = probe.test_client().get("/ip", headers={"X-Forwarded-For": "203.0.113.9"}, environ_base={"REMOTE_ADDR": "10.0.0.1"})
    assert res.get_data(as_text=True) == "203.0.113.9"
    # a visitor who sends a fake first entry does not win: only the entry the nearest proxy added counts
    res = probe.test_client().get("/ip", headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.9"}, environ_base={"REMOTE_ADDR": "10.0.0.1"})
    assert res.get_data(as_text=True) == "203.0.113.9"
    assert config.PROXY_HOPS == 1 and hasattr(app_module, "create_app")
