"""GDELT DOC 2.0 API: article lists for the platform's standing queries.

Free, including commercial use with attribution, updated every 15 minutes; the DOC API searches
a rolling window and returns title, URL, language, source country and seen date, not article
text. Articles land as documents for extraction and for routing to questions; nothing here is
evidence until an analyst verifies what the extractor proposes from it. Noise is high, so each
query is narrow and capped.
"""

from __future__ import annotations

import json
import time
from datetime import datetime

from sqlalchemy.orm import Session

from .base import RawDoc, fetch_text, upsert_document

API = "https://api.gdeltproject.org/api/v2/doc/doc"
SOURCE = "gdelt"

# query -> question codes it feeds (routing hints; the extractor decides what it contains)
STANDING_QUERIES = {
    '"Strait of Hormuz" (tanker OR vessel OR shipping OR mine)': ["hormuz_closure_90", "gulf_infra_strike_90"],
    '(Houthi OR Houthis) (ship OR vessel OR "Red Sea" OR Saudi)': ["red_sea_attacks_60", "yemen_escalation_sa_90"],
    '(Iran OR IRGC) (missile OR drone) (Saudi OR UAE OR Qatar OR Kuwait OR Bahrain OR Oman)': ["gulf_infra_strike_90"],
    '(Israel) (Iran) (strike OR missile)': ["israel_iran_exchange_60"],
    '(Iraq) (militia OR "Islamic Resistance") (drone OR rocket) (Gulf OR Saudi OR Kuwait)': ["iraq_groups_90"],
    '(OFAC OR sanctions) (Iran) (UAE OR Dubai OR Qatar OR Oman)': ["sanctions_gulf_entity_90"],
    '("Fifth Fleet" OR CENTCOM OR "carrier strike group") (Gulf OR Bahrain OR Qatar)': ["us_posture_change_180"],
    '(GCC OR "Gulf Cooperation Council") (summit OR defence OR defense OR security)': ["gcc_rupture_180"],
    '(cyber OR cyberattack OR ransomware) (Saudi OR UAE OR Qatar OR Kuwait OR Bahrain OR Oman) (infrastructure OR ministry OR port)': ["cyber_cni_90"],
}


MIN_INTERVAL_S = 6.0  # GDELT asks for at most one request every five seconds
_last_call = 0.0


def fetch_articles(query: str, *, maxrecords: int = 75, timespan: str = "3d", languages: tuple[str, ...] = ()) -> list[dict]:
    global _last_call
    q = query + " (" + " OR ".join(f"sourcelang:{lang}" for lang in languages) + ")" if languages else query
    url = f"{API}?query={q}&mode=artlist&format=json&maxrecords={maxrecords}&timespan={timespan}&sort=datedesc"
    url = url.replace(" ", "%20").replace('"', "%22").replace("(", "%28").replace(")", "%29")
    wait = MIN_INTERVAL_S - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()
    text = fetch_text(url, timeout=60)
    if text.lstrip().startswith("Please limit requests"):
        raise RuntimeError("GDELT rate limit")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    return data.get("articles", [])


def to_docs(articles: list[dict], question_codes: list[str]) -> list[RawDoc]:
    docs = []
    for a in articles:
        url = a.get("url")
        if not url:
            continue
        seen = a.get("seendate")  # 20261018T120000Z
        published = None
        if seen:
            try:
                published = datetime.strptime(seen, "%Y%m%dT%H%M%SZ")
            except ValueError:
                published = None
        lang = {"English": "en", "Arabic": "ar", "Persian": "fa", "Hebrew": "he", "Turkish": "tr"}.get(a.get("language", ""), "en")
        text = " ".join(x for x in [a.get("title", ""), a.get("domain", ""), a.get("sourcecountry", "")] if x)
        docs.append(RawDoc(SOURCE, url, text, url=url, title=a.get("title"), language=lang, published_at=published, meta={"question_codes": question_codes, "domain": a.get("domain"), "sourcecountry": a.get("sourcecountry")}))
    return docs


def fetch_and_ingest(db: Session, *, timespan: str = "3d") -> int:
    n = 0
    for q, codes in STANDING_QUERIES.items():
        try:
            arts = fetch_articles(q, timespan=timespan)
        except Exception:  # noqa: BLE001
            try:
                time.sleep(MIN_INTERVAL_S)
                arts = fetch_articles(q, timespan=timespan)
            except Exception:  # noqa: BLE001
                continue
        for d in to_docs(arts, codes):
            doc, created = upsert_document(db, d)
            if created:
                doc.status = "ingested"
                n += 1
    db.commit()
    return n
