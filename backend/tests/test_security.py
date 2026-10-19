"""Regression tests for the October 2026 security review."""

import httpx
import pytest
from fastapi.testclient import TestClient

from rasad.api.app import app


def _c():
    return TestClient(app, headers={"X-Rasad-Client": "tests"})


def test_throttle_cannot_be_dodged_with_spaces_or_case(users):
    from rasad.api import auth_routes

    auth_routes.throttle._hits.clear()
    auth_routes.ip_throttle._hits.clear()
    c = _c()
    for i in range(10):
        assert c.post("/api/auth/login", json={"username": "viewer", "password": f"wrong-{i}"}).status_code == 401
    for variant in ("viewer", " viewer", "VIEWER  ", "\tviewer"):
        r = c.post("/api/auth/login", json={"username": variant, "password": users["viewer"]})
        assert r.status_code == 429, variant
    auth_routes.throttle._hits.clear()
    auth_routes.ip_throttle._hits.clear()


def test_forwarded_for_is_not_trusted_without_the_proxy(monkeypatch):
    from starlette.requests import Request

    from rasad.api.deps import client_ip

    req = Request({"type": "http", "headers": [(b"x-forwarded-for", b"6.6.6.6, 10.0.0.9")], "client": ("172.18.0.5", 1234)})
    monkeypatch.delenv("RASAD_TRUST_PROXY", raising=False)
    assert client_ip(req) == "172.18.0.5"
    monkeypatch.setenv("RASAD_TRUST_PROXY", "true")
    assert client_ip(req) == "10.0.0.9"  # the proxy's own entry, never the client-supplied first one


def test_logout_ends_that_session_only(users):
    a, b = _c(), _c()
    assert a.post("/api/auth/login", json={"username": "ana", "password": users["ana"]}).status_code == 200
    assert b.post("/api/auth/login", json={"username": "ana", "password": users["ana"]}).status_code == 200
    kept = a.cookies.get("rasad_session")
    assert a.post("/api/auth/logout").status_code == 200
    replay = _c()
    replay.cookies.set("rasad_session", kept)
    assert replay.get("/api/auth/me").status_code == 401  # a copied cookie dies with the sign-out
    assert b.get("/api/auth/me").status_code == 200  # the other browser stays signed in


def test_reactivation_respects_seats(admin_client, monkeypatch):
    from rasad import licence

    r = admin_client.post("/api/users", json={"username": "seatcheck", "password": "temp-password-1", "role": "viewer"})
    uid = r.json()["id"]
    assert admin_client.patch(f"/api/users/{uid}", json={"active": False}).status_code == 200
    full = licence.current()
    from rasad.auth.models import User
    from rasad.db import session_factory
    from sqlalchemy import func, select

    s = session_factory()()
    active = s.scalar(select(func.count(User.id)).where(User.active.is_(True)))
    s.close()
    monkeypatch.setattr(licence, "_cached", licence.LicenceState("licensed", licensee="t", seats=active, features=full.features))
    try:
        assert admin_client.patch(f"/api/users/{uid}", json={"active": True}).status_code == 403
    finally:
        monkeypatch.setattr(licence, "_cached", full)


def test_vendor_key_has_no_environment_override():
    import inspect

    from rasad import licence

    src = inspect.getsource(licence)
    assert 'getenv("RASAD_VENDOR_PUBLIC_KEY"' not in src


def test_redirects_off_the_allow_list_are_refused(monkeypatch):
    from rasad.pipelines.connectors import base

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.gov.uk":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
        return httpx.Response(200, text="internal secret")

    real = httpx.Client
    monkeypatch.setattr(base.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(base.EgressRefused):
        base.fetch_text("https://www.gov.uk/start")


def test_csv_cells_cannot_run_as_formulas():
    from rasad.api.admin_routes import _cell

    assert _cell('=HYPERLINK("http://evil.example","x")').startswith("'=")
    assert _cell("+44 20") == "'+44 20" and _cell("@SUM(A1)") == "'@SUM(A1)" and _cell("plain") == "plain" and _cell(3) == 3


def test_export_name_and_paging_are_bounded(admin_client):
    assert admin_client.get('/api/export/series.csv?name=x";%20filename="evil.html').status_code == 422
    assert admin_client.get("/api/events?days=1000000000").status_code == 422


def test_viewer_limits_and_attribution(viewer_client):
    assert viewer_client.post("/api/indicators/preview", json={"rule": {"type": "event_count"}}).status_code == 403
    r = viewer_client.post("/api/tasking", json={"text": "What is the risk to Ras Laffan this month?", "requested_by": "Minister of Defence"})
    assert r.status_code == 200
    rows = viewer_client.get("/api/tasking").json()
    row = next(t for t in rows if t["id"] == r.json()["id"])
    assert "entered by viewer" in row["requested_by"]


def test_costly_gets_need_the_client_header(users):
    c = TestClient(app)  # no client header, as a cross-site link would be
    c.post("/api/auth/login", json={"username": "ana", "password": users["ana"]}, headers={"X-Rasad-Client": "t"})
    assert c.get("/api/briefs/hormuz_closure_90?lang=en").status_code == 403
    assert c.get("/api/briefs/weekly?lang=en").status_code == 403
    assert c.get("/api/board").status_code == 200


def test_api_docs_are_off_and_headers_are_set(client):
    assert client.get("/api/openapi.json").status_code in (401, 404)
    r = client.get("/api/board")
    assert r.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"


def test_temporary_password_must_be_changed_before_anything_else(admin_client):
    admin_client.post("/api/users", json={"username": "fresh1", "password": "temp-password-1", "role": "analyst"})
    c = _c()
    assert c.post("/api/auth/login", json={"username": "fresh1", "password": "temp-password-1"}).status_code == 200
    assert c.get("/api/board").json()["detail"] == "password_change_required"
    assert c.get("/api/auth/me").status_code == 200


def test_webhook_refuses_internal_and_shared_ranges():
    from rasad.engine import notify

    for u in ("https://100.100.100.100/x", "https://10.1.2.3/x", "https://127.0.0.1/x", "https://169.254.169.254/x"):
        with pytest.raises(ValueError):
            notify.check_url(u)
