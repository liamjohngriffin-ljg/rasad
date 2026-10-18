from __future__ import annotations

from rasad.auth.core import hash_password, make_token, parse_token, verify_password


def test_password_hashing_roundtrip():
    h = hash_password("correct horse battery")
    assert verify_password("correct horse battery", h)
    assert not verify_password("wrong", h)
    assert h.startswith("pbkdf2_sha256$")


def test_token_roundtrip_and_tamper():
    t = make_token(42)
    assert parse_token(t) == 42
    payload, sig = t.rsplit(".", 1)
    assert parse_token(payload + ".x" + sig[1:]) is None
    assert parse_token(None) is None


def test_anonymous_is_refused(anon_client):
    assert anon_client.get("/api/board").status_code == 401
    assert anon_client.get("/api/calibration").status_code == 401
    assert anon_client.get("/api/health").status_code == 200


def test_login_and_me(anon_client, users):
    r = anon_client.post("/api/auth/login", json={"username": "ana", "password": "nope"})
    assert r.status_code == 401
    r = anon_client.post("/api/auth/login", json={"username": "ANA", "password": users["ana"]})
    assert r.status_code == 200 and r.json()["role"] == "analyst"
    assert anon_client.get("/api/auth/me").json()["username"] == "ana"
    assert anon_client.post("/api/auth/logout").status_code == 200
    assert anon_client.get("/api/auth/me").status_code == 401


def test_roles_gate_actions(viewer_client, client, admin_client):
    assert viewer_client.get("/api/board").status_code == 200
    assert viewer_client.get("/api/verification/queue").status_code == 403
    assert viewer_client.post("/api/forecasts/commit", json={"as_of": "2026-10-18"}).status_code == 403
    assert client.get("/api/verification/queue").status_code == 200
    assert client.get("/api/users").status_code == 403
    assert admin_client.get("/api/users").status_code == 200


def test_admin_manages_users_and_audit(admin_client):
    r = admin_client.post("/api/users", json={"username": "newbie", "password": "a-long-password", "role": "viewer", "display_name": "New Colleague"})
    assert r.status_code == 200 and r.json()["must_change_password"] is True
    uid = r.json()["id"]
    r = admin_client.patch(f"/api/users/{uid}", json={"role": "analyst"})
    assert r.json()["role"] == "analyst"
    r = admin_client.post("/api/users", json={"username": "newbie", "password": "a-long-password"})
    assert r.status_code == 400
    me = admin_client.get("/api/auth/me").json()
    assert admin_client.patch(f"/api/users/{me['id']}", json={"role": "viewer"}).status_code == 400
    log = admin_client.get("/api/audit").json()
    assert any(e["action"] == "user_created" and e["target"] == "newbie" for e in log)


def test_password_change(viewer_client, users):
    r = viewer_client.post("/api/auth/password", json={"current_password": "wrong", "new_password": "another-long-one"})
    assert r.status_code == 400
    r = viewer_client.post("/api/auth/password", json={"current_password": users["viewer"], "new_password": "another-long-one"})
    assert r.status_code == 200
    # restore so other tests that log in as viewer still work
    r = viewer_client.post("/api/auth/password", json={"current_password": "another-long-one", "new_password": users["viewer"]})
    assert r.status_code == 200
