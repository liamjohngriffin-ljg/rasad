"""JMIC weekly Middle East dashboard (CMF / UKMTO), published as PDFs on mscio.eu.

Two formats exist. Before the 2026 war the dashboard carried a CMF Regional Threat Level
Assessment with sentences per threat (Houthi threat to mariners, SoH harassment, SoH blockade,
piracy, GNSS interference). From March 2026 CMF suspended that assessment and the dashboard
states area levels in prose ("the threat levels in the Arabian Gulf, Gulf of Oman, and SoH
remain assessed as CRITICAL"). The parser reads both, plus the weekly incident counts and any
dated key considerations, which land as pending events.
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
LEVEL_RE = r"(LOW|MODERATE|SUBSTANTIAL|SEVERE|CRITICAL)"
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

AREA_TOKENS = {
    "red_sea": [r"\bRS\b", r"red sea"],
    "bab_al_mandab": [r"\bBAM\b", r"bab[- ]?(?:al|el)[- ]?mand[ae]b"],
    "gulf_of_aden": [r"\bGoA\b", r"gulf of aden"],
    "arabian_gulf": [r"arabian gulf", r"\bAG\b", r"persian gulf"],
    "gulf_of_oman": [r"gulf of oman", r"\bGoO\b"],
    "hormuz": [r"\bSoH\b", r"strait of hormuz", r"\bhormuz\b"],
    "somali_basin": [r"somali basin", r"indian ocean"],
}
LEGEND_RE = re.compile(r"an attack is|remote chance of an|attack definition|probability", re.I)
WEEK_RE = re.compile(r"Week\s*(\d{1,2})\s*[-–]\s*(20\d{2})\s*\(([^)]*)\)", re.I)
KEY_DATE_RE = re.compile(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})\s*[–-]\s*(.+?)(?=(?:\s\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d{2}\s*[–-])|$)", re.I)
NEW_INCIDENTS_RE = re.compile(r"\((\d+)\s+new this week\)", re.I)
TOTAL_INCIDENTS_RE = re.compile(r"Total number of Incidents\s+(\d+)", re.I)
DAYS_SINCE_RE = re.compile(r"Days since last incident[^0-9]{0,40}(\d+)\s*day", re.I)


def _week_end(week: int, year: int, span: str) -> date | None:
    span = span.replace("–", "-").replace(" to ", "-")
    parts = [p.strip() for p in span.split("-") if p.strip()]
    if not parts:
        return None
    end = parts[-1]
    m = re.match(r"(\d{1,2})\s*([A-Za-z]+)?", end)
    if not m:
        return None
    day = int(m.group(1))
    mon = m.group(2)
    if not mon:
        # "12-18 January": month after the end day
        m2 = re.search(r"([A-Za-z]{3,})", span)
        mon = m2.group(1) if m2 else None
    if not mon or mon.lower()[:3] not in MONTHS:
        return None
    month = MONTHS[mon.lower()[:3]]
    y = year
    if week >= 52 and month == 1:
        y = year + 1
    try:
        return date(y, month, day)
    except ValueError:
        return None


def _sentences(text: str) -> list[str]:
    # split at sentence ends followed by a capital or digit (keeps "inc. fleet" together) and at bullets
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9•])|•", text) if s.strip()]


def parse_dashboard(text: str) -> dict:
    t = " ".join(text.split())
    wm = WEEK_RE.search(t)
    week = int(wm.group(1)) if wm else None
    year = int(wm.group(2)) if wm else None
    week_end = _week_end(week, year, wm.group(3)) if wm else None
    levels: dict[str, int] = {}
    threats: dict[str, int] = {}
    level_pat = re.compile(r"(?:assessed as|remains? at|remains?|remain assessed as|(?:raised|lowered|increased|decreased|reduced) to|is now|is|are)\s+" + LEVEL_RE, re.I)
    for s in _sentences(t):
        if LEGEND_RE.search(s):
            continue
        matches = list(level_pat.finditer(s))
        if not matches:
            continue
        unassigned = False
        for lm in matches:
            level = LEVELS[lm.group(1).upper()]
            window = s[max(0, lm.start() - 90): lm.end() + 40].lower()
            if "piracy" in window:
                threats["piracy"] = level
            elif "harassment" in window:
                threats["soh_harassment"] = level
            elif "blockade" in window:
                threats["soh_blockade"] = level
            elif re.search(r"gnss|\bemi\b|electromagnetic|em interference|levels of interference", window):
                threats["gnss_interference"] = level
            else:
                unassigned = True
        if not unassigned:
            continue
        low = s.lower()
        if "merchant vessel" in low and ("houthi" in low or "rs, bam" in low or "bam and goa" in low):
            threats["houthi_to_mariners"] = LEVELS[matches[0].group(1).upper()]
        if not re.search(r"threat|security environment", low):
            continue  # the EMI map page states interference levels by area; those are not threat levels
        for area, pats in AREA_TOKENS.items():
            hits = [m.start() for p in pats for m in re.finditer(p, s, re.I)]
            if not hits:
                continue
            idx = min(hits)
            lvls = [(m.start(), LEVELS[m.group(1).upper()]) for m in re.finditer(LEVEL_RE, s, re.I)]
            if lvls:
                nearest = min(lvls, key=lambda x: abs(x[0] - idx))
                levels[area] = nearest[1]
    for s in _sentences(t):
        if re.match(r"^(LOW|MODERATE|SUBSTANTIAL|SEVERE|CRITICAL)\s+EM", s, re.I):
            threats.setdefault("gnss_interference", LEVELS[s.split()[0].upper()])
    mine = any(
        re.search(r"\bmine", s, re.I) and re.search(r"warning|confirmed|laid|threat (?:is|remains) (?:assessed|high)", s, re.I) and not re.search(r"unsubstantiated|no confirmation|not confirmed", s, re.I)
        for s in _sentences(t)
    )
    key_events = []
    for m in KEY_DATE_RE.finditer(t):
        try:
            d = date(int(m.group(3)), MONTHS[m.group(2).lower()[:3]], int(m.group(1)))
        except (ValueError, KeyError):
            continue
        desc = re.split(r"•|\s\d{1,2}\s+Electromagnetic|\s\d{1,2}/\d{1,2}\s", m.group(4))[0].strip()
        if desc:
            key_events.append((d, desc[:400]))
    new_inc = NEW_INCIDENTS_RE.search(t)
    tot = TOTAL_INCIDENTS_RE.search(t)
    days = DAYS_SINCE_RE.search(t)
    return {
        "week": week, "year": year, "week_end": week_end, "levels": levels, "threats": threats, "mine_warning": mine,
        "key_events": key_events, "new_incidents": int(new_inc.group(1)) if new_inc else None,
        "total_incidents": int(tot.group(1)) if tot else None, "days_since_incident": int(days.group(1)) if days else None,
    }


EVENT_LEXICON = [
    (re.compile(r"missile|projectile|ballistic", re.I), "missile_strike", 4),
    (re.compile(r"\buav\b|drone|uas\b", re.I), "drone_strike", 3),
    (re.compile(r"mine", re.I), "mine_warning", 4),
    (re.compile(r"exercise|drill", re.I), "exercise", 1),
    (re.compile(r"seiz|detain|board", re.I), "seizure", 4),
    (re.compile(r"attack|struck|fired", re.I), "maritime_attack", 4),
    (re.compile(r"navtex|warning|closure|closed", re.I), "statement_threat", 2),
]


def ingest_text(db: Session, text: str, *, external_id: str, url: str | None = None) -> dict:
    doc, created = upsert_document(db, RawDoc(SOURCE, external_id, text, url=url))
    parsed = parse_dashboard(text)
    d = parsed["week_end"]
    if d is None:
        doc.status = "extracted"
        db.commit()
        return parsed
    src = f"JMIC week {parsed['week']} {parsed['year']}"

    def put(series: str, value: float, unit: str) -> None:
        existing = db.scalar(select(SeriesPoint).where(SeriesPoint.series == series, SeriesPoint.date == d))
        if existing:
            existing.value, existing.is_synthetic, existing.source = value, False, src
        else:
            db.add(SeriesPoint(series=series, date=d, value=value, unit=unit, source=src, is_synthetic=False))

    for area, level in parsed["levels"].items():
        put(f"jmic_threat_level_{area}", level, "level_1_to_5")
    for threat, level in parsed["threats"].items():
        put(f"jmic_threat_{threat}", level, "level_1_to_5")
    if parsed["new_incidents"] is not None:
        put("jmic_new_incidents_week", parsed["new_incidents"], "count")
    if parsed["total_incidents"] is not None:
        put("jmic_incidents_total", parsed["total_incidents"], "count")
    if parsed["days_since_incident"] is not None:
        put("jmic_days_since_incident", parsed["days_since_incident"], "days")
    if created:
        if parsed["mine_warning"]:
            db.add(ThreatEvent(event_date=d - timedelta(days=3), event_type="mine_warning", location_name="Strait of Hormuz approaches", country="HORMUZ", severity=4, description_en=f"{src} dashboard carries a mine warning.", source_doc_id=doc.id, provenance={"source": src, "url": url or "", "grade": "A2"}, verification="pending"))
        for ev_date, desc in parsed["key_events"]:
            etype, sev = "statement_threat", 2
            for rx, t, s in EVENT_LEXICON:
                if rx.search(desc):
                    etype, sev = t, s
                    break
            country = "HORMUZ" if re.search(r"hormuz|soh|arabian gulf", desc, re.I) else "RED_SEA" if re.search(r"red sea|yemen|bam", desc, re.I) else None
            db.add(ThreatEvent(event_date=ev_date, event_type=etype, location_name=None, country=country, severity=sev, description_en=desc, source_doc_id=doc.id, provenance={"source": src + " key considerations", "url": url or "", "grade": "B2"}, verification="pending"))
    doc.status = "extracted"
    db.commit()
    return parsed


def fetch_and_ingest(db: Session, url: str) -> dict:
    import io

    import pdfplumber

    data = fetch_bytes(url)
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    return ingest_text(db, text, external_id=url.rsplit("/", 1)[-1], url=url)
