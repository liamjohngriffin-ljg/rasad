from datetime import date

from rasad.engine import incidents
from rasad.engine.indicators import _event_count
from rasad.models import ThreatEvent

D = date(2023, 6, 14)  # before the seeded record, so only the rows below are in play


def _ev(db, src, desc, *, d=D, country="AE", et="maritime_attack", grade="A2"):
    e = ThreatEvent(event_date=d, event_type=et, country=country, severity=4, description_en=desc,
                    provenance={"source": src, "grade": grade}, verification="pending", is_synthetic=False)
    db.add(e)
    db.flush()
    return e


def test_anchor_parsing():
    assert incidents.anchor("an incident 24NM northwest of Port Rashid, UAE.") == (24.0, "port rashid")
    assert incidents.anchor("approximately 28NM southeast of Al-Faw, Iraq") == (28.0, "al faw")
    assert incidents.anchor("within the Strait of Hormuz") is None


def test_linking_counts_incidents_once_and_respects_analysts(db, client):
    a = _ev(db, "UKMTO ATTACK 901-26", "UKMTO has received a report of an incident 17NM east of Zirku, UAE. A tanker was struck.")
    b = _ev(db, "MSCIO Atalanta weekly report", "MSCIO alert 901/26: attack approximately 17NM east of Zirku. Tanker struck by a projectile.", grade="B2")
    c = _ev(db, "JMIC advisory note", "Attack on a tanker 40NM north of Zirku; no damage.")  # different anchor: a different incident
    d = _ev(db, "UKMTO ATTACK 902-26", "UKMTO has received a report of an incident in the Gulf of Oman.", country="OM")
    e = _ev(db, "MSCIO Atalanta weekly report", "MSCIO alert 902/26: reported attack on a bulk carrier in the Gulf of Oman.", country="OM")
    p = _ev(db, "Wikipedia", "Ports on the Gulf of Oman struck repeatedly.", country="OM", et="missile_strike")  # campaign row: not linked
    db.commit()
    r = incidents.link(db, since=D, until=D)
    assert r["incidents"] == 2
    for x in (a, b, c, d, e, p):
        db.refresh(x)
    assert a.incident_id == b.incident_id == a.id and a.incident_link == "anchored"  # grade A beats B
    assert c.incident_id is None and p.incident_id is None
    assert d.incident_id == e.incident_id and d.incident_link == "probable"

    st = _event_count(db, {"type": "event_count", "window_days": 1, "event_types": ["maritime_attack"], "countries": ["AE", "OM"]}, D)
    assert st.evidence["reports"] == 5 and st.evidence["count"] == 3

    # the queue shows one item per incident and one decision covers every report
    q = client.get("/api/verification/queue").json()
    item = next(i for i in q["events"] if i["id"] == a.id)
    assert [o["id"] for o in item["other_reports"]] == [b.id]
    assert not any(i["id"] == b.id for i in q["events"])
    res = client.post(f"/api/verification/event/{a.id}", json={"decision": "verified"}).json()
    assert sorted(res["applied_to"]) == sorted([a.id, b.id])

    # an analyst detaches a report: it stands alone and automatic linking leaves it alone
    client.post(f"/api/events/{e.id}/incident", json={"to": None})
    incidents.link(db, since=D, until=D)
    db.refresh(d), db.refresh(e)
    assert e.incident_link == "detached" and e.incident_id is None and d.incident_id is None
    # and links by hand
    client.post(f"/api/events/{c.id}/incident", json={"to": a.id})
    db.refresh(c)
    assert c.incident_id == a.id and c.incident_link == "manual"
