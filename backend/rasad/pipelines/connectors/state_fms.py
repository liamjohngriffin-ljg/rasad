"""State Department arms sales congressional notifications (posted there since 26 Feb 2026).

Each notification to a GCC recipient is a sunk-cost, revealed-track observation of US Gulf
force posture (the United States is committing equipment and support years ahead) and an
`arms_notification` event in the threat ledger for the resolution of posture questions.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Actor, Issue, PolicyObservation, ThreatEvent
from .base import RawDoc, fetch_text, upsert_document

SOURCE = "state_fms"
RECIPIENTS = {
    "SA": re.compile(r"\bSaudi Arabia\b", re.I),
    "AE": re.compile(r"\bUnited Arab Emirates\b|\bUAE\b", re.I),
    "QA": re.compile(r"\bQatar\b", re.I),
    "KW": re.compile(r"\bKuwait\b", re.I),
    "BH": re.compile(r"\bBahrain\b", re.I),
    "OM": re.compile(r"\bOman\b", re.I),
}
VALUE_RE = re.compile(r"\$\s?([\d,.]+)\s*(billion|million)", re.I)
DATE_RE = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(20\d{2})")
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], start=1)}


def parse_notifications(text: str) -> list[dict]:
    """Split a listing page into notification items: title line containing a recipient and a
    value, with the nearest date before it."""
    out = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    last_date: date | None = None
    for ln in lines:
        dm = DATE_RE.search(ln)
        if dm:
            last_date = date(int(dm.group(3)), MONTHS[dm.group(1)], int(dm.group(2)))
        for code, rx in RECIPIENTS.items():
            if rx.search(ln) and VALUE_RE.search(ln):
                vm = VALUE_RE.search(ln)
                amount = float(vm.group(1).replace(",", "")) * (1e9 if vm.group(2).lower() == "billion" else 1e6)
                out.append({"recipient": code, "title": ln[:300], "value_usd": amount, "date": last_date})
    return out


def ingest(db: Session, items: list[dict], url: str = "") -> int:
    us = db.scalar(select(Actor).where(Actor.code == "US"))
    issue = db.scalar(select(Issue).where(Issue.code == "gulf_force_posture"))
    n = 0
    for it in items:
        if it["date"] is None:
            continue
        exists = db.scalar(select(ThreatEvent).where(ThreatEvent.event_type == "arms_notification", ThreatEvent.description_en == it["title"]))
        if exists:
            continue
        db.add(ThreatEvent(event_date=it["date"], event_type="arms_notification", country=it["recipient"], severity=1, description_en=it["title"], provenance={"source": "State Department arms sales notifications", "url": url, "grade": "A1"}, verification="verified", verified_by="source"))
        if us and issue:
            score = 0.3 if it["value_usd"] < 1e9 else 0.5
            db.add(PolicyObservation(actor_id=us.id, issue_id=issue.id, observed_at=it["date"], track="revealed", channel="notification", cost_class="sunk_cost", speaker_level="institution", language="en", score=score, source_grade="A1", model_confidence=1.0, text_excerpt=it["title"], provenance={"source": "State Department arms sales notifications", "url": url, "grade": "A1"}, verification="verified", verified_by="source"))
        n += 1
    db.commit()
    return n


def fetch_and_ingest(db: Session, url: str) -> int:
    html = fetch_text(url)
    text = re.sub(r"<[^>]+>", "\n", html)
    upsert_document(db, RawDoc(SOURCE, f"listing-{datetime.utcnow().date().isoformat()}", text, url=url))
    return ingest(db, parse_notifications(text), url=url)
