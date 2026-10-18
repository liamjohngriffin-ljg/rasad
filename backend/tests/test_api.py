from __future__ import annotations


def test_status_and_board(client):
    r = client.get("/api/status")
    assert r.status_code == 200 and r.json()["open_questions"] == 10
    b = client.get("/api/board?as_of=2026-10-18").json()
    assert len(b["questions"]) == 10
    q = b["questions"][0]
    assert 0.02 <= q["final_prob"] <= 0.98 and len(q["history"]) >= 10 and q["movers"]


def test_question_detail_decomposes(client):
    d = client.get("/api/questions/hormuz_closure_90?as_of=2026-10-18").json()
    assert d["indicators"] and all("state" in i and "evidence" in i for i in d["indicators"])
    present = [i for i in d["indicators"] if i["state"] == "present"]
    assert present and any(i["code"] == "iran_revealed_closure" for i in present)


def test_position_book_and_divergence(client):
    bk = client.get("/api/actors/IR/book?as_of=2026-10-18").json()
    hormuz = next(i for i in bk["issues"] if i["issue"] == "hormuz_posture")
    assert hormuz["revealed"]["score"] > 0.5 and hormuz["divergence"] is not None
    obs = client.get("/api/actors/IR/issues/hormuz_posture/observations").json()
    assert obs and all("verification" in o for o in obs)


def test_calibration_chain_verifies(client):
    c = client.get("/api/calibration").json()
    assert c["chain"]["verified"] is True and c["chain"]["length"] > 0
    assert c["resolved"] and c["all"]["n"] == 4


def test_briefs_both_languages(client):
    en = client.get("/api/briefs/gulf_infra_strike_90?lang=en&as_of=2026-10-18&polish=false").json()
    ar = client.get("/api/briefs/gulf_infra_strike_90?lang=ar&as_of=2026-10-18&polish=false").json()
    assert "## Judgement" in en["content_md"] and en["generator"] == "template"
    assert "## الحكم" in ar["content_md"]


def test_verification_and_tasking(client):
    q = client.get("/api/verification/queue").json()
    assert q["events"] or q["observations"]
    if q["events"]:
        eid = q["events"][0]["id"]
        r = client.post(f"/api/verification/event/{eid}", json={"decision": "verified", "by": "ana"})
        assert r.status_code == 200 and r.json()["verification"] == "verified"
    r = client.post("/api/tasking", json={"text": "Probability of a Houthi strike on Jeddah port within 30 days?", "requested_by": "principal"})
    assert r.status_code == 200
    assert client.get("/api/tasking").json()[0]["status"] == "open"


def test_commit_is_idempotent(client):
    a = client.post("/api/forecasts/commit", json={"as_of": "2026-10-18"}).json()
    b = client.post("/api/forecasts/commit", json={"as_of": "2026-10-18"}).json()
    assert a == b


def test_workflow_question_indicator_panel_resolution(client):
    vocab = client.get("/api/reference/vocab").json()
    assert "event_count" in vocab["rule_types"] and "hormuz_transits" in vocab["series"]
    r = client.post("/api/questions", json={
        "code": "test_q_90", "title_en": "Will a test question resolve yes within 90 days?", "horizon_days": 90,
        "resolution_criteria": "Resolves yes if the test passes.", "decision_hooks": ["none"], "base_rate": 0.2,
        "indicators": [{"code": "attacks", "name_en": "Maritime attacks in the Gulf", "lr_present": 3.0, "lr_absent": 0.6,
                        "rule": {"type": "event_count", "event_types": ["maritime_attack"], "countries": ["HORMUZ", "OM", "AE"], "window_days": 30, "threshold": 1}}],
    })
    assert r.status_code == 201, r.text
    q = r.json()
    assert q["status"] == "open" and len(q["indicators"]) == 1
    bad = client.post("/api/questions/test_q_90/indicators", json={"code": "bad", "name_en": "Bad rule here", "lr_present": 2, "lr_absent": 0.5, "rule": {"type": "nope"}})
    assert bad.status_code == 400
    pv = client.post("/api/indicators/preview", json={"rule": {"type": "series_threshold", "series": "hormuz_transits", "op": "<=", "value": 20, "lookback_days": 30}, "as_of": "2026-10-11"}).json()
    assert pv["state"] in ("present", "absent") and len(pv["history"]) == 6
    ind_id = q["indicators"][0]["id"]
    assert client.put(f"/api/indicators/{ind_id}", json={"lr_present": 4.0}).json()["lr_present"] == 4.0
    assert client.put("/api/questions/test_q_90", json={"base_rate": 0.25}).json()["base_rate"] == 0.25
    p = client.post("/api/questions/test_q_90/panel", json={"probability": 0.4, "rationale": "test", "as_of": "2026-10-18"})
    assert p.status_code == 201
    panel = client.get("/api/questions/test_q_90/panel").json()
    assert panel["mine"]["probability"] == 0.4 and panel["latest"]
    c = client.post("/api/forecasts/commit", json={"as_of": "2026-10-18"}).json()
    assert any(x["question"] == "test_q_90" for x in c["committed"])
    e = client.post("/api/events", json={"event_date": "2026-10-17", "event_type": "maritime_attack", "description_en": "Analyst-entered test attack on a tanker.", "country": "OM", "severity": 4, "source": "analyst test", "grade": "B2"})
    assert e.status_code == 201 and e.json()["verification"] == "verified"
    o = client.post("/api/observations", json={"actor": "IR", "issue": "hormuz_posture", "observed_at": "2026-10-17", "track": "stated", "score": 0.5, "text_excerpt": "Test statement about the strait.", "source": "analyst test"})
    assert o.status_code == 201
    sp = client.post("/api/series", json={"series": "war_risk_premium_hormuz_pct", "date": "2026-10-18", "value": 7.25, "unit": "pct_hull", "source": "broker quote"})
    assert sp.status_code == 201
    t = client.post("/api/tasking", json={"text": "How likely is a test?"}).json()
    assert client.post(f"/api/tasking/{t['id']}/frame", json={"question_code": "test_q_90"}).json()["status"] == "framed"
    assert client.post(f"/api/tasking/{t['id']}/answer", json={"answer_md": "## Answer\nAbout 40 percent."}).json()["status"] == "answered"
    res = client.post("/api/questions/test_q_90/resolve", json={"outcome": True, "notes": "test resolved", "resolved_at": "2026-10-18"})
    assert res.status_code == 200 and res.json()["status"] == "resolved"
    assert client.put("/api/questions/test_q_90", json={"base_rate": 0.3}).status_code == 409
    cal = client.get("/api/calibration").json()
    assert any(x["code"] == "test_q_90" for x in cal["resolved"])


