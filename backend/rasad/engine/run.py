"""Compute and commit a forecast for a question on a given day.

Steps: evaluate every indicator -> Bayesian posterior from the base rate -> aggregate the
panel's latest forecasts -> blend -> commit to the hash chain. The decomposition stored with
the commit is exactly what the board shows when a number is opened.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Forecast, Indicator, IndicatorState, PanelForecast, Question, Resolution
from . import bayes, indicators, panel
from .commitment import commit_hash


def latest_panel(db: Session, question_id: int, as_of: date, max_age_days: int = 21) -> list[tuple[float, float]]:
    """Each forecaster's most recent forecast within max_age_days of as_of."""
    rows = db.scalars(
        select(PanelForecast)
        .where(PanelForecast.question_id == question_id, PanelForecast.as_of <= as_of, PanelForecast.as_of > as_of - timedelta(days=max_age_days))
        .order_by(PanelForecast.as_of.desc())
    ).all()
    seen: dict[int, tuple[float, float]] = {}
    for r in rows:
        if r.forecaster_id not in seen:
            seen[r.forecaster_id] = (r.probability, r.forecaster.skill_weight)
    return list(seen.values())


def evaluate_question(db: Session, question: Question, as_of: date, *, persist_states: bool = True) -> dict:
    settings = get_settings()
    states: list[tuple[str, str, float, float, dict]] = []
    for ind in question.indicators:
        ev = indicators.evaluate(db, ind, as_of)
        states.append((ind.code, ev.state, ind.lr_present, ind.lr_absent, ev.evidence))
        if persist_states:
            existing = db.scalar(select(IndicatorState).where(IndicatorState.indicator_id == ind.id, IndicatorState.as_of == as_of))
            if existing:
                existing.state, existing.evidence = ev.state, ev.evidence
            else:
                db.add(IndicatorState(indicator_id=ind.id, as_of=as_of, state=ev.state, evidence=ev.evidence))
    post = bayes.update(question.base_rate, states, floor=settings.probability_floor, ceiling=settings.probability_ceiling)
    pf = latest_panel(db, question.id, as_of)
    summary = panel.aggregate(pf, extremise=settings.panel_extremising_exponent, floor=settings.probability_floor, ceiling=settings.probability_ceiling)
    final = panel.combine(post.probability, summary.probability if summary else None, settings.machine_weight)
    final = bayes.clamp_probability(final, settings.probability_floor, settings.probability_ceiling)
    return {
        "question": question.code,
        "as_of": as_of.isoformat(),
        "machine": post.as_dict(),
        "panel": summary.as_dict() if summary else None,
        "machine_weight": settings.machine_weight if summary else 1.0,
        "final_prob": round(final, 4),
    }


def commit(db: Session, question: Question, as_of: date) -> Forecast:
    existing = db.scalar(select(Forecast).where(Forecast.question_id == question.id, Forecast.as_of == as_of))
    if existing:
        return existing
    result = evaluate_question(db, question, as_of)
    prev = db.scalar(select(Forecast).order_by(Forecast.id.desc()).limit(1))
    prev_hash = prev.commit_hash if prev else None
    decomposition = {k: v for k, v in result.items() if k not in {"final_prob"}}
    h = commit_hash(prev_hash, question.code, as_of, result["final_prob"], decomposition)
    fc = Forecast(
        question_id=question.id,
        as_of=as_of,
        machine_prob=result["machine"]["probability"],
        panel_prob=result["panel"]["probability"] if result["panel"] else None,
        final_prob=result["final_prob"],
        decomposition=decomposition,
        prev_hash=prev_hash,
        commit_hash=h,
    )
    db.add(fc)
    db.commit()
    return fc


def commit_all_open(db: Session, as_of: date) -> list[Forecast]:
    out = []
    for q in db.scalars(select(Question).where(Question.status == "open").order_by(Question.order)).all():
        out.append(commit(db, q, as_of))
    return out


def history(db: Session, question_id: int, days: int = 30, as_of: date | None = None) -> list[dict]:
    as_of = as_of or date.today()
    rows = db.scalars(
        select(Forecast).where(Forecast.question_id == question_id, Forecast.as_of > as_of - timedelta(days=days), Forecast.as_of <= as_of).order_by(Forecast.as_of)
    ).all()
    return [{"as_of": r.as_of.isoformat(), "final_prob": r.final_prob, "machine_prob": r.machine_prob, "panel_prob": r.panel_prob} for r in rows]


def resolved_pairs(db: Session, *, horizon_days: int | None = None) -> list[tuple[float, float, bool]]:
    """(forecast, baseline, outcome) for scoring: the forecast made horizon_days before
    resolution, or the earliest committed forecast when no horizon is given."""
    out = []
    for res in db.scalars(select(Resolution)).all():
        q = db.get(Question, res.question_id)
        if q is None:
            continue
        stmt = select(Forecast).where(Forecast.question_id == q.id)
        if horizon_days is not None:
            target = res.resolved_at - timedelta(days=horizon_days)
            stmt = stmt.where(Forecast.as_of <= target).order_by(Forecast.as_of.desc())
        else:
            stmt = stmt.order_by(Forecast.as_of)
        fc = db.scalar(stmt.limit(1))
        if fc is None:
            continue
        out.append((fc.final_prob, q.base_rate, res.outcome))
    return out
