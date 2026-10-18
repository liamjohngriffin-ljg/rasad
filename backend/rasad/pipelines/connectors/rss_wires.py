"""State wires and official feeds (QNA, WAM, SPA, Abu Dhabi Media Office, Tasnim) via RSS.

The connector only stores documents; extraction of events and policy observations runs
separately (rasad.extraction) so that model-assisted steps are reviewable. Feeds are polled
every 15 minutes in the scheduler; Tasnim is included only when the operator has recorded a
compliance review (it is IRGC-controlled and sanctioned).
"""

from __future__ import annotations

from datetime import datetime
from time import mktime

import feedparser
from sqlalchemy.orm import Session

from .base import RawDoc, check_egress, upsert_document

FEEDS = {
    "qna": ("https://qna.org.qa/en/rss", "en"),
    "adm": ("https://www.mediaoffice.abudhabi/en/rss/", "en"),
    "wam": ("https://wam.ae/en/rss", "en"),
    "spa": ("https://www.spa.gov.sa/rss", "ar"),
    "tasnim": ("https://tasnimnews.ir/en/rss", "en"),
}


def parse_feed(source_code: str, content: str | bytes, language: str = "en") -> list[RawDoc]:
    parsed = feedparser.parse(content)
    out = []
    for e in parsed.entries:
        published = None
        if getattr(e, "published_parsed", None):
            published = datetime.fromtimestamp(mktime(e.published_parsed))
        text = " ".join(x for x in [getattr(e, "title", ""), getattr(e, "summary", "")] if x)
        out.append(RawDoc(source_code, getattr(e, "id", None) or getattr(e, "link", "") or getattr(e, "title", ""), text, url=getattr(e, "link", None), title=getattr(e, "title", None), language=language, published_at=published))
    return out


def ingest_docs(db: Session, docs: list[RawDoc]) -> int:
    n = 0
    for d in docs:
        _, created = upsert_document(db, d)
        n += int(created)
    db.commit()
    return n


def fetch_and_ingest(db: Session, source_code: str, *, allow_sanctioned: bool = False) -> int:
    url, lang = FEEDS[source_code]
    if source_code == "tasnim" and not allow_sanctioned:
        raise PermissionError("tasnim requires a recorded compliance review; pass allow_sanctioned=True")
    check_egress(url)
    parsed = feedparser.parse(url)
    docs = []
    for e in parsed.entries:
        published = datetime.fromtimestamp(mktime(e.published_parsed)) if getattr(e, "published_parsed", None) else None
        text = " ".join(x for x in [getattr(e, "title", ""), getattr(e, "summary", "")] if x)
        docs.append(RawDoc(source_code, getattr(e, "id", None) or getattr(e, "link", ""), text, url=getattr(e, "link", None), title=getattr(e, "title", None), language=lang, published_at=published))
    return ingest_docs(db, docs)
