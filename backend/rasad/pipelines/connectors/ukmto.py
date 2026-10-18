"""UKMTO warnings and advisories (published as one-page PDFs on mscio.eu and ukmto.org).

A warning is a short structured notice:

    UKMTO WARNING
    134-26 - ATTACK
    Report Date: Report Time: Issue Date: Source
    12 Sep 26 2300UTC 13 Sep 26 Verified
    UKMTO has received a report of an incident 116NM east of Aden, Yemen. A vessel has
    been hit by an unknown projectile ...

The parser reads the number, UKMTO's own category, the report date, the source line, the
location phrase (distance, bearing and place), a position in either DDMM.MN DDDMM.ME or
DD MM.MN form, and the narrative. Updates ("UPDATE 001") refer to the same incident number
and amend the existing event rather than creating another. Everything it produces is
`pending` until an analyst accepts it; the ledger of record is the verified set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import ThreatEvent
from .base import RawDoc, fetch_bytes, upsert_document

SOURCE = "ukmto"

# UKMTO's headline category decides the event type; the body lexicon is the fallback
HEADLINE_TYPES = {
    "ATTACK": ("maritime_attack", 4), "INCIDENT": ("maritime_attack", 3), "WARNING": ("maritime_attack", 4),
    "HIJACK": ("seizure", 5), "ILLEGAL BOARDING": ("seizure", 4), "BOARDING": ("seizure", 4), "SEIZURE": ("seizure", 5), "DETENTION": ("seizure", 4),
    "ATTEMPTED BOARDING": ("maritime_harassment", 3), "ATTEMPTED HIJACK": ("maritime_harassment", 3),
    "SUSPICIOUS ACTIVITY": ("maritime_harassment", 2), "SUSPICIOUS APPROACH": ("maritime_harassment", 2), "APPROACH": ("maritime_harassment", 2),
    "ELECTRONIC INTERFERENCE": ("gnss_interference", 2), "ELECTRONIC INTERFERANCE": ("gnss_interference", 2), "GPS INTERFERENCE": ("gnss_interference", 2),
    "ADVISORY": (None, 2), "INFORMATION": (None, 1),
}
TYPE_MAP = [
    (re.compile(r"\b(explosion|struck by|projectile|missile|hit by|disabling fire|fired upon|fire upon|under fire)\b", re.I), "maritime_attack", 4),
    (re.compile(r"\b(attack|attacked|uav|drone)\b", re.I), "maritime_attack", 4),
    (re.compile(r"\b(boarded|boarding|hijack|seized|seizure|detained|taking control)\b", re.I), "seizure", 4),
    (re.compile(r"\b(mine|mines|mining)\b", re.I), "mine_warning", 4),
    (re.compile(r"\b(suspicious approach|suspicious activity|approached by|small craft|skiff|harass|interaction with military|involving a (?:merchant vessel|tanker) and military)\b", re.I), "maritime_harassment", 2),
    (re.compile(r"\b(gps|gnss|jamming|spoofing|electronic interfer\w+|electromagnetic)\b", re.I), "gnss_interference", 2),
    (re.compile(r"\b(access restrictions|closure|closed|navtex|notice to mariners|blockade|movement process|convoy)\b", re.I), "maritime_advisory", 2),
]

HEADLINE_RE = re.compile(r"(?:UKMTO\s+)?(?:WARNING|ADVISORY)?\s*(?:[-–]\s*)?(?:UPDATE\s*\d{3}\s*)?(\d{3})[-_](\d{2})\s*[-–]\s*([A-Z][A-Z ]+?)(?=\s*(?:[-–]|UPDATE|Update|Report|Issue|\n|$))", re.M)
UPDATE_RE = re.compile(r"UPDATE\s*[-–]?\s*(\d{3})", re.I)
ADVISORY_RE = re.compile(r"(?:advisory|warning|incident)\s*(\d{3})[-/_](\d{2})", re.I)
DATE_RE = re.compile(r"(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(20\d{2}|\d{2})\b", re.I)
NUMERIC_DATE_RE = re.compile(r"\b(\d{2})/(\d{2})/(20\d{2})\b")
ISO_DATE_RE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")
REPORT_LINE_RE = re.compile(r"Report Date:.*\n(.+)(?:\n([A-Z][a-z]+)\n)?", re.I)
TIME_RE = re.compile(r"\b(\d{4})\s*(?:UTC|Z)\b", re.I)
SOURCE_RE = re.compile(r"Source\s*[:\-]?\s*\n?(?:[^\n]*?UTC\s+\d{1,2}\s+\w+\s+\d{2,4}\s+)?([A-Z][A-Za-z ]{3,40}?)(?:\n|$)")
POS_RE = re.compile(r"(\d{1,2})[°\s](\d{1,2}(?:\.\d+)?)['’]?\s*([NS])[,\s]+(\d{1,3})[°\s](\d{1,2}(?:\.\d+)?)['’]?\s*([EW])", re.I)
COMPACT_POS_RE = re.compile(r"\b(\d{2})(\d{2}(?:\.\d+)?)\s*([NS])[\s,]+(\d{3})(\d{2}(?:\.\d+)?)\s*([EW])\b")
INCIDENT_LOC_RE = re.compile(r"report of an? (?:incident|vessel|event|suspicious activity|approach)[^.\n]*?\s((?:approximately\s+|approx\.?\s+)?\d{1,4}\s*NM\s+[A-Za-z\- ]+?\s+of\s+[^.\n]+?|within\s+[^.\n]+?|in\s+the\s+[^.\n]+?|off\s+[^.\n]+?)\s*(?:\.|\n)", re.I)
NM_RE = re.compile(r"(\d{1,4})\s*NM\s+([A-Za-z\- ]+?)\s+of\s+([A-Z][A-Za-z' \-]{2,40}?)(?:,\s*([A-Z][A-Za-z ]{2,30}))?(?:\.|$|\n)")

AREAS = [
    (re.compile(r"\b(hormuz|strait of hormuz|bandar abbas|jask|sirik|larak|qeshm|khasab|musandam)\b", re.I), "HORMUZ"),
    (re.compile(r"\b(fujairah|khor ?fakkan|abu dhabi|dubai|jebel ali|ras al khaimah|ajman|sharjah|\buae\b|united arab emirates|das island|ruwais)\b", re.I), "AE"),
    (re.compile(r"\b(red sea|bab[- ]?al[- ]?mandab|bab el[- ]?mandeb|hodeidah|hudaydah|mokha|mukha|mocha|eilat|jeddah|yanbu|ras isa|kamaran|salif)\b", re.I), "RED_SEA"),
    (re.compile(r"\b(gulf of aden|\baden\b|socotra|somali|somalia|mukalla|nishtun|mareeyo|eyl|hobyo|bosaso|shihr|balhaf|ash shihr)\b", re.I), "GULF_OF_ADEN"),
    (re.compile(r"\b(gulf of oman|arabian sea|muscat|sohar|duqm|salalah|\boman\b|ras al hadd|sur\b)\b", re.I), "OM"),
    (re.compile(r"\b(doha|ras laffan|mesaieed|qatar|hamad port)\b", re.I), "QA"),
    (re.compile(r"\b(ras tanura|jubail|jubayl|dammam|al ahsa|saudi|khafji)\b", re.I), "SA"),
    (re.compile(r"\b(kuwait|shuwaikh|shuaiba|mina al[- ]ahmadi)\b", re.I), "KW"),
    (re.compile(r"\b(bahrain|manama|mina salman|sitra)\b", re.I), "BH"),
    (re.compile(r"\b(iraq|basrah|basra|umm qasr|khor al zubair)\b", re.I), "IQ"),
    (re.compile(r"\b(iran|kharg|bushehr|bandar|assaluyeh)\b", re.I), "IR"),
    (re.compile(r"\b(arabian gulf|persian gulf)\b", re.I), "ARABIAN_GULF"),
    (re.compile(r"\b(yemen)\b", re.I), "GULF_OF_ADEN"),
]

# bounding boxes (lat_min, lat_max, lon_min, lon_max) used when the text names no place
BOXES = [
    (24.0, 27.5, 55.0, 57.5, "HORMUZ"),
    (22.0, 26.5, 57.5, 62.5, "OM"),
    (10.0, 16.5, 42.0, 46.0, "GULF_OF_ADEN"),
    (10.0, 16.5, 46.0, 56.0, "GULF_OF_ADEN"),
    (-2.0, 12.0, 46.0, 60.0, "GULF_OF_ADEN"),
    (12.0, 30.0, 32.0, 44.0, "RED_SEA"),
    (24.0, 30.5, 47.5, 55.0, "ARABIAN_GULF"),
]

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


@dataclass
class ParsedAdvisory:
    advisory_no: str | None
    update_no: int | None
    category: str | None
    event_date: date | None
    event_type: str | None
    severity: int
    area: str | None
    location: str | None
    lat: float | None
    lon: float | None
    source_line: str | None
    summary: str


def _dms(deg: str, minutes: str, hemi: str) -> float:
    v = float(deg) + float(minutes) / 60
    return -v if hemi.upper() in ("S", "W") else v


def _date(m: re.Match) -> date | None:
    yr = int(m.group(3))
    yr = yr + 2000 if yr < 100 else yr
    try:
        return date(yr, MONTHS[m.group(2).lower()[:3]], int(m.group(1)))
    except (ValueError, KeyError):
        return None


def _area_from_box(lat: float, lon: float) -> str | None:
    for a, b, c, d, code in BOXES:
        if a <= lat <= b and c <= lon <= d:
            return code
    return None


def parse_advisory(text: str) -> ParsedAdvisory:
    head = text[:400]
    hm = HEADLINE_RE.search(head)
    advisory_no = f"{hm.group(1)}-{hm.group(2)}" if hm else None
    if advisory_no is None:
        adv = ADVISORY_RE.search(text)
        advisory_no = f"{adv.group(1)}-{adv.group(2)}" if adv else None
    um = UPDATE_RE.search(head)
    update_no = int(um.group(1)) if um else None
    category = hm.group(3).strip().upper() if hm else None
    if category:
        category = re.sub(r"\s+", " ", category.replace("UPDATE", "")).strip()

    d: date | None = None
    rl = REPORT_LINE_RE.search(text)
    if rl:
        m = DATE_RE.search(rl.group(1))
        if m:
            d = _date(m)
        else:
            nm = NUMERIC_DATE_RE.search(rl.group(1))
            if nm:
                try:
                    d = date(int(nm.group(3)), int(nm.group(2)), int(nm.group(1)))
                except ValueError:
                    d = None
    if d is None:
        m = ISO_DATE_RE.search(text)
        if m:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        else:
            m = DATE_RE.search(text)
            d = _date(m) if m else None

    event_type, severity = None, 2
    if category in HEADLINE_TYPES and HEADLINE_TYPES[category][0]:
        event_type, severity = HEADLINE_TYPES[category]
    body = text[hm.end():] if hm else text
    if event_type is None:
        for rx, t, sev in TYPE_MAP:
            if rx.search(body):
                event_type, severity = t, sev
                break
    if event_type is None and hm:
        event_type, severity = "maritime_advisory", 1
    if category and "ATTEMPTED" in category and event_type == "seizure":
        event_type, severity = "maritime_harassment", 3

    source_line = None
    if rl:
        tail = re.sub(r".*?(?:UTC|Z|TBC)\s+(?:\d{1,2}\s+\w+\s+\d{2,4}|\d{2}/\d{2}/\d{4})\s*", "", rl.group(1), flags=re.I)
        if rl.group(2):
            tail = tail.strip() + " " + rl.group(2)  # "Company Security" / "Officer" wrapped over two lines
        source_line = tail.strip() or None

    lat = lon = None
    p = COMPACT_POS_RE.search(text) or POS_RE.search(text)
    if p:
        lat = _dms(p.group(1), p.group(2), p.group(3))
        lon = _dms(p.group(4), p.group(5), p.group(6))

    location = None
    lm = INCIDENT_LOC_RE.search(text)
    if lm:
        location = " ".join(lm.group(1).split()).strip(" ,")
    area = None
    for rx, code in AREAS:
        if rx.search(location or "") or rx.search(text):
            area = code
            break
    if area is None and lat is not None and lon is not None:
        area = _area_from_box(lat, lon)

    narrative = body if hm else text
    narrative = re.split(r"\|\s*watchkeepers|Vessels are advised", narrative, maxsplit=1)[0]
    narrative = re.sub(r"Report Date:.*?\n.*?\n(?:[A-Z][a-z]+\n)?", "", narrative, count=1, flags=re.I)
    narrative = re.sub(r"^\s*(?:[-–]\s*)?(?:UPDATE\s*\d{3}\s*)?(?:Officer|Reports)?\s*", "", narrative, count=1, flags=re.I)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", " ".join(narrative.split())) if s.strip()]
    summary = " ".join(sentences[:4]) if sentences else text[:300]
    return ParsedAdvisory(advisory_no, update_no, category, d, event_type, severity, area, location, lat, lon, source_line, summary[:700])


def _find_existing(db: Session, advisory_no: str) -> ThreatEvent | None:
    for ev in db.scalars(select(ThreatEvent).where(ThreatEvent.provenance["incident_no"].as_string() == advisory_no)):
        return ev
    return None


def ingest_text(db: Session, text: str, *, external_id: str, url: str | None = None, published_at: datetime | None = None) -> ThreatEvent | None:
    doc, created = upsert_document(db, RawDoc(SOURCE, external_id, text, url=url, published_at=published_at))
    if not created:
        return None
    parsed = parse_advisory(text)
    if parsed.event_type is None or parsed.event_date is None:
        doc.status = "extracted"
        return None
    prov = {"source": f"UKMTO {parsed.category or 'advisory'} {parsed.advisory_no or external_id}", "url": url or "", "grade": "A2", "incident_no": parsed.advisory_no or external_id}
    if parsed.source_line:
        prov["reported_by"] = parsed.source_line
    if parsed.update_no is not None:
        prov["update_no"] = parsed.update_no
    existing = _find_existing(db, parsed.advisory_no) if parsed.advisory_no else None
    if existing is not None:
        # an update amends the incident of record: newer category wins, narrative appended
        prev_update = (existing.provenance or {}).get("update_no") or 0
        if parsed.update_no is not None and parsed.update_no >= prev_update:
            existing.event_type = parsed.event_type
            existing.severity = max(existing.severity or 0, parsed.severity)
            existing.description_en = (existing.description_en or "").split(" Update ")[0] + f" Update {parsed.update_no:03d}: {parsed.summary}"
            if parsed.lat is not None:
                existing.lat, existing.lon = parsed.lat, parsed.lon
            existing.provenance = {**(existing.provenance or {}), "update_no": parsed.update_no, "update_url": url or ""}
        doc.status = "extracted"
        return None
    ev = ThreatEvent(
        event_date=parsed.event_date, event_type=parsed.event_type, location_name=parsed.location, country=parsed.area,
        lat=parsed.lat, lon=parsed.lon, severity=parsed.severity, description_en=parsed.summary,
        source_doc_id=doc.id, provenance=prov, verification="pending",
    )
    db.add(ev)
    doc.status = "extracted"
    return ev


def ingest_pdf(db: Session, data: bytes, *, external_id: str, url: str | None = None) -> ThreatEvent | None:
    import io

    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    return ingest_text(db, text, external_id=external_id, url=url)


def fetch_and_ingest(db: Session, urls: list[str]) -> int:
    """Download advisory PDFs (URLs discovered by the operator or the mscio listing connector),
    extract text with pdfplumber and ingest. Returns the number of new events."""
    n = 0
    for url in urls:
        ev = ingest_pdf(db, fetch_bytes(url), external_id=url.rsplit("/", 1)[-1], url=url)
        if ev is not None:
            n += 1
    db.commit()
    return n
