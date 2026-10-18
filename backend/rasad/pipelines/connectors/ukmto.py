"""UKMTO advisories and incident reports.

The PDFs are unstructured prose. The parser pulls the advisory number, date, position and a
typed event from the headline vocabulary UKMTO uses (explosion, attack, boarding, suspicious
approach, hijack, UAV, GPS interference). Everything it produces is `pending` until an analyst
accepts it; the ledger of record is the verified set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from ...models import ThreatEvent
from .base import RawDoc, fetch_bytes, upsert_document

SOURCE = "ukmto"

TYPE_MAP = [
    (re.compile(r"\b(explosion|struck by|projectile|missile|hit by)\b", re.I), "maritime_attack", 4),
    (re.compile(r"\b(attack|attacked|fired upon|uav|drone)\b", re.I), "maritime_attack", 4),
    (re.compile(r"\b(boarded|boarding|hijack|seized|seizure|detained)\b", re.I), "seizure", 4),
    (re.compile(r"\b(suspicious approach|approached by|small craft|skiff|harass)\b", re.I), "maritime_harassment", 2),
    (re.compile(r"\b(gps|gnss|jamming|spoofing|electronic interference)\b", re.I), "gnss_interference", 2),
    (re.compile(r"\b(mine|mines)\b", re.I), "mine_warning", 4),
]

ADVISORY_RE = re.compile(r"advisory\s*(\d{3})[-/](\d{2})", re.I)
DATE_RE = re.compile(r"(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(20\d{2})", re.I)
ISO_DATE_RE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")
POS_RE = re.compile(r"(\d{1,2})[°\s](\d{1,2}(?:\.\d+)?)['’]?\s*([NS])[,\s]+(\d{1,3})[°\s](\d{1,2}(?:\.\d+)?)['’]?\s*([EW])", re.I)
NM_RE = re.compile(r"(\d{1,4})\s*nm\s+(?:[NSEW]{1,3}\s+)?(?:of|from)\s+([A-Z][A-Za-z' ]{2,40})")

AREAS = [
    (re.compile(r"\b(hormuz|strait of hormuz|bandar|fujairah|khor fakkan)\b", re.I), "HORMUZ"),
    (re.compile(r"\b(red sea|bab[- ]?al[- ]?mandab|bab el[- ]?mandeb|hodeidah|hudaydah|mokha|eilat|jeddah|yanbu)\b", re.I), "RED_SEA"),
    (re.compile(r"\b(gulf of aden|aden|socotra|somali|somalia)\b", re.I), "GULF_OF_ADEN"),
    (re.compile(r"\b(gulf of oman|muscat|sohar|duqm|salalah)\b", re.I), "OM"),
    (re.compile(r"\b(abu dhabi|dubai|ras al khaimah|ajman|sharjah)\b", re.I), "AE"),
    (re.compile(r"\b(doha|ras laffan|mesaieed)\b", re.I), "QA"),
    (re.compile(r"\b(ras tanura|jubail|dammam|al ahsa)\b", re.I), "SA"),
    (re.compile(r"\b(kuwait|shuwaikh|shuaiba)\b", re.I), "KW"),
    (re.compile(r"\b(bahrain|manama|mina salman)\b", re.I), "BH"),
]

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


@dataclass
class ParsedAdvisory:
    advisory_no: str | None
    event_date: date | None
    event_type: str | None
    severity: int
    area: str | None
    lat: float | None
    lon: float | None
    summary: str


def _dms(deg: str, minutes: str, hemi: str) -> float:
    v = float(deg) + float(minutes) / 60
    return -v if hemi.upper() in ("S", "W") else v


def parse_advisory(text: str) -> ParsedAdvisory:
    adv = ADVISORY_RE.search(text)
    advisory_no = f"{adv.group(1)}-{adv.group(2)}" if adv else None
    d: date | None = None
    m = ISO_DATE_RE.search(text)
    if m:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    else:
        m = DATE_RE.search(text)
        if m:
            d = date(int(m.group(3)), MONTHS[m.group(2).lower()[:3]], int(m.group(1)))
    event_type, severity = None, 2
    for rx, t, sev in TYPE_MAP:
        if rx.search(text):
            event_type, severity = t, sev
            break
    area = None
    for rx, code in AREAS:
        if rx.search(text):
            area = code
            break
    lat = lon = None
    p = POS_RE.search(text)
    if p:
        lat = _dms(p.group(1), p.group(2), p.group(3))
        lon = _dms(p.group(4), p.group(5), p.group(6))
    # first sentence that mentions the event as the summary
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    summary = next((s for s in sentences if any(rx.search(s) for rx, _, _ in TYPE_MAP)), sentences[0] if sentences else text[:300])
    return ParsedAdvisory(advisory_no, d, event_type, severity, area, lat, lon, summary[:600])


def ingest_text(db: Session, text: str, *, external_id: str, url: str | None = None, published_at: datetime | None = None) -> ThreatEvent | None:
    doc, created = upsert_document(db, RawDoc(SOURCE, external_id, text, url=url, published_at=published_at))
    if not created:
        return None
    parsed = parse_advisory(text)
    if parsed.event_type is None or parsed.event_date is None:
        doc.status = "extracted"
        return None
    ev = ThreatEvent(
        event_date=parsed.event_date, event_type=parsed.event_type, location_name=parsed.area, country=parsed.area,
        lat=parsed.lat, lon=parsed.lon, severity=parsed.severity, description_en=parsed.summary,
        source_doc_id=doc.id, provenance={"source": f"UKMTO advisory {parsed.advisory_no or external_id}", "url": url or "", "grade": "A2"},
        verification="pending",
    )
    db.add(ev)
    doc.status = "extracted"
    return ev


def fetch_and_ingest(db: Session, urls: list[str]) -> int:
    """Download advisory PDFs (URLs discovered by the operator or a listing scraper), extract
    text with pdfplumber and ingest. Returns the number of new events."""
    import io

    import pdfplumber

    n = 0
    for url in urls:
        data = fetch_bytes(url)
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        ev = ingest_text(db, text, external_id=url.rsplit("/", 1)[-1], url=url)
        if ev is not None:
            n += 1
    db.commit()
    return n
