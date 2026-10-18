"""Analyst workflows: question and indicator editing, panel forecasts, evidence entry,
resolution and tasking. Every write is audited and attributed to the signed-in user."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import core as auth
from ..auth.models import User
from ..db import get_session
from ..engine import indicators as ind_engine
from ..engine import run as engine_run
from ..models import Actor, Forecaster, Indicator, Issue, PanelForecast, PolicyObservation, Question, Resolution, SeriesPoint, TaskingRequest, ThreatEvent
from .deps import current_user, require_role

router = APIRouter(prefix="/api", tags=["workflow"])

RULE_TYPES = set(ind_engine.RULES)
EVENT_TYPES = [
    "missile_strike", "drone_strike", "rocket_attack", "maritime_attack", "maritime_harassment", "seizure", "mine_warning",
    "gnss_interference", "maritime_advisory", "intercept", "closure", "ceasefire", "designation", "insurer_listing",
    "deployment", "expulsion", "statement_threat", "cyber_incident", "intra_gcc_recall", "exercise", "other",
]
COST_CLASSES = ["cheap_talk", "hands_tying", "sunk_cost", "revealed_action"]
SPEAKER_LEVELS = ["head_of_state", "minister", "institution", "spokesperson", "legislature", "media", "other"]
CHANNELS = ["statement", "speech", "interview", "communique", "notification", "deployment", "event", "document", "analyst"]


def _q(db: Session, code: str) -> Question:
    q = db.scalar(select(Question).where(Question.code == code))
    if q is None:
        raise HTTPException(404, "question not found")
    return q


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


class IndicatorIn(BaseModel):
    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_]+$")
    name_en: str = Field(min_length=3, max_length=200)
    name_ar: str | None = None
    description: str | None = None
    lr_present: float = Field(gt=0, le=10)
    lr_absent: float = Field(gt=0, le=10)
    polarity: str = Field(default="emerging", pattern="^(emerging|not_emerging)$")
    rule: dict


class QuestionIn(BaseModel):
    code: str = Field(min_length=3, max_length=48, pattern=r"^[a-z0-9_]+$")
    title_en: str = Field(min_length=10, max_length=300)
    title_ar: str | None = None
    horizon_days: int = Field(ge=7, le=730)
    resolution_criteria: str = Field(min_length=10)
    decision_hooks: list[str] = []
    base_rate: float = Field(gt=0.0, lt=1.0)
    base_rate_note: str | None = None
    opened_at: str | None = None
    indicators: list[IndicatorIn] = []


class QuestionUpdate(BaseModel):
    title_en: str | None = None
    title_ar: str | None = None
    horizon_days: int | None = Field(default=None, ge=7, le=730)
    resolution_criteria: str | None = None
    decision_hooks: list[str] | None = None
    base_rate: float | None = Field(default=None, gt=0.0, lt=1.0)
    base_rate_note: str | None = None
    resolves_at: str | None = None
    order: int | None = None


def _validate_rule(rule: dict) -> None:
    t = rule.get("type")
    if t not in RULE_TYPES:
        raise HTTPException(400, f"rule type must be one of {sorted(RULE_TYPES)}")
    need = {
        "event_count": ["event_types"], "series_threshold": ["series", "op", "value"], "series_change": ["series", "op", "ratio"],
        "position_level": ["actor", "issue", "op", "value"], "divergence": ["actor", "issue", "op", "value"], "silence": ["actor", "issue"],
        "change_point": ["actor", "issue", "track"],
    }[t]
    missing = [k for k in need if k not in rule]
    if missing:
        raise HTTPException(400, f"rule {t} needs {missing}")
    if "op" in rule and rule["op"] not in ind_engine.OPS:
        raise HTTPException(400, f"op must be one of {sorted(ind_engine.OPS)}")


def _question_row(q: Question) -> dict:
    return {
        "code": q.code, "title_en": q.title_en, "title_ar": q.title_ar, "horizon_days": q.horizon_days, "resolution_criteria": q.resolution_criteria,
        "decision_hooks": q.decision_hooks, "base_rate": q.base_rate, "base_rate_note": q.base_rate_note, "status": q.status,
        "opened_at": q.opened_at.isoformat(), "resolves_at": q.resolves_at.isoformat(), "order": q.order,
        "indicators": [
            {"id": i.id, "code": i.code, "name_en": i.name_en, "name_ar": i.name_ar, "description": i.description, "lr_present": i.lr_present, "lr_absent": i.lr_absent, "polarity": i.polarity, "rule": i.rule}
            for i in q.indicators
        ],
    }


@router.get("/questions")
def list_questions(db: Session = Depends(get_session), user: User = Depends(current_user)) -> list[dict]:
    return [_question_row(q) for q in db.scalars(select(Question).order_by(Question.status, Question.order)).all()]


@router.get("/questions/{code}/definition")
def question_definition(code: str, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    return _question_row(_q(db, code))


@router.post("/questions", status_code=201)
def create_question(req: QuestionIn, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    if db.scalar(select(Question).where(Question.code == req.code)):
        raise HTTPException(409, "a question with that code exists")
    opened = date.fromisoformat(req.opened_at) if req.opened_at else date.today()
    order = (db.scalar(select(func.max(Question.order))) or 0) + 1
    q = Question(
        code=req.code, title_en=req.title_en, title_ar=req.title_ar, horizon_days=req.horizon_days, resolution_criteria=req.resolution_criteria,
        decision_hooks=req.decision_hooks, base_rate=req.base_rate, base_rate_note=req.base_rate_note, status="open", opened_at=opened,
        resolves_at=opened + timedelta(days=req.horizon_days), order=order,
    )
    db.add(q)
    db.flush()
    for ind in req.indicators:
        _validate_rule(ind.rule)
        db.add(Indicator(question_id=q.id, **ind.model_dump()))
    db.commit()
    auth.audit(db, user, "question_created", q.code, {"title": q.title_en[:120], "indicators": len(req.indicators)})
    return _question_row(_q(db, q.code))


@router.put("/questions/{code}")
def update_question(code: str, req: QuestionUpdate, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    q = _q(db, code)
    if q.status != "open":
        raise HTTPException(409, "resolved questions are frozen; open a new question instead")
    changed = {}
    for k, v in req.model_dump(exclude_none=True).items():
        if k == "resolves_at":
            v = date.fromisoformat(v)
        setattr(q, k, v)
        changed[k] = str(v)[:120]
    if "horizon_days" in changed and "resolves_at" not in changed:
        q.resolves_at = q.opened_at + timedelta(days=q.horizon_days)
    db.commit()
    auth.audit(db, user, "question_updated", code, changed)
    return _question_row(q)


class ResolveIn(BaseModel):
    outcome: bool
    notes: str | None = None
    resolved_at: str | None = None


@router.post("/questions/{code}/resolve")
def resolve_question(code: str, req: ResolveIn, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    q = _q(db, code)
    if q.status == "resolved":
        raise HTTPException(409, "already resolved")
    when = date.fromisoformat(req.resolved_at) if req.resolved_at else date.today()
    # a final forecast on the resolution day so the record shows what the platform said at the end
    engine_run.commit(db, q, when)
    db.add(Resolution(question_id=q.id, resolved_at=when, outcome=req.outcome, notes=req.notes, resolved_by=user.username))
    q.status = "resolved"
    db.commit()
    auth.audit(db, user, "question_resolved", code, {"outcome": req.outcome, "notes": (req.notes or "")[:200]})
    return {"code": code, "status": q.status, "outcome": req.outcome, "resolved_at": when.isoformat()}


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------


@router.post("/questions/{code}/indicators", status_code=201)
def add_indicator(code: str, req: IndicatorIn, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    q = _q(db, code)
    if any(i.code == req.code for i in q.indicators):
        raise HTTPException(409, "indicator code exists on this question")
    _validate_rule(req.rule)
    ind = Indicator(question_id=q.id, **req.model_dump())
    db.add(ind)
    db.commit()
    auth.audit(db, user, "indicator_created", f"{code}/{req.code}", {"rule": req.rule.get("type")})
    return {"id": ind.id, **req.model_dump()}


class IndicatorUpdate(BaseModel):
    name_en: str | None = None
    name_ar: str | None = None
    description: str | None = None
    lr_present: float | None = Field(default=None, gt=0, le=10)
    lr_absent: float | None = Field(default=None, gt=0, le=10)
    polarity: str | None = Field(default=None, pattern="^(emerging|not_emerging)$")
    rule: dict | None = None


@router.put("/indicators/{ind_id}")
def update_indicator(ind_id: int, req: IndicatorUpdate, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    ind = db.get(Indicator, ind_id)
    if ind is None:
        raise HTTPException(404, "indicator not found")
    if req.rule is not None:
        _validate_rule(req.rule)
    changed = req.model_dump(exclude_none=True)
    for k, v in changed.items():
        setattr(ind, k, v)
    db.commit()
    auth.audit(db, user, "indicator_updated", f"{ind.question.code}/{ind.code}", {k: (str(v)[:80]) for k, v in changed.items()})
    return {"id": ind.id, "code": ind.code, "name_en": ind.name_en, "name_ar": ind.name_ar, "description": ind.description, "lr_present": ind.lr_present, "lr_absent": ind.lr_absent, "polarity": ind.polarity, "rule": ind.rule}


@router.delete("/indicators/{ind_id}")
def delete_indicator(ind_id: int, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    ind = db.get(Indicator, ind_id)
    if ind is None:
        raise HTTPException(404, "indicator not found")
    target = f"{ind.question.code}/{ind.code}"
    db.delete(ind)
    db.commit()
    auth.audit(db, user, "indicator_deleted", target)
    return {"deleted": ind_id}


class RulePreview(BaseModel):
    rule: dict
    as_of: str | None = None


@router.post("/indicators/preview")
def preview_rule(req: RulePreview, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    _validate_rule(req.rule)
    d = date.fromisoformat(req.as_of) if req.as_of else date.today()
    stub = Indicator(code="preview", name_en="preview", lr_present=1.0, lr_absent=1.0, rule=req.rule)
    st = ind_engine.evaluate(db, stub, d)
    # a short history so the author sees how often the rule fires
    history = []
    for back in (90, 60, 30, 14, 7, 0):
        dd = d - timedelta(days=back)
        history.append({"as_of": dd.isoformat(), "state": ind_engine.evaluate(db, stub, dd).state})
    return {"as_of": d.isoformat(), "state": st.state, "evidence": st.evidence, "history": history}


@router.get("/reference/vocab")
def vocab(db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    series = [s for (s,) in db.execute(select(SeriesPoint.series).distinct().order_by(SeriesPoint.series))]
    return {
        "rule_types": sorted(RULE_TYPES), "event_types": EVENT_TYPES, "cost_classes": COST_CLASSES, "speaker_levels": SPEAKER_LEVELS, "channels": CHANNELS,
        "ops": sorted(ind_engine.OPS), "series": series,
        "actors": [{"code": a.code, "name_en": a.name_en, "name_ar": a.name_ar} for a in db.scalars(select(Actor).order_by(Actor.code))],
        "issues": [{"code": i.code, "name_en": i.name_en, "name_ar": i.name_ar} for i in db.scalars(select(Issue).order_by(Issue.code))],
        "countries": ["SA", "AE", "QA", "KW", "BH", "OM", "IQ", "IR", "YE", "IL", "SO", "HORMUZ", "RED_SEA", "GULF_OF_ADEN", "ARABIAN_GULF"],
    }


# ---------------------------------------------------------------------------
# Panel forecasts
# ---------------------------------------------------------------------------


def _seat_for(db: Session, user: User) -> Forecaster:
    code = f"user:{user.username}"
    f = db.scalar(select(Forecaster).where(Forecaster.code == code))
    if f is None:
        f = Forecaster(code=code, name=user.display_name, kind="human", skill_weight=1.0)
        db.add(f)
        db.flush()
    return f


class PanelIn(BaseModel):
    probability: float = Field(gt=0.0, lt=1.0)
    rationale: str | None = None
    as_of: str | None = None


@router.get("/questions/{code}/panel")
def panel(code: str, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    q = _q(db, code)
    rows = db.scalars(select(PanelForecast).where(PanelForecast.question_id == q.id).order_by(PanelForecast.as_of.desc(), PanelForecast.id.desc())).all()
    latest: dict[int, PanelForecast] = {}
    for r in rows:
        latest.setdefault(r.forecaster_id, r)
    mine = next((r for r in rows if r.forecaster.code == f"user:{user.username}"), None)
    return {
        "question": code,
        "latest": [{"forecaster": r.forecaster.name, "code": r.forecaster.code, "as_of": r.as_of.isoformat(), "probability": r.probability, "rationale": r.rationale, "skill_weight": r.forecaster.skill_weight} for r in latest.values()],
        "mine": {"as_of": mine.as_of.isoformat(), "probability": mine.probability, "rationale": mine.rationale} if mine else None,
        "history": [{"forecaster": r.forecaster.name, "as_of": r.as_of.isoformat(), "probability": r.probability} for r in rows[:200]],
    }


@router.post("/questions/{code}/panel", status_code=201)
def submit_panel(code: str, req: PanelIn, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    q = _q(db, code)
    if q.status != "open":
        raise HTTPException(409, "question is resolved")
    seat = _seat_for(db, user)
    d = date.fromisoformat(req.as_of) if req.as_of else date.today()
    existing = db.scalar(select(PanelForecast).where(PanelForecast.question_id == q.id, PanelForecast.forecaster_id == seat.id, PanelForecast.as_of == d))
    if existing:
        existing.probability, existing.rationale = req.probability, req.rationale
    else:
        db.add(PanelForecast(question_id=q.id, forecaster_id=seat.id, as_of=d, probability=req.probability, rationale=req.rationale))
    db.commit()
    auth.audit(db, user, "panel_forecast", code, {"p": req.probability, "as_of": d.isoformat()})
    return {"question": code, "forecaster": seat.name, "as_of": d.isoformat(), "probability": req.probability}


# ---------------------------------------------------------------------------
# Evidence entry
# ---------------------------------------------------------------------------


class EventIn(BaseModel):
    event_date: str
    event_type: str
    description_en: str = Field(min_length=10)
    description_ar: str | None = None
    location_name: str | None = None
    country: str | None = None
    lat: float | None = None
    lon: float | None = None
    actor: str | None = None
    target: str | None = None
    fatalities: int | None = None
    severity: int = Field(default=2, ge=1, le=5)
    source: str = Field(min_length=3)
    url: str | None = None
    grade: str = Field(default="B2", pattern=r"^[A-F][1-6]$")
    verified: bool = True


def _event_dict(e: ThreatEvent) -> dict:
    return {"id": e.id, "event_date": e.event_date.isoformat(), "event_type": e.event_type, "country": e.country, "location_name": e.location_name, "severity": e.severity, "description_en": e.description_en, "provenance": e.provenance, "verification": e.verification}


@router.post("/events", status_code=201)
def create_event(req: EventIn, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    if req.event_type not in EVENT_TYPES:
        raise HTTPException(400, f"event_type must be one of {EVENT_TYPES}")
    actor = db.scalar(select(Actor).where(Actor.code == req.actor)) if req.actor else None
    target = db.scalar(select(Actor).where(Actor.code == req.target)) if req.target else None
    e = ThreatEvent(
        event_date=date.fromisoformat(req.event_date), event_type=req.event_type, location_name=req.location_name, country=req.country, lat=req.lat, lon=req.lon,
        actor_id=actor.id if actor else None, target_actor_id=target.id if target else None, fatalities=req.fatalities, severity=req.severity,
        description_en=req.description_en, description_ar=req.description_ar,
        provenance={"source": req.source, "url": req.url or "", "grade": req.grade, "entered_by": user.username},
        verification="verified" if req.verified else "pending", verified_by=user.username if req.verified else None, verified_at=datetime.utcnow() if req.verified else None,
    )
    db.add(e)
    db.commit()
    auth.audit(db, user, "event_entered", str(e.id), {"type": e.event_type, "date": req.event_date})
    return _event_dict(e)


class EventUpdate(BaseModel):
    event_date: str | None = None
    event_type: str | None = None
    description_en: str | None = None
    location_name: str | None = None
    country: str | None = None
    severity: int | None = Field(default=None, ge=1, le=5)
    lat: float | None = None
    lon: float | None = None


@router.put("/events/{event_id}")
def update_event(event_id: int, req: EventUpdate, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    e = db.get(ThreatEvent, event_id)
    if e is None:
        raise HTTPException(404, "event not found")
    changed = req.model_dump(exclude_none=True)
    if "event_type" in changed and changed["event_type"] not in EVENT_TYPES:
        raise HTTPException(400, "unknown event_type")
    for k, v in changed.items():
        setattr(e, k, date.fromisoformat(v) if k == "event_date" else v)
    prov = dict(e.provenance or {})
    prov.setdefault("edits", []).append({"by": user.username, "at": datetime.utcnow().isoformat(timespec="seconds"), "fields": sorted(changed)})
    e.provenance = prov
    db.commit()
    auth.audit(db, user, "event_edited", str(event_id), {k: str(v)[:80] for k, v in changed.items()})
    return _event_dict(e)


class ObservationIn(BaseModel):
    actor: str
    issue: str
    observed_at: str
    track: str = Field(pattern="^(stated|revealed)$")
    channel: str = "statement"
    cost_class: str = "cheap_talk"
    speaker_level: str = "institution"
    language: str = "en"
    score: float = Field(ge=-1.0, le=1.0)
    source_grade: str = Field(default="B2", pattern=r"^[A-F][1-6]$")
    text_excerpt: str = Field(min_length=5)
    text_excerpt_en: str | None = None
    source: str = Field(min_length=3)
    url: str | None = None
    verified: bool = True


@router.post("/observations", status_code=201)
def create_observation(req: ObservationIn, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    actor = db.scalar(select(Actor).where(Actor.code == req.actor))
    issue = db.scalar(select(Issue).where(Issue.code == req.issue))
    if actor is None or issue is None:
        raise HTTPException(400, "unknown actor or issue")
    if req.cost_class not in COST_CLASSES or req.speaker_level not in SPEAKER_LEVELS:
        raise HTTPException(400, "unknown cost_class or speaker_level")
    o = PolicyObservation(
        actor_id=actor.id, issue_id=issue.id, observed_at=date.fromisoformat(req.observed_at), track=req.track, channel=req.channel, cost_class=req.cost_class,
        speaker_level=req.speaker_level, language=req.language, score=req.score, source_grade=req.source_grade, model_confidence=1.0,
        text_excerpt=req.text_excerpt, text_excerpt_en=req.text_excerpt_en, provenance={"source": req.source, "url": req.url or "", "grade": req.source_grade, "entered_by": user.username},
        verification="verified" if req.verified else "pending", verified_by=user.username if req.verified else None, verified_at=datetime.utcnow() if req.verified else None,
    )
    db.add(o)
    db.commit()
    auth.audit(db, user, "observation_entered", str(o.id), {"actor": req.actor, "issue": req.issue, "score": req.score})
    return {"id": o.id, "actor": req.actor, "issue": req.issue, "observed_at": req.observed_at, "track": o.track, "score": o.score, "verification": o.verification}


class SeriesPointIn(BaseModel):
    series: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9_]+$")
    date: str
    value: float
    unit: str = Field(min_length=1, max_length=32)
    source: str = Field(min_length=3, max_length=120)


@router.post("/series", status_code=201)
def add_series_point(req: SeriesPointIn, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    d = date.fromisoformat(req.date)
    p = db.scalar(select(SeriesPoint).where(SeriesPoint.series == req.series, SeriesPoint.date == d))
    if p:
        p.value, p.unit, p.source, p.is_synthetic = req.value, req.unit, f"{req.source} (entered by {user.username})", False
    else:
        p = SeriesPoint(series=req.series, date=d, value=req.value, unit=req.unit, source=f"{req.source} (entered by {user.username})", is_synthetic=False)
        db.add(p)
    db.commit()
    auth.audit(db, user, "series_point_entered", req.series, {"date": req.date, "value": req.value})
    return {"series": req.series, "date": req.date, "value": req.value}


# ---------------------------------------------------------------------------
# Tasking: open -> framed (linked to a question) -> answered
# ---------------------------------------------------------------------------


class FrameIn(BaseModel):
    question_code: str


@router.post("/tasking/{task_id}/frame")
def frame_tasking(task_id: int, req: FrameIn, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    t = db.get(TaskingRequest, task_id)
    if t is None:
        raise HTTPException(404, "tasking not found")
    q = _q(db, req.question_code)
    t.question_id, t.status = q.id, "framed"
    db.commit()
    auth.audit(db, user, "tasking_framed", str(task_id), {"question": q.code})
    return {"id": t.id, "status": t.status, "question": q.code}


class AnswerIn(BaseModel):
    answer_md: str = Field(min_length=10)


@router.post("/tasking/{task_id}/answer")
def answer_tasking(task_id: int, req: AnswerIn, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    t = db.get(TaskingRequest, task_id)
    if t is None:
        raise HTTPException(404, "tasking not found")
    t.answer_md, t.status, t.answered_at = req.answer_md, "answered", datetime.utcnow()
    db.commit()
    auth.audit(db, user, "tasking_answered", str(task_id))
    return {"id": t.id, "status": t.status, "answered_at": t.answered_at.isoformat()}
