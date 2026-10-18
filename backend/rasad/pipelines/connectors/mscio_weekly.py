"""MSCIO / EUNAVFOR Atalanta weekly reports (mscio.eu, "WEEKLY THREAT ASSESSMENT" folders).

Each report opens with a table of incidents in the Voluntary Reporting Area by category
(armed robbery, attack, attempted boarding, boarding, hijack, kidnap, piracy, suspicious
activity, other) and then one block per incident:

    1.1. TYPE OF INCIDENT: ATTEMPTED BOARDING.
    1.2. PERIOD: 03 NOV 2025.
    1.3. LOCATION: 322Nm Southeast from Mogadiscio. (00-03N 050-31E).
    2.1. ATTACKED VESSEL.  MV STOLT SAGALAND.

and a piracy threat assessment sentence ("The PIRACY Threat Assessment (TA) is determined
as LOW in ..."). The parser writes weekly count series and pending events with positions.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import SeriesPoint, ThreatEvent
from .base import RawDoc, upsert_document

SOURCE = "mscio"
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
LEVELS = {"LOW": 1, "MODERATE": 2, "ELEVATED": 3, "SUBSTANTIAL": 3, "SIGNIFICANT": 4, "SEVERE": 4, "HIGH": 4, "CRITICAL": 5}
CATEGORIES = {
    "armed robbery": "armed_robbery", "attack": "attack", "attempted boarding": "attempted_boarding", "boarding": "boarding", "hijack": "hijack",
    "kidnap": "kidnap", "piracy": "piracy", "suspicious activity": "suspicious_activity", "other maritime crimes": "other",
}
EVENT_TYPES = {
    "armed_robbery": ("seizure", 3), "attack": ("maritime_attack", 4), "attempted_boarding": ("maritime_harassment", 3), "boarding": ("seizure", 4),
    "hijack": ("seizure", 5), "kidnap": ("seizure", 5), "piracy": ("seizure", 4), "suspicious_activity": ("maritime_harassment", 2), "other": ("maritime_harassment", 2),
}
WEEK_RE = re.compile(r"WEEK\s+(\d{1,2})(?:ST|ND|RD|TH)?\s+([A-Z]{3,9})?\s*(?:TO|-|–)\s*(\d{1,2})(?:ST|ND|RD|TH)?\s+([A-Z]{3,9})\s+(20\d{2})", re.I)
TITLE_RANGE_RE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s*([A-Za-z]{3,9})?\s*(?:–|-|to)\s*(\d{1,2})(?:st|nd|rd|th)?\s*([A-Za-z]{3,9})")
TOTAL_RE = re.compile(r"Total Incidents\s+(\d+)", re.I)
TYPE_RE = re.compile(r"TYPE OF INCIDENT:\s*([A-Z ]+?)\.?\s*\n", re.I)
PERIOD_RE = re.compile(r"P\s?ERIOD:\s*(?:FM\s+)?(\d{1,2})(?:ST|ND|RD|TH)?\s*(?:\d{4}\s*UTC\s*)?(?:TO\s+\d{1,2}(?:ST|ND|RD|TH)?\s*)?([A-Z]{3,9})?\s*(20\d{2})?", re.I)
LOCATION_RE = re.compile(r"LOCATION:\s*([^\n]+?)\.?\s*(?:\((\d{2})-(\d{2}(?:\.\d+)?)\s*([NS])\s+(\d{3})-(\d{2}(?:\.\d+)?)\s*([EW])\))?", re.I)
VESSEL_RE = re.compile(r"ATTACKED VESSEL\.?\s*\n?\s*(?:MV|MT|M/V|M/T|FV|Dhow)?\s*([A-Z][A-Z0-9 \-']{2,40}?)\.?\s*\n", re.I)
TA_RE = re.compile(r"PIRACY Threat Assessment \(TA\) is determined as\s+" + "(" + "|".join(LEVELS) + ")", re.I)
# 2026 layout: bullets per category, then one sentence per MSCIO alert
BULLET_TYPE_RE = re.compile(r"•\s*TYPE\s*OF\s*INCIDENT\s*:\s*([A-Z /]+?)\.", re.I)
BULLET_LOC_RE = re.compile(r"•\s*LOCATION\s*:\s*([^\n]+?)\.?\s*\n", re.I)
ALERT_RE = re.compile(r"On\s*(\d{1,2})\s*([A-Z][a-z]{2,8}),?\s*MSCIO\s*issued\s*ALERT\s*(\d{3})\s*/\s*(\d{2})\s*(.+?)(?=\s*On\s*\d{1,2}\s*[A-Z][a-z]{2,8},?\s*MSCIO\s*issued|\s*•|\s*MSCIO WEEKLY REPORT|$)", re.S)
PLACES = [
    (re.compile(r"\b(strait of hormuz|\bsoh\b|hormuz|khasab|musandam)\b", re.I), "HORMUZ"),
    (re.compile(r"\b(fujairah|khor ?fakkan|jebel ali|dubai|abu dhabi|\buae\b|sharjah|ras al khaimah)\b", re.I), "AE"),
    (re.compile(r"\b(sohar|muscat|duqm|salalah|\boman\b|gulf of oman)\b", re.I), "OM"),
    (re.compile(r"\b(arabian gulf|persian gulf)\b", re.I), "ARABIAN_GULF"),
    (re.compile(r"\b(red sea|bab[- ]?(?:al|el)[- ]?mand[ae]b|hodeidah|hudaydah|yanbu|jeddah|mukha|mocha)\b", re.I), "RED_SEA"),
    (re.compile(r"\b(gulf of aden|\baden\b|somali|somalia|mukalla|horn of africa|socotra|yemen|eyl|mogadis)\b", re.I), "GULF_OF_ADEN"),
    (re.compile(r"\b(iraq|basrah|umm qasr)\b", re.I), "IQ"),
    (re.compile(r"\b(qatar|ras laffan|doha)\b", re.I), "QA"),
    (re.compile(r"\b(saudi|jubail|ras tanura|dammam)\b", re.I), "SA"),
    (re.compile(r"\b(kuwait)\b", re.I), "KW"),
    (re.compile(r"\b(bahrain|manama)\b", re.I), "BH"),
    (re.compile(r"\b(iran|bandar abbas|jask|sirik)\b", re.I), "IR"),
]


def _place(text: str) -> str | None:
    for rx, code in PLACES:
        if rx.search(text):
            return code
    return None


def _week_end(text: str, filename: str | None) -> date | None:
    m = WEEK_RE.search(text)
    if m:
        mon = m.group(4) or m.group(2)
        if mon and mon.lower()[:3] in MONTHS:
            try:
                return date(int(m.group(5)), MONTHS[mon.lower()[:3]], int(m.group(3)))
            except ValueError:
                pass
    years = re.findall(r"\b(20[23]\d)\b", text[:3000])
    year = int(max(set(years), key=years.count)) if years else None
    m = TITLE_RANGE_RE.search(text[:400])
    if m and year and m.group(4).lower()[:3] in MONTHS:
        try:
            return date(year, MONTHS[m.group(4).lower()[:3]], int(m.group(3)))
        except ValueError:
            pass
    if filename:
        fm = re.search(r"(\d{1,2})_?([A-Z]{3})(?:_?(\d{2}))?\.pdf$", filename, re.I)
        if fm and fm.group(2).lower() in MONTHS:
            yr = 2000 + int(fm.group(3)) if fm.group(3) else (year or date.today().year)
            try:
                return date(yr, MONTHS[fm.group(2).lower()], int(fm.group(1)))
            except ValueError:
                pass
    return None


def _counts(text: str) -> dict[str, int]:
    head = text[:1500]
    out: dict[str, int] = {}
    flat = " ".join(head.split())
    for label, key in CATEGORIES.items():
        m = re.search(re.escape(label) + r"\s+(Nil|\d+)\b", flat, re.I)
        if m:
            out[key] = 0 if m.group(1).lower() == "nil" else int(m.group(1))
    tm = TOTAL_RE.search(flat)
    if tm:
        out["total"] = int(tm.group(1))
    return out


def _alert_incidents(text: str, week_end: date | None) -> list[dict]:
    """2026 layout: category bullets followed by one 'On D Month, MSCIO issued ALERT NNN/YY ...' per incident."""
    items: list[dict] = []
    year = week_end.year if week_end else date.today().year
    sections = re.split(r"(?=•\s*TYPE\s*OF\s*INCIDENT)", text)
    for sec in sections[1:]:
        tm = BULLET_TYPE_RE.search(sec)
        cat_raw = (tm.group(1).strip().lower() if tm else "other")
        cat = next((v for k, v in CATEGORIES.items() if k in cat_raw), "other")
        lm = BULLET_LOC_RE.search(sec)
        loc = " ".join(lm.group(1).split()) if lm else None
        for am in ALERT_RE.finditer(sec):
            mon = am.group(2).lower()[:3]
            if mon not in MONTHS:
                continue
            try:
                issued = date(year, MONTHS[mon], int(am.group(1)))
            except ValueError:
                continue
            body = " ".join(am.group(5).split())
            # the attack may have happened earlier than the alert ("... on 10 October")
            d = issued
            em = re.search(r"\bon\s+(\d{1,2})\s+([A-Z][a-z]{2,8})\b", body)
            if em and em.group(2).lower()[:3] in MONTHS:
                try:
                    cand = date(year, MONTHS[em.group(2).lower()[:3]], int(em.group(1)))
                    if cand <= issued:
                        d = cand
                except ValueError:
                    pass
            country = _place(body) or _place(loc or "") or None
            low = body.lower()
            if re.search(r"hijack|boarded|seized|detained|unauthorised persons", low):
                c = "hijack" if "hijack" in low else "boarding"
            elif re.search(r"attack|struck|projectile|uav|explosion|fire on ?board|missile|drone", low):
                c = "attack"
            elif re.search(r"approach|skiff|suspicious|small craft|hail", low):
                c = "suspicious_activity"
            else:
                c = cat
            items.append({"category": c, "date": d, "location": loc, "lat": None, "lon": None, "vessel": None, "summary": f"MSCIO alert {am.group(3)}/{am.group(4)}: {body}"[:600], "ref": f"{am.group(3)}/{am.group(4)}", "country": country})
    return items


def _incidents(text: str, week_end: date | None) -> list[dict]:
    items: list[dict] = _alert_incidents(text, week_end)
    blocks = re.split(r"(?=\b1\.1\.\s*TYPE OF INCIDENT)", text)
    for b in blocks[1:]:
        tm = TYPE_RE.search(b)
        if not tm:
            continue
        cat = CATEGORIES.get(tm.group(1).strip().lower(), "other")
        d: date | None = None
        pm = PERIOD_RE.search(b)
        if pm and pm.group(2) and pm.group(2).lower()[:3] in MONTHS:
            yr = int(pm.group(3)) if pm.group(3) else (week_end.year if week_end else date.today().year)
            try:
                d = date(yr, MONTHS[pm.group(2).lower()[:3]], int(pm.group(1)))
            except ValueError:
                d = None
        if d is None and week_end is not None:
            d = week_end - timedelta(days=3)
        lm = LOCATION_RE.search(b)
        loc = " ".join(lm.group(1).split()) if lm else None
        lat = lon = None
        if lm and lm.group(2):
            lat = int(lm.group(2)) + float(lm.group(3)) / 60
            lat = -lat if lm.group(4).upper() == "S" else lat
            lon = int(lm.group(5)) + float(lm.group(6)) / 60
            lon = -lon if lm.group(7).upper() == "W" else lon
        vm = VESSEL_RE.search(b)
        vessel = " ".join(vm.group(1).split()) if vm else None
        rel = re.search(r"RELEVANT INFORMATION[^\n]*\n(.{40,700}?)(?:\n\s*4\.|\n\s*3\.\d|$)", b, re.S)
        summary = " ".join(rel.group(1).split()) if rel else " ".join(b[:400].split())
        items.append({"category": cat, "date": d, "location": loc, "lat": lat, "lon": lon, "vessel": vessel, "summary": summary[:600], "ref": None, "country": _place(loc or "") or "GULF_OF_ADEN"})
    return items


def parse_report(text: str, filename: str | None = None) -> dict:
    week_end = _week_end(text, filename)
    ta = TA_RE.search(" ".join(text.split()))
    return {"week_end": week_end, "counts": _counts(text), "incidents": _incidents(text, week_end), "piracy_ta": LEVELS[ta.group(1).upper()] if ta else None}


def _put(db: Session, series: str, d: date, value: float, unit: str, src: str) -> None:
    existing = db.scalar(select(SeriesPoint).where(SeriesPoint.series == series, SeriesPoint.date == d))
    if existing:
        existing.value, existing.is_synthetic, existing.source = value, False, src
    else:
        db.add(SeriesPoint(series=series, date=d, value=value, unit=unit, source=src, is_synthetic=False))
    db.flush()


def read_pdf_text(data: bytes) -> str:
    """These reports need a tight x tolerance or words run together."""
    import io

    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join((p.extract_text(x_tolerance=1) or "") for p in pdf.pages)


def ingest_text(db: Session, text: str, *, external_id: str, url: str | None = None, force: bool = False) -> dict:
    doc, created = upsert_document(db, RawDoc(SOURCE, external_id, text, url=url, title=external_id))
    created = created or force
    parsed = parse_report(text, external_id)
    d = parsed["week_end"]
    out = {"week_end": d.isoformat() if d else None, "series": 0, "events": 0}
    if d is None:
        doc.status = "extracted"
        db.commit()
        return out
    src = f"MSCIO Atalanta weekly report to {d.isoformat()}"
    for key, val in parsed["counts"].items():
        _put(db, f"mscio_vra_{key}_week", d, val, "count", src)
        out["series"] += 1
    if parsed["piracy_ta"] is not None:
        _put(db, "mscio_piracy_threat_assessment", d, parsed["piracy_ta"], "level_1_to_5", src)
        out["series"] += 1
    if created:
        for it in parsed["incidents"]:
            if it["date"] is None:
                continue
            etype, sev = EVENT_TYPES[it["category"]]
            desc = (f"{it['category'].replace('_', ' ')} on {it['vessel']}: " if it["vessel"] else f"{it['category'].replace('_', ' ')}: ") + it["summary"]
            desc = desc[:600]
            if db.scalar(select(ThreatEvent).where(ThreatEvent.event_type == etype, ThreatEvent.description_en == desc)):
                continue
            prov = {"source": src, "url": url or "", "grade": "A2"}
            if it["vessel"]:
                prov["vessel"] = it["vessel"]
            if it.get("ref"):
                prov["incident_no"] = f"MSCIO {it['ref']}"
                if db.scalar(select(ThreatEvent).where(ThreatEvent.provenance["incident_no"].as_string() == prov["incident_no"])):
                    continue
            db.add(ThreatEvent(event_date=it["date"], event_type=etype, location_name=it["location"], country=it.get("country") or "GULF_OF_ADEN", lat=it["lat"], lon=it["lon"], severity=sev, description_en=desc, source_doc_id=doc.id, provenance=prov, verification="pending"))
            out["events"] += 1
    doc.status = "extracted"
    db.commit()
    return out
