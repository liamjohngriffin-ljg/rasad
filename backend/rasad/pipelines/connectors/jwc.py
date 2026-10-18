"""Lloyd's Joint War Committee listed areas (JWLA circulars).

The circular lists areas and territorial waters where additional premiums apply. The parser
counts GCC states named in the circular and writes the `jwc_gcc_states_listed` series on the
circular's date; it also files an `insurer_listing` event when a state is newly listed.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import SeriesPoint, ThreatEvent
from .base import RawDoc, fetch_bytes, upsert_document

SOURCE = "jwc"
GCC = {
    "SA": re.compile(r"saudi arabia", re.I),
    "AE": re.compile(r"united arab emirates|\bUAE\b", re.I),
    "QA": re.compile(r"\bqatar\b", re.I),
    "KW": re.compile(r"\bkuwait\b", re.I),
    "BH": re.compile(r"\bbahrain\b", re.I),
    "OM": re.compile(r"\boman\b", re.I),
}
CIRC_RE = re.compile(r"JWLA[- ]?(\d{3})", re.I)
DATE_RE = re.compile(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})")
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], start=1)}


def parse_circular(text: str) -> dict:
    listed = sorted(code for code, rx in GCC.items() if rx.search(text))
    m = CIRC_RE.search(text)
    d = None
    dm = DATE_RE.search(text)
    if dm:
        d = date(int(dm.group(3)), MONTHS[dm.group(2)], int(dm.group(1)))
    return {"circular": f"JWLA-{m.group(1)}" if m else None, "date": d, "gcc_listed": listed}


def ingest_text(db: Session, text: str, *, external_id: str, url: str | None = None, previously_listed: set[str] | None = None) -> dict:
    doc, created = upsert_document(db, RawDoc(SOURCE, external_id, text, url=url))
    parsed = parse_circular(text)
    if parsed["date"] is None:
        return parsed
    d = parsed["date"]
    existing = db.scalar(select(SeriesPoint).where(SeriesPoint.series == "jwc_gcc_states_listed", SeriesPoint.date == d))
    if existing:
        existing.value, existing.is_synthetic, existing.source = len(parsed["gcc_listed"]), False, parsed["circular"] or external_id
    else:
        db.add(SeriesPoint(series="jwc_gcc_states_listed", date=d, value=len(parsed["gcc_listed"]), unit="count", source=parsed["circular"] or external_id, is_synthetic=False))
    if created:
        new = set(parsed["gcc_listed"]) - (previously_listed or set())
        if new:
            db.add(ThreatEvent(
                event_date=d, event_type="insurer_listing", location_name="JWC listed areas", country="HORMUZ", severity=3,
                description_en=f"{parsed['circular'] or external_id} lists {', '.join(sorted(new))} as additional-premium areas.",
                source_doc_id=doc.id, provenance={"source": f"Lloyd's JWC {parsed['circular'] or ''}", "url": url or "", "grade": "A1"},
                verification="verified", verified_by="source", verified_at=datetime.utcnow(),
            ))
    db.commit()
    return parsed


def fetch_and_ingest(db: Session, url: str, previously_listed: set[str] | None = None) -> dict:
    import io

    import pdfplumber

    data = fetch_bytes(url)
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    return ingest_text(db, text, external_id=url.rsplit("/", 1)[-1], url=url, previously_listed=previously_listed)
