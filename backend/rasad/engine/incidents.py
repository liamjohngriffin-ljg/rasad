"""Cross-source incident linking.

UKMTO, JMIC and the MSCIO / EUNAVFOR Atalanta weekly report each publish their own record of the
same attack on a ship. Counted as separate rows they inflate every event-count indicator. This
module links reports of one real-world incident: each report keeps its row and provenance, and
all of them carry `incident_id` = the id of the canonical report, so indicators count incidents
and analysts verify an incident once.

Two reports from different publishers are linked when their dates are within a day, their event
types are compatible, their area or country agree, and either

  - both carry the same position anchor ("24NM north-west of Port Rashid"): link = anchored, or
  - they fall on the same date, neither anchor contradicts the other, and each is the only
    candidate the other publisher has for that date, area and type: link = probable.

Analyst decisions stand: a report marked `detached` is never relinked, and `manual` links are
kept. The canonical report is the one with the best source grade, then the earliest date, then
the lowest id (the first report in).
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ThreatEvent

KINETIC = {"maritime_attack", "missile_strike", "drone_strike", "mine_warning"}
LINKABLE = KINETIC | {"seizure", "maritime_harassment", "gnss_interference"}
# publishers that report single incidents; curated rows from press or reference works often summarise
# a campaign ("ports struck repeatedly from 1 March") and are linked only by hand
REPORTERS = {"UKMTO", "MSCIO", "JMIC", "EUNAVFOR", "MARAD", "CMF"}

_ANCHOR = re.compile(r"(\d{1,3}(?:\.\d)?)\s*(?:NM|nm|nautical miles)\s+[A-Za-z\- ]{0,24}?\bof\s+((?:Al[- ])?[A-Z][A-Za-z'\-]+(?:\s[A-Z][A-Za-z'\-]+)?)")


def anchor(text: str | None) -> tuple[float, str] | None:
    """(distance in nautical miles, place) from the first position anchor in a report."""
    if not text:
        return None
    m = _ANCHOR.search(text)
    if not m:
        return None
    place = m.group(2).lower().replace("al-", "al ").strip()
    place = re.sub(r"[^a-z ]", "", place).strip()
    return float(m.group(1)), place


def publisher(e: ThreatEvent) -> str:
    src = str((e.provenance or {}).get("source") or "").strip()
    return (src.split(" ", 1)[0] or "OTHER").upper().rstrip(",")


def _compatible(a: str, b: str) -> bool:
    return a == b or (a in KINETIC and b in KINETIC)


def _grade_rank(e: ThreatEvent) -> int:
    g = str((e.provenance or {}).get("grade") or "C3")[:1].upper()
    return "ABCDEF".find(g) if g in "ABCDEF" else 9


def _anchors_agree(a: tuple[float, str] | None, b: tuple[float, str] | None) -> bool | None:
    """True when both anchors exist and match, False when both exist and differ, None otherwise."""
    if a is None or b is None:
        return None
    return abs(a[0] - b[0]) <= 2 and (a[1] == b[1] or a[1].startswith(b[1]) or b[1].startswith(a[1]))


def link(db: Session, *, since: date | None = None, until: date | None = None) -> dict:
    since = since or date.today() - timedelta(days=150)
    until = until or date.today() + timedelta(days=1)
    rows = db.scalars(
        select(ThreatEvent).where(
            ThreatEvent.event_date >= since - timedelta(days=1), ThreatEvent.event_date <= until,
            ThreatEvent.is_synthetic.is_(False), ThreatEvent.verification != "rejected", ThreatEvent.event_type.in_(LINKABLE),
        ).order_by(ThreatEvent.event_date, ThreatEvent.id)
    ).all()
    rows = [r for r in rows if r.incident_link != "detached" and publisher(r) in REPORTERS]
    by_id = {r.id: r for r in rows}
    pub = {r.id: publisher(r) for r in rows}
    anc = {r.id: anchor(r.description_en) for r in rows}

    # candidate pairs across publishers
    by_day: dict[date, list[ThreatEvent]] = defaultdict(list)
    for r in rows:
        by_day[r.event_date].append(r)
    cands: dict[int, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        for d in (r.event_date - timedelta(days=1), r.event_date, r.event_date + timedelta(days=1)):
            for o in by_day.get(d, []):
                if o.id == r.id or pub[o.id] == pub[r.id] or not _compatible(r.event_type, o.event_type):
                    continue
                if (r.country or "") != (o.country or ""):
                    continue
                if _anchors_agree(anc[r.id], anc[o.id]) is False:
                    continue
                cands[r.id][pub[o.id]].append(o.id)

    parent = {r.id: r.id for r in rows}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    kind: dict[tuple[int, int], str] = {}
    for rid, per_pub in cands.items():
        for p, others in per_pub.items():
            for oid in others:
                agree = _anchors_agree(anc[rid], anc[oid])
                if agree:
                    k = "anchored"
                elif (
                    by_id[rid].event_date == by_id[oid].event_date
                    and others == [oid]
                    and cands[oid].get(pub[rid]) == [rid]
                ):
                    k = "probable"  # same day, same area, and each is the other publisher's only candidate
                else:
                    continue
                a, b = find(rid), find(oid)
                if a != b:
                    parent[a] = b
                kind[(min(rid, oid), max(rid, oid))] = k

    groups: dict[int, list[ThreatEvent]] = defaultdict(list)
    for r in rows:
        groups[find(r.id)].append(r)
    changed = linked = 0
    for members in groups.values():
        if len(members) < 2:
            # a report that lost its partners (a partner was rejected or detached) stands alone again
            only = members[0]
            if only.incident_id is not None and only.incident_link != "manual":
                only.incident_id, only.incident_link = None, None
                changed += 1
            continue
        canon = sorted(members, key=lambda e: (_grade_rank(e), e.event_date, e.id))[0]
        ids = {m.id for m in members}
        strong = any(v == "anchored" for (x, y), v in kind.items() if x in ids and y in ids)
        label = "anchored" if strong else "probable"
        for m in members:
            if m.incident_link == "manual":
                continue
            if m.incident_id != canon.id or m.incident_link != label:
                m.incident_id, m.incident_link = canon.id, label
                changed += 1
        linked += len(members)
    db.commit()
    return {"reports_linked": linked, "incidents": sum(1 for g in groups.values() if len(g) > 1), "changed": changed}


def members(db: Session, e: ThreatEvent) -> list[ThreatEvent]:
    if not e.incident_id:
        return [e]
    return db.scalars(select(ThreatEvent).where(ThreatEvent.incident_id == e.incident_id).order_by(ThreatEvent.id)).all()


def incident_key(e: ThreatEvent) -> int:
    return e.incident_id or e.id
