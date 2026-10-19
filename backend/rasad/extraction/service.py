from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Actor, Document, Issue, PolicyObservation, ThreatEvent
from . import prompts, rules
from .schema import ExtractionResult


def _provider_anthropic(text: str, published: date, language: str, source_name: str) -> ExtractionResult | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    import anthropic

    client = anthropic.Anthropic(api_key=s.anthropic_api_key)
    msg = client.messages.create(model=s.anthropic_model, max_tokens=4000, system=prompts.SYSTEM, messages=[{"role": "user", "content": prompts.user_prompt(text, published.isoformat(), language, source_name)}])
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return _parse_json(raw, f"anthropic:{s.anthropic_model}")


def _provider_local(text: str, published: date, language: str, source_name: str) -> ExtractionResult | None:
    s = get_settings()
    if not s.local_model_base_url:
        return None
    import httpx

    body = {"model": s.local_model_name, "messages": [{"role": "system", "content": prompts.SYSTEM}, {"role": "user", "content": prompts.user_prompt(text, published.isoformat(), language, source_name)}], "temperature": 0}
    r = httpx.post(f"{s.local_model_base_url.rstrip('/')}/chat/completions", json=body, timeout=120)
    r.raise_for_status()
    raw = r.json()["choices"][0]["message"]["content"]
    return _parse_json(raw, f"local:{s.local_model_name}")


def _parse_json(raw: str, provider: str) -> ExtractionResult | None:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < 0:
        return None
    try:
        data = json.loads(raw[start : end + 1])
        res = ExtractionResult.model_validate(data)
        res.provider = provider
        return res
    except Exception:
        return None


# official wires and government feeds speak for their government when a story names no other actor
SOURCE_DEFAULT_ACTOR = {"qna": "QA", "spa": "SA", "wam": "AE", "adm": "AE", "ukgov": "UK", "kuna": "KW", "bna": "BH", "ona": "OM", "tasnim": "IR", "irna": "IR"}


def extract(text: str, published: date, language: str, source_name: str, source_code: str | None = None) -> ExtractionResult:
    s = get_settings()
    out: ExtractionResult | None = None
    from .. import licence

    licensed = licence.current().has("model")
    if s.model_provider in ("anthropic", "local") and not licensed:
        out = None  # the licence does not carry model-assisted extraction: the built-in rules run
    elif s.model_provider == "anthropic":
        out = _provider_anthropic(text, published, language, source_name)
    elif s.model_provider == "local":
        out = _provider_local(text, published, language, source_name)
    if out is None:
        out = rules.extract(text, published, language, default_actor=SOURCE_DEFAULT_ACTOR.get(source_code or ""))
    return out


# wires that publish each story in English and Arabic under one source
BILINGUAL = {"qna", "wam", "spa", "bna", "kuna", "ona"}

_STOP = set("the and for with from that this into after over amid says said will have has been their its are was were not but who what new news report reports".split())


def _tokens(text: str) -> set[str]:
    """Content words of a headline or excerpt, without the outlet suffix GDELT appends."""
    import re

    t = re.sub(r"\s+[a-z0-9.-]+\.[a-z]{2,}(\s+[A-Z][\w ]+)?$", "", text or "")
    return {w for w in re.findall(r"[\w\u0600-\u06FF]{3,}", t.lower()) if w not in _STOP}


