"""OFAC SDN list (CSV) and UK Sanctions List (CSV).

Two uses. First, designations with a Gulf address become `designation` events in the threat
ledger (they resolve the sanctions question and feed the shadow-fleet picture). Second, every
Iran-programme designation is a revealed-action observation of US (or UK) enforcement posture
in the policy ledger, graded A1 because the list is the authority.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Actor, Issue, PolicyObservation, ThreatEvent
from .base import fetch_text

GULF_HINTS = {
    "AE": ("united arab emirates", "dubai", "abu dhabi", "sharjah", "ajman", "fujairah", "ras al khaimah", "u.a.e", "uae"),
    "QA": ("qatar", "doha"),
    "SA": ("saudi arabia", "riyadh", "jeddah", "dammam"),
    "KW": ("kuwait",),
    "BH": ("bahrain", "manama"),
    "OM": ("oman", "muscat"),
}
IRAN_PROGRAMMES = ("IRAN", "IFSR", "IRGC", "NPWMD", "SDGT")


def _gulf_country(text: str) -> str | None:
    t = text.lower()
    for code, hints in GULF_HINTS.items():
        if any(h in t for h in hints):
            return code
    return None


def parse_ofac_sdn_csv(sdn_text: str, add_text: str | None = None) -> list[dict]:
    """sdn.csv has no header: ent_num, name, type, program, title, call_sign, vess_type, tonnage,
    grt, vess_flag, vess_owner, remarks. add.csv: ent_num, add_num, address, city, country, add_remarks."""
    addresses: dict[str, list[str]] = {}
    if add_text:
        for row in csv.reader(io.StringIO(add_text)):
            if len(row) >= 5:
                addresses.setdefault(row[0], []).append(" ".join(x for x in row[2:5] if x and x != "-0-"))
    out = []
    for row in csv.reader(io.StringIO(sdn_text)):
        if len(row) < 4:
            continue
        ent, name, typ, program = row[0], row[1], row[2], row[3]
        remarks = row[11] if len(row) > 11 else ""
        addr = " | ".join(addresses.get(ent, []))
        gulf = _gulf_country(addr + " " + remarks)
        out.append({"ent_num": ent, "name": name, "type": typ, "program": program, "remarks": remarks, "address": addr, "gulf_country": gulf, "iran_related": any(p in program.upper() for p in IRAN_PROGRAMMES)})
    return out


def ingest_designations(db: Session, rows: list[dict], listed_on: date, *, authority: str = "US", url: str = "") -> int:
    actor_code = "US" if authority == "US" else "UK"
    actor = db.scalar(select(Actor).where(Actor.code == actor_code))
    issue = db.scalar(select(Issue).where(Issue.code == "sanctions_enforcement_iran"))
    n = 0
    for r in rows:
        if r["gulf_country"]:
            desc = f"{authority} designation of {r['name']} ({r['type'] or 'entity'}) under {r['program']} with a {r['gulf_country']} address."
            exists = db.scalar(select(ThreatEvent).where(ThreatEvent.event_type == "designation", ThreatEvent.description_en == desc))
            if not exists:
                db.add(ThreatEvent(event_date=listed_on, event_type="designation", location_name=r["address"][:200] or None, country=r["gulf_country"], severity=2, description_en=desc, provenance={"source": f"{authority} sanctions list", "url": url, "grade": "A1"}, verification="verified", verified_by="source"))
                n += 1
    iran_count = sum(1 for r in rows if r["iran_related"])
    if actor and issue and iran_count:
        db.add(PolicyObservation(
            actor_id=actor.id, issue_id=issue.id, observed_at=listed_on, track="revealed", channel="event", cost_class="revealed_action",
            speaker_level="institution", language="en", score=min(1.0, 0.3 + 0.05 * iran_count), source_grade="A1", model_confidence=1.0,
            text_excerpt=f"{iran_count} Iran-related designations on the {authority} list as of {listed_on.isoformat()}.",
            provenance={"source": f"{authority} sanctions list", "url": url, "grade": "A1"}, verification="verified", verified_by="source",
        ))
    db.commit()
    return n


def fetch_and_ingest_ofac(db: Session, sdn_url: str, add_url: str | None, listed_on: date) -> int:
    sdn = fetch_text(sdn_url)
    add = fetch_text(add_url) if add_url else None
    return ingest_designations(db, parse_ofac_sdn_csv(sdn, add), listed_on, authority="US", url=sdn_url)
