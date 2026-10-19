"""Load the seed into a database and commit a 30-day forecast history."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import init_db, session_factory
from ..engine import run as engine_run
from ..models import (
    Actor,
    Forecaster,
    Indicator,
    Issue,
    PanelForecast,
    PolicyObservation,
    Question,
    Resolution,
    SeriesPoint,
    Source,
    ThreatEvent,
)
from . import ledgers, reference


def _d(s: str) -> date:
    return date.fromisoformat(s)


def load_reference(db: Session) -> None:
    for code, en, ar, kind in reference.ACTORS:
        if not db.scalar(select(Actor).where(Actor.code == code)):
            db.add(Actor(code=code, name_en=en, name_ar=ar, kind=kind))
    for code, en, ar, low, high, cap in reference.ISSUES:
        if not db.scalar(select(Issue).where(Issue.code == code)):
            db.add(Issue(code=code, name_en=en, name_ar=ar, low_label_en=low, high_label_en=high, cap_code=cap))
    for code, name, tier, kind, url, lang, note, reuse in reference.SOURCES:
        if not db.scalar(select(Source).where(Source.code == code)):
            db.add(Source(code=code, name=name, tier=tier, kind=kind, url=url, language=lang, licence_note=note, reuse_ok=reuse))
    db.commit()


def load_questions(db: Session, opened_at: date) -> None:
    for order, (code, en, ar, horizon, base, note, criteria, hooks) in enumerate(reference.QUESTIONS):
        q = db.scalar(select(Question).where(Question.code == code))
        if q is None:
            q = Question(
                code=code, title_en=en, title_ar=ar, horizon_days=horizon, base_rate=base, base_rate_note=note,
                resolution_criteria=criteria, decision_hooks=hooks, status="open", opened_at=opened_at,
                resolves_at=opened_at + timedelta(days=horizon), order=order,
            )
            db.add(q)
            db.flush()
        ar = reference.QUESTIONS_AR.get(code)
        if ar and not q.resolution_criteria_ar:
            q.resolution_criteria_ar, q.decision_hooks_ar = ar[0], ar[1]
        # indicators added to the reference after a database was created are appended (never overwritten:
        # an analyst's edits to an existing indicator stand)
        have = {i.code for i in q.indicators}
        for icode, iname, iname_ar, lrp, lra, polarity, rule in reference.INDICATORS.get(code, []):
            if icode in have:
                continue
            db.add(Indicator(question_id=q.id, code=icode, name_en=iname, name_ar=iname_ar, lr_present=lrp, lr_absent=lra, polarity=polarity, rule=rule))
    for order, (code, en, ar, horizon, base, criteria, opened, resolved, outcome, notes) in enumerate(reference.RESOLVED_QUESTIONS, start=100):
        q = db.scalar(select(Question).where(Question.code == code))
        if q is None:
            q = Question(
                code=code, title_en=en, title_ar=ar, horizon_days=horizon, base_rate=base,
                base_rate_note="Demo resolved question used to exercise the calibration page.",
                resolution_criteria=criteria, decision_hooks=[], status="resolved", opened_at=_d(opened),
                resolves_at=_d(resolved), order=order,
            )
            db.add(q)
            db.flush()
            # Borrow indicators from the live question that shares the subject so the engine has something to read.
            twin = {
                "hormuz_depressed_through_jun_2026": "hormuz_closure_90",
                "ceasefire_holds_through_jul_2026": "gulf_infra_strike_90",
                "houthi_saudi_strike_by_sep_2026": "yemen_escalation_sa_90",
                "jwc_adds_gcc_states_q1_2026": "hormuz_closure_90",
            }[code]
            invert = code == "ceasefire_holds_through_jul_2026"
            for icode, iname, iname_ar, lrp, lra, polarity, rule in reference.INDICATORS[twin]:
                if invert:
                    lrp, lra = (1 / lrp), (1 / lra)
                db.add(Indicator(question_id=q.id, code=icode, name_en=iname, name_ar=iname_ar, lr_present=lrp, lr_absent=lra, polarity=polarity, rule=rule))
            db.add(Resolution(question_id=q.id, resolved_at=_d(resolved), outcome=outcome, notes=notes, resolved_by="seed"))
    db.commit()


def load_ledgers(db: Session, as_of: date) -> None:
    actors = {a.code: a.id for a in db.scalars(select(Actor)).all()}
    issues = {i.code: i.id for i in db.scalars(select(Issue)).all()}
    if db.scalar(select(ThreatEvent).limit(1)) is None:
        for (d, etype, loc, country, actor, target, fat, sev, desc, prov, synth) in ledgers.EVENTS:
            db.add(ThreatEvent(
                event_date=_d(d), event_type=etype, location_name=loc, country=country,
                actor_id=actors.get(actor) if actor else None, target_actor_id=actors.get(target) if target else None,
                fatalities=fat, severity=sev, description_en=desc, provenance=prov,
                verification="verified" if not synth else "pending", verified_by="seed" if not synth else None,
                is_synthetic=synth,
            ))
    if db.scalar(select(SeriesPoint).limit(1)) is None:
        # the shipped snapshot carries the sourced record (PortWatch, JMIC, UKMTO, sanctions lists);
        # synthetic shaping is generated only for series the snapshot does not cover
        from . import snapshot

        db.flush()
        snapshot.load(db, include_observations=False)
        have = {s for (s,) in db.execute(select(SeriesPoint.series).distinct())}
        start = date(2025, 1, 1)
        if "hormuz_transits" not in have:
            for d, v, synth in ledgers.hormuz_transit_series(start, as_of):
                db.add(SeriesPoint(series="hormuz_transits", date=d, value=v, unit="transits_per_day", source="demo series shaped by PortWatch anchors", is_synthetic=synth))
        if "bab_el_mandeb_transits" not in have:
            for d, v, synth in ledgers.bab_el_mandeb_series(start, as_of):
                db.add(SeriesPoint(series="bab_el_mandeb_transits", date=d, value=v, unit="transits_per_day", source="demo series", is_synthetic=synth))
        existing = {(s, d) for s, d in db.execute(select(SeriesPoint.series, SeriesPoint.date))}
        for d, series, v, unit, src, synth in ledgers.SERIES_ANCHORS:
            if (series, _d(d)) in existing:
                continue
            db.add(SeriesPoint(series=series, date=_d(d), value=v, unit=unit, source=src, is_synthetic=synth))
    if db.scalar(select(PolicyObservation).limit(1)) is None:
        for (d, actor, issue, track, channel, cost, level, lang, score, grade, excerpt, excerpt_en, prov, synth) in ledgers.OBSERVATIONS:
            db.add(PolicyObservation(
                actor_id=actors[actor], issue_id=issues[issue], observed_at=_d(d), track=track, channel=channel,
                cost_class=cost, speaker_level=level, language=lang, score=score, source_grade=grade,
                model_confidence=1.0, text_excerpt=excerpt, text_excerpt_en=excerpt_en, provenance=prov,
                verification="verified" if not synth else "pending", verified_by="seed" if not synth else None,
                is_synthetic=synth,
            ))
        db.flush()
        from . import snapshot

        snapshot.load(db, include_series=False, include_events=False)
    if db.scalar(select(Forecaster).limit(1)) is None:
        for code, name, kind, w in ledgers.FORECASTERS:
            db.add(Forecaster(code=code, name=name, kind=kind, skill_weight=w))
        db.flush()
        seats = {f.code: f.id for f in db.scalars(select(Forecaster)).all()}
        for qcode, entries in ledgers.PANEL_ROUND.items():
            q = db.scalar(select(Question).where(Question.code == qcode))
            if q is None:
                continue
            for seat, p in entries:
                # two rounds: a week ago and four weeks ago, with a small drift, so the spread shows movement
                db.add(PanelForecast(question_id=q.id, forecaster_id=seats[seat], as_of=as_of - timedelta(days=7), probability=p, rationale="Demo round."))
                db.add(PanelForecast(question_id=q.id, forecaster_id=seats[seat], as_of=as_of - timedelta(days=28), probability=max(0.02, min(0.98, p - 0.06)), rationale="Demo round."))
    db.commit()


def commit_history(db: Session, as_of: date, days: int = 30) -> None:
    for q in db.scalars(select(Question).where(Question.status == "open")).all():
        for i in range(days, -1, -1):
            engine_run.commit(db, q, as_of - timedelta(days=i))
    # resolved demo questions: forecasts at T-90, T-60, T-30 relative to resolution
    for q in db.scalars(select(Question).where(Question.status == "resolved")).all():
        for back in (90, 60, 30):
            d = q.resolves_at - timedelta(days=back)
            if d >= q.opened_at - timedelta(days=60):
                engine_run.commit(db, q, d)


def seed(as_of: date | None = None, history_days: int = 30) -> None:
    init_db()
    as_of = as_of or date.today()
    db = session_factory()()
    try:
        load_reference(db)
        load_questions(db, as_of - timedelta(days=history_days))
        load_ledgers(db, as_of)
        from ..engine import incidents
        from ..pipelines.connectors import ukmto

        ukmto.tidy_descriptions(db)
        incidents.link(db, since=date(2024, 1, 1), until=as_of + timedelta(days=1))
        commit_history(db, as_of, history_days)
    finally:
        db.close()


if __name__ == "__main__":
    import sys

    as_of = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    seed(as_of)
    print(f"seeded as of {as_of}")