def test_daily_alerts_changes_search_docx(client):
    scan = client.post("/api/alerts/scan").json()
    assert "raised" in scan
    al = client.get("/api/alerts").json()
    assert isinstance(al, list)
    ch = client.get("/api/changes?since=2026-10-01").json()
    assert ch["since"] == "2026-10-01" and "moves" in ch and "events" in ch
    s = client.get("/api/search?q=Hormuz&days=400").json()
    assert s["events"] or s["documents"] or s["observations"]
    docs = client.get("/api/questions/hormuz_closure_90/documents?days=3650").json()
    assert "terms" in docs and "hormuz" in docs["terms"]
    r = client.get("/api/briefs/hormuz_closure_90/docx?lang=en&as_of=2026-10-18&polish=false")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats") and len(r.content) > 5000
    r2 = client.get("/api/briefs/hormuz_closure_90/docx?lang=ar&as_of=2026-10-18&polish=false")
    assert r2.status_code == 200
    if al:
        a = client.post(f"/api/alerts/{al[0]['id']}/ack").json()
        assert a["acknowledged_by"]
    assert client.post("/api/alerts/ack-all").json()["acknowledged"] >= 0
    st = client.get("/api/status").json()
    assert "open_alerts" in st and "marking" in st


def test_admin_licence_keys_settings_exports(admin_client, client):
    lic = admin_client.get("/api/licence").json()
    assert lic["mode"] in ("evaluation", "licensed", "grace") and "seats_used" in lic
    bad = admin_client.post("/api/licence", json={"document": {"payload": {"licensee": "x"}, "signature": "AAAA"}})
    assert bad.status_code == 400
    k = admin_client.post("/api/keys", json={"name": "bi-tool", "role": "viewer"})
    assert k.status_code == 201 and k.json()["token"].startswith("rsk_")
    token = k.json()["token"]
    from fastapi.testclient import TestClient

    from rasad.api.app import app

    anon = TestClient(app)
    assert anon.get("/api/status").status_code == 401
    r = anon.get("/api/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["licence"]["mode"] in ("evaluation", "licensed", "grace")
    assert anon.post("/api/alerts/ack-all", headers={"Authorization": f"Bearer {token}"}).status_code == 403  # viewer key
    assert admin_client.delete(f"/api/keys/{k.json()['id']}").json()["revoked_at"]
    assert anon.get("/api/status", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    st = admin_client.put("/api/settings", json={"values": {"org_name": "Test Org", "marking": "RESTRICTED"}}).json()
    assert st["org_name"] == "Test Org" and st["marking"] == "RESTRICTED"
    assert client.get("/api/status").json()["marking"] == "RESTRICTED"
    assert admin_client.put("/api/settings", json={"values": {"nope": "x"}}).status_code == 400
    for path in ("/api/export/events.csv?days=400", "/api/export/observations.csv", "/api/export/series.csv?name=hormuz_transits", "/api/export/forecasts.csv"):
        r = client.get(path)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv"), path
    assert client.get("/api/export/forecasts.json").json()


def test_csrf_header_required(users):
    from fastapi.testclient import TestClient

    from rasad.api.app import app

    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": "ana", "password": users["ana"]}).status_code == 200
    assert c.get("/api/status").status_code == 200
    assert c.post("/api/alerts/scan", json={}).status_code == 403
    assert c.post("/api/alerts/scan", json={}, headers={"X-Rasad-Client": "web"}).status_code == 200


def test_sources_freshness_series_index_and_bulk_verify(client):
    src = client.get("/api/sources").json()
    assert src and all("documents" in s and "last_fetched" in s for s in src)
    idx = client.get("/api/series").json()
    assert any(r["series"] == "hormuz_transits" and r["points"] > 500 and r["synthetic"] == 0 for r in idx)
    q = client.get("/api/verification/queue").json()
    ids = [e["id"] for e in q["events"][:3]]
    if ids:
        r = client.post("/api/verification/bulk", json={"kind": "event", "ids": ids, "decision": "verified"}).json()
        assert r["n"] == len(ids)
    assert client.post("/api/verification/bulk", json={"kind": "event", "ids": [], "decision": "maybe"}).status_code == 400
