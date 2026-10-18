from __future__ import annotations

import json
from datetime import date, datetime

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
    if s.model_provider == "anthropic":
        out = _provider_anthropic(text, published, language, source_name)
    elif s.model_provider == "local":
        out = _provider_local(text, published, language, source_name)
    if out is None:
        out = rules.extract(text, published, language, default_actor=SOURCE_DEFAULT_ACTOR.get(source_code or ""))
    return out


def process_document(db: Session, doc: Document) -> tuple[int, int]:
    published = (doc.published_at or doc.fetched_at).date()
    res = extract(doc.raw_text or "", published, doc.language, doc.source.name, doc.source.code)
    actors = {a.code: a.id for a in db.scalars(select(Actor)).all()}
    issues = {i.code: i.id for i in db.scalars(select(Issue)).all()}
    n_e = n_o = 0
    for e in res.events:
        db.add(ThreatEvent(
            event_date=e.event_date, event_type=e.event_type, country=e.country, location_name=e.location_name,
            actor_id=actors.get(e.actor) if e.actor else None, target_actor_id=actors.get(e.target) if e.target else None,
            fatalities=e.fatalities, severity=e.severity, description_en=e.description_en, description_ar=e.description_ar,
            source_doc_id=doc.id, provenance={"source": doc.source.name, "url": doc.url or "", "grade": "C3", "provider": res.provider, "quote": e.quote, "confidence": e.confidence},
            verification="pending",
        ))
        n_e += 1
    for o in res.observations:
        if o.actor not in actors or o.issue not in issues:
            continue
        db.add(PolicyObservation(
            actor_id=actors[o.actor], issue_id=issues[o.issue], observed_at=o.observed_at, track=o.track, channel=o.channel,
            cost_class=o.cost_class, speaker_level=o.speaker_level, language=doc.language, score=o.score, source_grade="C3",
            model_confidence=o.confidence, text_excerpt=o.quote, text_excerpt_en=o.quote_en, source_doc_id=doc.id,
            provenance={"source": doc.source.name, "url": doc.url or "", "grade": "C3", "provider": res.provider}, verification="pending",
        ))
        n_o += 1
    doc.status = "extracted"
    return n_e, n_o


def process_pending(db: Session, limit: int = 200) -> dict:
    docs = db.scalars(select(Document).where(Document.status == "ingested").order_by(Document.fetched_at).limit(limit)).all()
    tot_e = tot_o = 0
    for d in docs:
        e, o = process_document(db, d)
        tot_e += e
        tot_o += o
    db.commit()
    return {"documents": len(docs), "events": tot_e, "observations": tot_o, "at": datetime.utcnow().isoformat()}
