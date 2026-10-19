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


def test_licence_verify_and_evaluation_cap(tmp_path, monkeypatch):
    from datetime import date

    from rasad import licence

    pub = licence.keygen(str(tmp_path / "k.key"))
    doc = licence.issue(str(tmp_path / "k.key"), licensee="Org", seats=5, expires="2030-01-01", features=["core"])
    assert licence.verify(doc, pub)["licensee"] == "Org"
    doc["payload"]["seats"] = 500
    try:
        licence.verify(doc, pub)
        raise AssertionError("tampered licence verified")
    except ValueError:
        pass
    import json

    p = tmp_path / "licence.json"
    p.write_text(json.dumps(licence.issue(str(tmp_path / "k.key"), licensee="Org", seats=5, expires="2026-01-01", features=["core"])))
    monkeypatch.setattr(licence, "VENDOR_PUBLIC_KEY_B64", pub)
    assert licence.load(str(p), today=date(2025, 12, 1)).mode == "licensed"
    assert licence.load(str(p), today=date(2026, 1, 15)).mode == "grace"
    st = licence.load(str(p), today=date(2026, 3, 15))
    assert st.mode == "evaluation" and st.seats == licence.EVALUATION_SEATS
    assert licence.load(str(tmp_path / "missing.json")).mode == "evaluation"


def test_totp_rfc6238_vector():
    import base64

    from rasad.auth import totp

    secret = base64.b32encode(b"12345678901234567890").decode()
    assert totp.code_at(secret, 59 // 30) == "287082"
    step = totp.verify(secret, "287082", now=59)
    assert step == 1
    assert totp.verify(secret, "287082", now=59, last_step=step) is None  # no replay


def test_two_factor_enrolment_login_recovery_and_policy(admin_client, anon_client):
    import time as _t

    from fastapi.testclient import TestClient

    from rasad.api.app import app

    def make_client(_):
        return TestClient(app, headers={"X-Rasad-Client": "tests"})

    from rasad.auth import totp

    admin = admin_client
    uname = f"mfa{int(_t.time() * 1000) % 100000}"
    r = admin.post("/api/users", json={"username": uname, "password": "first-password-1", "role": "analyst"})
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    c = make_client(None)
    assert c.post("/api/auth/login", json={"username": uname, "password": "first-password-1"}).status_code == 200
    setup = c.post("/api/auth/mfa/setup").json()
    assert setup["uri"].startswith("otpauth://totp/") and setup["qr_svg"].startswith("<svg")
    assert c.post("/api/auth/mfa/enable", json={"code": "000000" if totp.code_at(setup["secret"], totp.current_step()) != "000000" else "111111"}).status_code == 400
    en = c.post("/api/auth/mfa/enable", json={"code": totp.code_at(setup["secret"], totp.current_step())})
    assert en.status_code == 200, en.text
    codes = en.json()["recovery_codes"]
    assert len(codes) == 8 and c.get("/api/auth/me").json()["mfa_enabled"] is True

    fresh = make_client(None)
    r = fresh.post("/api/auth/login", json={"username": uname, "password": "first-password-1"})
    assert r.status_code == 401 and r.json()["detail"] == "mfa_required"
    assert fresh.post("/api/auth/login", json={"username": uname, "password": "first-password-1", "code": "123456x"}).status_code == 401
    assert fresh.post("/api/auth/login", json={"username": uname, "password": "first-password-1", "code": codes[0]}).status_code == 200
    again = make_client(None)
    assert again.post("/api/auth/login", json={"username": uname, "password": "first-password-1", "code": codes[0]}).status_code == 401  # spent
    assert fresh.get("/api/auth/me").json()["recovery_codes_left"] == 7

    # sign out everywhere: the other session's cookie stops working, this one keeps going
    assert fresh.post("/api/auth/sessions/revoke").status_code == 200
    assert c.get("/api/board").status_code == 401
    assert fresh.get("/api/board").status_code == 200

    # admin reset for a lost phone
    assert admin.patch(f"/api/users/{uid}", json={"reset_mfa": True}).status_code == 200
    assert fresh.get("/api/board").status_code == 401
    plain = make_client(None)
    assert plain.post("/api/auth/login", json={"username": uname, "password": "first-password-1"}).status_code == 200

    # organisation policy: without a second factor only the account endpoints answer
    assert admin.put("/api/settings", json={"values": {"require_mfa": "true"}}).status_code == 200
    try:
        assert plain.get("/api/board").status_code == 403
        assert plain.get("/api/auth/me").json()["must_enrol_mfa"] is True
        assert plain.post("/api/auth/mfa/disable", json={"password": "first-password-1"}).status_code == 400
    finally:
        # the admin has no second factor either, so the policy is lifted directly
        from rasad.auth.models import Setting
        from rasad.db import session_factory

        db = session_factory()()
        db.merge(Setting(key="require_mfa", value={"v": "false"}))
        db.commit()
        db.close()
    assert plain.get("/api/board").status_code == 200
