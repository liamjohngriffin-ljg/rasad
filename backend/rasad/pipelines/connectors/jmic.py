"""JMIC weekly Middle East dashboard (CMF / MSCIO).

The dashboard carries a threat level per area (LOW, MODERATE, SUBSTANTIAL, SEVERE, CRITICAL)
and warnings such as mines. The parser writes one series point per area and week and files a
`mine_warning` event when the text carries one.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import SeriesPoint, ThreatEvent
from .base import RawDoc, fetch_bytes, upsert_document

SOURCE = "jmic"
LEVELS = {"LOW": 1, "MODERATE": 2, "SUBSTANTIAL": 3, "SEVERE": 4, "CRITICAL": 5}
AREAS = {
    "arabian_gulf": re.compile(r"(arabian gulf|persian gulf)[^.\n]{0,80}?\b(LOW|MODERATE|SUBSTANTIAL|SEVERE|CRITICAL)\b", re.I),
    "hormuz": re.compile(r"(strait of hormuz|hormuz)[^.\n]{0,80}?\b(LOW|MODERATE|SUBSTANTIAL|SEVERE|CRITICAL)\b", re.I),
    "gulf_of_oman": re.compile(r"(gulf of oman)[^.\n]{0,80}?\b(LOW|MODERATE|SUBSTANTIAL|SEVERE|CRITICAL)\b", re.I),
    "red_sea": re.compile(r"(red sea)[^.\n]{0,80}?\b(LOW|MODERATE|SUBSTANTIAL|SEVERE|CRITICAL)\b", re.I),
    "bab_al_mandab": re.compile(r"(bab[- ]?al[- ]?mandab|bab el[- ]?mandeb)[^.\n]{0,80}?\b(LOW|MODERATE|SUBSTANTIAL|SEVERE|CRITICAL)\b", re.I),
    "gulf_of_aden": re.compile(r"(gulf of aden)[^.\n]{0,80}?\b(LOW|MODERATE|SUBSTANTIAL|SEVERE|CRITICAL)\b", re.I),
}
WEEK_RE = re.compile(r"week\s*(\d{1,2})\b[^\n]*?(\d{1,2})\s*(?:-|to|–)\s*(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(20\d{2})", re.I)
MINE_RE = re.compile(r"\bmine(s|field|\s+warning|\s+threat)?\b", re.I)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def parse_dashboard(text: str) -> dict:
    wm = WEEK_RE.search(text)
    week_end = None
    if wm:
        week_end = date(int(wm.group(5)), MONTHS[wm.group(4).lower()[:3]], int(wm.group(3)))
    levels = {}
    for area, rx in AREAS.items():
        m = rx.search(text)
        if m:
            levels[area] = LEVELS[m.group(2).upper()]
    return {"week": int(wm.group(1)) if wm else None, "week_end": week_end, "levels": levels, "mine_warning": bool(MINE_RE.search(text))}


def ingest_text(db: Session, text: str, *, external_id: str, url: str | None = None) -> dict:
    doc, created = upsert_document(db, RawDoc(SOURCE, external_id, text, url=url))
    parsed = parse_dashboard(text)
    if parsed["week_end"] is None:
        return parsed
    d = parsed["week_end"]
    for area, level in parsed["levels"].items():
        series = f"jmic_threat_level_{area}"
        existing = db.scalar(select(SeriesPoint).where(SeriesPoint.series == series, SeriesPoint.date == d))
        if existing:
            existing.value, existing.is_synthetic = level, False
        else:
            db.add(SeriesPoint(series=series, date=d, value=level, unit="level_1_to_5", source=f"JMIC week {parsed['week']}", is_synthetic=False))
    if created and parsed["mine_warning"]:
        db.add(ThreatEvent(
            event_date=d - timedelta(days=3), event_type="mine_warning", location_name="JMIC area of operations", country="HORMUZ", severity=4,
            description_en=f"JMIC week {parsed['week']} dashboard carries a mine warning.", source_doc_id=doc.id,
            provenance={"source": f"JMIC week {parsed['week']} dashboard", "url": url or "", "grade": "A2"},
            verification="pending",
        ))
    db.commit()
    return parsed


def fetch_and_ingest(db: Session, url: str) -> dict:
    import io

    import pdfplumber

    data = fetch_bytes(url)
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    return ingest_text(db, text, external_id=url.rsplit("/", 1)[-1], url=url)
