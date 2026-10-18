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
