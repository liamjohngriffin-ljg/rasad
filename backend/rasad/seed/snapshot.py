"""Seed snapshot: real ledger rows exported from a live database and shipped with the code.

`export` writes series points, events and policy observations that came from connectors
(is_synthetic false, provenance from a source) to rasad/seed/data/snapshot.json. `load`
reads them back during seeding so a fresh install starts with the sourced record rather
than synthetic placeholders. Events keep their verification state; those an analyst has not
yet accepted stay `pending` in the new database too.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Actor, Issue, PolicyObservation, SeriesPoint, ThreatEvent

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "data", "snapshot.json")
# series the snapshot carries; everything else in the series table is either synthetic demo
# shaping or operator-specific
SERIES_PREFIXES = ("hormuz_", "bab_el_mandeb_", "suez_", "cape_of_good_hope_", "jmic_", "uk_designated_", "ofac_", "jwc_", "war_risk_")


def export(db: Session, path: str | None = None) -> dict:
    path = path or DEFAULT_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    series = [
        {"s": p.series, "d": p.date.isoformat(), "v": p.value, "u": p.unit, "src": p.source}
        for p in db.scalars(select(SeriesPoint).where(SeriesPoint.is_synthetic.is_(False)).order_by(SeriesPoint.series, SeriesPoint.date))
        if p.series.startswith(SERIES_PREFIXES)
    ]
    actors = {a.id: a.code for a in db.scalars(select(Actor))}
    issues = {i.id: i.code for i in db.scalars(select(Issue))}
    events = []
    for e in db.scalars(select(ThreatEvent).where(ThreatEvent.is_synthetic.is_(False)).order_by(ThreatEvent.event_date, ThreatEvent.id)):
        prov = e.provenance or {}
        if prov.get("source", "").startswith("demo") or prov.get("provider"):
            continue  # model or rules extractions from wires are not shipped; connectors and curated rows are
        events.append({
            "date": e.event_date.isoformat(), "type": e.event_type, "loc": e.location_name, "country": e.country,
            "lat": e.lat, "lon": e.lon, "actor": actors.get(e.actor_id), "target": actors.get(e.target_actor_id),
            "fatalities": e.fatalities, "severity": e.severity, "desc": e.description_en, "prov": e.provenance or {},
            "verification": e.verification, "verified_by": e.verified_by,
        })
    observations = []
    for o in db.scalars(select(PolicyObservation).where(PolicyObservation.is_synthetic.is_(False)).order_by(PolicyObservation.observed_at, PolicyObservation.id)):
        if o.actor_id not in actors or o.issue_id not in issues or (o.provenance or {}).get("provider"):
            continue
        observations.append({
            "date": o.observed_at.isoformat(), "actor": actors[o.actor_id], "issue": issues[o.issue_id], "track": o.track, "channel": o.channel,
            "cost": o.cost_class, "level": o.speaker_level, "lang": o.language, "score": o.score, "grade": o.source_grade,
            "confidence": o.model_confidence, "excerpt": o.text_excerpt, "excerpt_en": o.text_excerpt_en, "prov": o.provenance or {},
            "verification": o.verification, "verified_by": o.verified_by,
        })
    payload = {"exported_at": datetime.utcnow().isoformat(timespec="seconds"), "series": series, "events": events, "observations": observations}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    return {"path": path, "series": len(series), "events": len(events), "observations": len(observations)}


def available(path: str | None = None) -> bool:
    return os.path.exists(path or DEFAULT_PATH)


def load(db: Session, path: str | None = None, *, include_series: bool = True, include_events: bool = True, include_observations: bool = True) -> dict:
    path = path or DEFAULT_PATH
    if not os.path.exists(path):
        return {"series": 0, "events": 0, "observations": 0}
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    actors = {a.code: a.id for a in db.scalars(select(Actor))}
    issues = {i.code: i.id for i in db.scalars(select(Issue))}
    existing = {(s, d) for s, d in db.execute(select(SeriesPoint.series, SeriesPoint.date))}
    n_series = 0
    for row in payload.get("series", []) if include_series else []:
        d = date.fromisoformat(row["d"])
        if (row["s"], d) in existing:
            continue
        db.add(SeriesPoint(series=row["s"], date=d, value=row["v"], unit=row["u"], source=row["src"], is_synthetic=False))
        existing.add((row["s"], d))
        n_series += 1
    seen_desc = {(e.event_type, e.description_en) for e in db.scalars(select(ThreatEvent))}
    n_events = 0
    for e in payload.get("events", []) if include_events else []:
        key = (e["type"], e["desc"])
        if key in seen_desc:
            continue
        seen_desc.add(key)
        db.add(ThreatEvent(
            event_date=date.fromisoformat(e["date"]), event_type=e["type"], location_name=e.get("loc"), country=e.get("country"),
            lat=e.get("lat"), lon=e.get("lon"), actor_id=actors.get(e.get("actor") or ""), target_actor_id=actors.get(e.get("target") or ""),
            fatalities=e.get("fatalities"), severity=e.get("severity") or 2, description_en=e["desc"], provenance=e.get("prov") or {},
            verification=e.get("verification") or "pending", verified_by=e.get("verified_by"), is_synthetic=False,
        ))
        n_events += 1
    n_obs = 0
    seen_obs = {(o.actor_id, o.issue_id, o.observed_at, o.text_excerpt) for o in db.scalars(select(PolicyObservation))}
    for o in payload.get("observations", []) if include_observations else []:
        if o["actor"] not in actors or o["issue"] not in issues:
            continue
        key = (actors[o["actor"]], issues[o["issue"]], date.fromisoformat(o["date"]), o.get("excerpt"))
        if key in seen_obs:
            continue
        seen_obs.add(key)
        db.add(PolicyObservation(
            actor_id=actors[o["actor"]], issue_id=issues[o["issue"]], observed_at=date.fromisoformat(o["date"]), track=o["track"], channel=o["channel"],
            cost_class=o["cost"], speaker_level=o["level"], language=o["lang"], score=o["score"], source_grade=o["grade"],
            model_confidence=o.get("confidence") or 1.0, text_excerpt=o.get("excerpt"), text_excerpt_en=o.get("excerpt_en"), provenance=o.get("prov") or {},
            verification=o.get("verification") or "pending", verified_by=o.get("verified_by"), is_synthetic=False,
        ))
        n_obs += 1
    db.commit()
    return {"series": n_series, "events": n_events, "observations": n_obs}
