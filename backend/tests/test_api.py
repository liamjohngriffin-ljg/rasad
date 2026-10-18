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
