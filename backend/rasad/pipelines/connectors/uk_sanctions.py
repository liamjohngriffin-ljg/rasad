"""UK Sanctions List (gov.uk, Open Government Licence v3).

Reads the published CSV, files designations with a Gulf address as `designation` events and
counts Iran-regime designations as a revealed-action observation of UK enforcement posture.
The list is the authority, so rows are verified by source.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Actor, Issue, PolicyObservation, SeriesPoint, ThreatEvent
from .base import fetch_text
from .sanctions import GULF_HINTS

PUBLICATION_PAGE = "https://www.gov.uk/government/publications/the-uk-sanctions-list"
CSV_URL = "https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.csv"


def discover_csv_url() -> str | None:
    try:
        html = fetch_text(PUBLICATION_PAGE, timeout=60)
    except Exception:  # noqa: BLE001
        return CSV_URL
    m = re.search(r'href="(https://sanctionslist\.fcdo\.gov\.uk/docs/UK-Sanctions-List\.csv)"', html)
    return m.group(1) if m else CSV_URL


def _gulf(text: str) -> str | None:
    t = text.lower()
    for code, hints in GULF_HINTS.items():
        if any(h in t for h in hints):
            return code
    return None


def parse_csv(text: str) -> list[dict]:
    """One record per designation (the file repeats a designation once per alias and address)."""
    reader = csv.reader(io.StringIO(text.lstrip("\ufeff")))
    header = None
    seen: dict[str, dict] = {}
    for row in reader:
        if header is None:
            if "Unique ID" in row and "Regime Name" in row:
                header = row
            continue
        rec = dict(zip(header, row))
        uid = rec.get("Unique ID") or ""
        if not uid:
            continue
        regime = rec.get("Regime Name") or ""
        name = " ".join(x for x in [rec.get("Name 6", ""), rec.get("Name 1", ""), rec.get("Name 2", ""), rec.get("Name 3", "")] if x).strip()
        country = rec.get("Address Country") or ""
        gulf = _gulf(country + " " + " ".join(rec.get(f"Address Line {i}", "") for i in range(1, 7)))
        item = seen.setdefault(uid, {"uid": uid, "name": name, "regime": regime, "address": country, "gulf_country": None, "iran_related": "iran" in regime.lower(), "listed_on": rec.get("Date Designated") or "", "is_ship": bool(rec.get("IMO number")), "ship_flag": rec.get("Current believed flag of ship") or ""})
        if gulf and not item["gulf_country"]:
            item["gulf_country"] = gulf
            item["address"] = country
        if rec.get("Name type") == "Primary Name" and name:
            item["name"] = name
    return list(seen.values())


def _parse_listed(s: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def ingest(db: Session, rows: list[dict], listed_on: date, url: str = "") -> int:
    uk = db.scalar(select(Actor).where(Actor.code == "UK"))
    issue = db.scalar(select(Issue).where(Issue.code == "sanctions_enforcement_iran"))
    n = 0
    iran_ships = sum(1 for r in rows if r["iran_related"] and r["is_ship"])
    existing = db.scalar(select(SeriesPoint).where(SeriesPoint.series == "uk_designated_vessels_iran", SeriesPoint.date == listed_on))
    if existing:
        existing.value, existing.is_synthetic = iran_ships, False
    else:
        db.add(SeriesPoint(series="uk_designated_vessels_iran", date=listed_on, value=iran_ships, unit="count", source="UK Sanctions List", is_synthetic=False))
    for r in rows:
        if not r["gulf_country"]:
            continue
        designated = _parse_listed(r.get("listed_on", "")) or listed_on
        if (listed_on - designated).days > 400:
            continue  # the ledger carries recent designations; the full list stays in the raw cache
        desc = f"UK designation of {r['name']} under the {r['regime']} regime with a {r['gulf_country']} address."
        if db.scalar(select(ThreatEvent).where(ThreatEvent.event_type == "designation", ThreatEvent.description_en == desc)):
            continue
        db.add(ThreatEvent(event_date=designated, event_type="designation", country=r["gulf_country"], severity=2, description_en=desc, provenance={"source": "UK Sanctions List", "url": url, "grade": "A1", "uid": r["uid"]}, verification="verified", verified_by="source"))
        n += 1
    iran = sum(1 for r in rows if r["iran_related"])
    if uk and issue and iran:
        db.add(PolicyObservation(actor_id=uk.id, issue_id=issue.id, observed_at=listed_on, track="revealed", channel="event", cost_class="revealed_action", speaker_level="institution", language="en", score=min(1.0, 0.3 + iran / 400), source_grade="A1", model_confidence=1.0, text_excerpt=f"{iran} Iran-regime designations on the UK Sanctions List as of {listed_on.isoformat()}.", provenance={"source": "UK Sanctions List", "url": url, "grade": "A1"}, verification="verified", verified_by="source"))
    db.commit()
    return n


def fetch_and_ingest(db: Session) -> int:
    url = discover_csv_url()
    if not url:
        return 0
    return ingest(db, parse_csv(fetch_text(url, timeout=120)), date.today(), url)