_NUM_WORDS = {"two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}


_AR_NUM = {
    r"(طائرتين|مسيرتين|صاروخين|زورقين|سفينتين|ناقلتين|اثنين|اثنتين)": "2", r"\bثلاث(ة)?\b": "3", r"\bأربع(ة)?\b": "4",
    r"\bخمس(ة)?\b": "5", r"\bست(ة)?\b": "6", r"\bسبع(ة)?\b": "7", r"\bثماني(ة)?\b": "8", r"\bتسع(ة)?\b": "9", r"\bعشر(ة)?\b": "10",
}


def _numbers(text: str) -> set[str]:
    import re

    t = re.sub(r"[\u0660-\u0669]", lambda m: str(ord(m.group()) - 0x0660), (text or "").lower())
    months = r"(january|february|march|april|may|june|july|august|september|october|november|december|يناير|فبراير|مارس|أبريل|مايو|يونيو|يوليو|أغسطس|سبتمبر|أكتوبر|نوفمبر|ديسمبر)"
    t = re.sub(rf"\b\d{{1,2}}\s+{months}\b|\b{months}\s+\d{{1,2}}\b", " ", t)  # dates are not counts
    found = set(re.findall(r"\b\d{1,4}\b", t)) | {v for k, v in _NUM_WORDS.items() if re.search(rf"\b{k}\b", t)}
    found |= {v for k, v in _AR_NUM.items() if re.search(k, t)}
    return found


def _same_story(a: str, b: str, threshold: float = 0.6) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    na, nb = _numbers(a), _numbers(b)
    if na and nb and not (na & nb):
        return False  # "two drones" and "four drones" are different stories
    return len(ta & tb) / len(ta | tb) >= threshold


def _numbers_agree(a: str, b: str) -> bool:
    """Two language versions of one story state the same count, or neither states one."""
    na, nb = _numbers(a), _numbers(b)
    return bool(na & nb) if (na or nb) else True


def _domain(url: str | None) -> str:
    from urllib.parse import urlparse

    return (urlparse(url or "").hostname or "").removeprefix("www.")


def _note_copy(row, doc: Document) -> None:
    prov = dict(row.provenance or {})
    also = list(prov.get("also_carried_by") or [])
    if doc.url and doc.url not in also and doc.url != prov.get("url"):
        also.append(doc.url)
    prov["also_carried_by"] = also[:20]
    row.provenance = prov


def process_document(db: Session, doc: Document) -> tuple[int, int]:
    published = (doc.published_at or doc.fetched_at).date()
    res = extract(doc.raw_text or "", published, doc.language, doc.source.name, doc.source.code)
    actors = {a.code: a.id for a in db.scalars(select(Actor)).all()}
    issues = {i.code: i.id for i in db.scalars(select(Issue)).all()}
    n_e = n_o = 0
    for e in res.events:
        if not e.country:
            continue  # no Gulf or regional geography in the text: not a ledger event (a Ukraine ceasefire headline, say)
        near = db.scalars(select(ThreatEvent).where(
            ThreatEvent.event_date >= e.event_date - timedelta(days=1), ThreatEvent.event_date <= e.event_date + timedelta(days=1),
            ThreatEvent.event_type == e.event_type, ThreatEvent.country == e.country, ThreatEvent.source_doc_id.is_not(None),
        )).all()
        # same day, type and place are already required, so a looser word overlap is enough to call
        # two headlines one story (0.3 joins "tanker hits naval mine south of Hormuz" with "oil tanker
        # on fire after hitting mine in Hormuz")
        # a syndicated copy: another outlet carrying a story already in the queue. Same day, type and
        # place are required, so a loose word overlap is enough; two stories from the same outlet are
        # never folded (QNA files several separate intercept reports a day in near-identical words)
        dom = _domain(doc.url)
        dup = next((r for r in near if str((r.provenance or {}).get("grade", ""))[:1] == "C" and _domain((r.provenance or {}).get("url")) != dom
                    and _same_story(r.description_en, e.description_en, 0.25)), None)
        if dup is not None:
            _note_copy(dup, doc)
            continue
        if doc.source.code in BILINGUAL:
            # the same wire's version of this story in the other language: pair one to one, keep both texts
            cands = [r for r in near if (r.provenance or {}).get("source_code") == doc.source.code and (r.provenance or {}).get("lang") not in (None, doc.language)
                     and not (r.provenance or {}).get("twin_doc") and _numbers_agree(r.description_en, e.description_en)]
            mine = _numbers(e.description_en)
            # a version that states the same count beats one that states none
            cands.sort(key=lambda r: (not (mine & _numbers(r.description_en)), r.id))
            twin = cands[0] if cands else None
            if twin is not None:
                prov = dict(twin.provenance or {})
                prov["twin_doc"], prov["twin_url"] = doc.id, doc.url or ""
                twin.provenance = prov
                if doc.language == "ar":
                    twin.description_ar = twin.description_ar or e.description_en[:400]
                elif not twin.description_ar:
                    twin.description_ar, twin.description_en = twin.description_en, e.description_en
                continue
        db.add(ThreatEvent(
            event_date=e.event_date, event_type=e.event_type, country=e.country, location_name=e.location_name,
            actor_id=actors.get(e.actor) if e.actor else None, target_actor_id=actors.get(e.target) if e.target else None,
            fatalities=e.fatalities, severity=e.severity, description_en=e.description_en, description_ar=e.description_ar,
            source_doc_id=doc.id, provenance={"source": doc.source.name, "source_code": doc.source.code, "lang": doc.language, "url": doc.url or "", "grade": "C3", "provider": res.provider, "quote": e.quote, "confidence": e.confidence},
            verification="pending",
        ))
        db.flush()
        n_e += 1
    for o in res.observations:
        if o.actor not in actors or o.issue not in issues:
            continue
        near = db.scalars(select(PolicyObservation).where(
            PolicyObservation.actor_id == actors[o.actor], PolicyObservation.issue_id == issues[o.issue],
            PolicyObservation.observed_at >= o.observed_at - timedelta(days=2), PolicyObservation.observed_at <= o.observed_at + timedelta(days=2),
            PolicyObservation.source_grade == "C3",
        )).all()
        dup = next((r for r in near if _same_story(r.text_excerpt or "", o.quote or "")), None)
        if dup is not None:
            _note_copy(dup, doc)
            continue
        db.add(PolicyObservation(
            actor_id=actors[o.actor], issue_id=issues[o.issue], observed_at=o.observed_at, track=o.track, channel=o.channel,
            cost_class=o.cost_class, speaker_level=o.speaker_level, language=doc.language, score=o.score, source_grade="C3",
            model_confidence=o.confidence, text_excerpt=o.quote, text_excerpt_en=o.quote_en, source_doc_id=doc.id,
            provenance={"source": doc.source.name, "url": doc.url or "", "grade": "C3", "provider": res.provider}, verification="pending",
        ))
        db.flush()
        n_o += 1
    doc.status = "extracted"
    return n_e, n_o


# sources whose documents are read by a dedicated parser (PDF library, data services); the lexicon
# extractor runs on wires and news only, where a sentence is a claim rather than a whole report
PARSED_SOURCES = {"ukmto", "jmic", "mscio", "jwc", "portwatch", "ofac", "uk_sanctions", "state_fms"}


def process_pending(db: Session, limit: int = 200) -> dict:
    docs = db.scalars(select(Document).where(Document.status == "ingested").order_by(Document.fetched_at).limit(limit)).all()
    tot_e = tot_o = 0
    for d in docs:
        if d.source.code in PARSED_SOURCES:
            d.status = "stored"
            db.commit()
            continue
        e, o = process_document(db, d)
        tot_e += e
        tot_o += o
    db.commit()
    return {"documents": len(docs), "events": tot_e, "observations": tot_o, "at": datetime.utcnow().isoformat()}
