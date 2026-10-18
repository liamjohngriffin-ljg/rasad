"""Database-facing position book."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Actor, Issue, PolicyObservation
from . import positions as P


def load_observations(
    db: Session, actor_code: str, issue_code: str, *, verified_only: bool = False
) -> list[P.Observation]:
    stmt = (
        select(PolicyObservation)
        .join(Actor, PolicyObservation.actor_id == Actor.id)
        .join(Issue, PolicyObservation.issue_id == Issue.id)
        .where(Actor.code == actor_code, Issue.code == issue_code)
    )
    if verified_only:
        stmt = stmt.where(PolicyObservation.verification == "verified")
    else:
        stmt = stmt.where(PolicyObservation.verification != "rejected")
    rows = db.scalars(stmt).all()
    return [
        P.Observation(
            observed_at=r.observed_at,
            track=r.track,
            score=r.score,
            cost_class=r.cost_class,
            speaker_level=r.speaker_level,
            source_grade=r.source_grade,
            model_confidence=r.model_confidence,
            ref=r.id,
        )
        for r in rows
    ]


def issue_position(db: Session, actor_code: str, issue_code: str, as_of: date, *, history_days: int = 180) -> dict:
    obs = load_observations(db, actor_code, issue_code)
    stated = P.estimate(obs, as_of, track="stated")
    revealed = P.estimate(obs, as_of, track="revealed")
    start = as_of - timedelta(days=history_days)
    stated_series = P.series(obs, start, as_of, track="stated")
    revealed_series = P.series(obs, start, as_of, track="revealed")
    return {
        "actor": actor_code,
        "issue": issue_code,
        "as_of": as_of.isoformat(),
        "stated": stated.as_dict(),
        "revealed": revealed.as_dict(),
        "divergence": None if (d := P.divergence(stated, revealed)) is None else round(d, 3),
        "change_points": {
            "stated": P.change_points(stated_series),
            "revealed": P.change_points(revealed_series),
        },
        "silence": P.silence(obs, as_of),
        "series": {
            "stated": [(d.isoformat(), None if v is None else round(v, 3)) for d, v in stated_series],
            "revealed": [(d.isoformat(), None if v is None else round(v, 3)) for d, v in revealed_series],
        },
    }


def actor_book(db: Session, actor_code: str, as_of: date) -> dict:
    actor = db.scalar(select(Actor).where(Actor.code == actor_code))
    if actor is None:
        raise KeyError(actor_code)
    issue_ids = db.scalars(
        select(PolicyObservation.issue_id).where(PolicyObservation.actor_id == actor.id).distinct()
    ).all()
    issues = db.scalars(select(Issue).where(Issue.id.in_(issue_ids))).all() if issue_ids else []
    entries = []
    for issue in sorted(issues, key=lambda i: i.code):
        entry = issue_position(db, actor_code, issue.code, as_of)
        entry["issue_name_en"] = issue.name_en
        entry["issue_name_ar"] = issue.name_ar
        entry["low_label_en"] = issue.low_label_en
        entry["high_label_en"] = issue.high_label_en
        entries.append(entry)
    return {
        "actor": {"code": actor.code, "name_en": actor.name_en, "name_ar": actor.name_ar, "kind": actor.kind},
        "as_of": as_of.isoformat(),
        "issues": entries,
    }


def observation_rows(db: Session, actor_code: str, issue_code: str, limit: int = 50) -> list[dict]:
    stmt = (
        select(PolicyObservation)
        .join(Actor, PolicyObservation.actor_id == Actor.id)
        .join(Issue, PolicyObservation.issue_id == Issue.id)
        .where(Actor.code == actor_code, Issue.code == issue_code)
        .order_by(PolicyObservation.observed_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": r.id,
            "observed_at": r.observed_at.isoformat(),
            "track": r.track,
            "channel": r.channel,
            "cost_class": r.cost_class,
            "speaker_level": r.speaker_level,
            "language": r.language,
            "score": r.score,
            "source_grade": r.source_grade,
            "model_confidence": r.model_confidence,
            "text_excerpt": r.text_excerpt,
            "text_excerpt_en": r.text_excerpt_en,
            "provenance": r.provenance,
            "verification": r.verification,
            "is_synthetic": r.is_synthetic,
        }
        for r in db.scalars(stmt).all()
    ]
