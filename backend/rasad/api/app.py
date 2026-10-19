from __future__ import annotations

import os
from datetime import date, datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .. import __version__
from ..auth import core as auth
from ..auth.models import User
from ..briefs import generate as briefs
from ..db import get_session, init_db, session_factory
from ..engine import alerts as alert_engine
from ..engine import run as engine_run
from ..engine import scoring
from ..engine.commitment import verify_chain
from ..models import (
    Actor,
    Alert,
    Brief,
    Document,
    Forecast,
    Indicator,
    IndicatorState,
    Issue,
    PolicyObservation,
    Question,
    Resolution,
    SeriesPoint,
    Source,
    TaskingRequest,
    ThreatEvent,
)
from ..policy import book as policy_book
from . import admin_routes, auth_routes, daily_routes, workflow_routes
from .. import licence
from .deps import client_ip, current_user, require_role

app = FastAPI(title="Rasad API", version=__version__)
_dev_origins = [o.strip() for o in os.getenv("RASAD_CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_dev_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_routes.router)
app.include_router(workflow_routes.router)
app.include_router(daily_routes.router)
app.include_router(admin_routes.router)
PUBLIC_RECORD = os.getenv("RASAD_PUBLIC_RECORD", "false").lower() in ("1", "true", "yes")


@app.on_event("startup")
def _startup() -> None:
    init_db()
    db = session_factory()()
    try:
        generated = auth.bootstrap_admin(db)
        if generated:
            print("Rasad: created the first admin account; its password is in <data_dir>/admin-password.txt", flush=True)
    finally:
        db.close()


def _as_of(v: str | None) -> date:
    return date.fromisoformat(v) if v else date.today()


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@app.get("/api/status")
def status(db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    synthetic = (db.scalar(select(func.count(ThreatEvent.id)).where(ThreatEvent.is_synthetic)) or 0) + (
        db.scalar(select(func.count(PolicyObservation.id)).where(PolicyObservation.is_synthetic)) or 0
    ) + (db.scalar(select(func.count(SeriesPoint.id)).where(SeriesPoint.is_synthetic)) or 0)
    last = db.scalar(select(func.max(Forecast.as_of)))
    return {
        "version": __version__,
        "events": db.scalar(select(func.count(ThreatEvent.id))),
        "observations": db.scalar(select(func.count(PolicyObservation.id))),
        "series_points": db.scalar(select(func.count(SeriesPoint.id))),
        "forecasts": db.scalar(select(func.count(Forecast.id))),
        "open_questions": db.scalar(select(func.count(Question.id)).where(Question.status == "open")),
        "pending_verification": (db.scalar(select(func.count(ThreatEvent.id)).where(ThreatEvent.verification == "pending")) or 0)
        + (db.scalar(select(func.count(PolicyObservation.id)).where(PolicyObservation.verification == "pending")) or 0),
        "synthetic_rows": synthetic,
        "last_commit": last.isoformat() if last else None,
        "open_alerts": db.scalar(select(func.count(Alert.id)).where(Alert.acknowledged_at.is_(None))) or 0,
        "marking": admin_routes.get_setting(db, "marking"),
        "org_name": admin_routes.get_setting(db, "org_name"),
        "product_name": admin_routes.get_setting(db, "product_name"),
        "licence": licence.current().as_dict(),
    }


# ---------------------------------------------------------------------------
# Board and questions
# ---------------------------------------------------------------------------


def _question_summary(db: Session, q: Question, as_of: date) -> dict:
    fc = db.scalar(select(Forecast).where(Forecast.question_id == q.id, Forecast.as_of <= as_of).order_by(Forecast.as_of.desc()).limit(1))
    hist = engine_run.history(db, q.id, 30, as_of)
    contributions = (fc.decomposition or {}).get("machine", {}).get("contributions", []) if fc else []
    movers = sorted((c for c in contributions if c["state"] != "unknown"), key=lambda c: abs(c["log_lr"]), reverse=True)[:3]
    names = {i.code: (i.name_en, i.name_ar) for i in q.indicators}
    synth = max([float((c.get("evidence") or {}).get("synthetic_share", 0.0)) for c in contributions] + [1.0 if (c.get("evidence") or {}).get("is_synthetic") else 0.0 for c in contributions] + [0.0])
    return {
        "code": q.code,
        "title_en": q.title_en,
        "title_ar": q.title_ar,
        "horizon_days": q.horizon_days,
        "base_rate": q.base_rate,
        "status": q.status,
        "resolves_at": q.resolves_at.isoformat(),
        "decision_hooks": q.decision_hooks,
        "final_prob": fc.final_prob if fc else None,
        "machine_prob": fc.machine_prob if fc else None,
        "panel_prob": fc.panel_prob if fc else None,
        "as_of": fc.as_of.isoformat() if fc else None,
        "delta_30d": round((fc.final_prob - hist[0]["final_prob"]) * 100, 1) if fc and hist else 0.0,
        "history": hist,
        "movers": [
            {"indicator": c["indicator"], "name_en": names.get(c["indicator"], (c["indicator"], None))[0], "name_ar": names.get(c["indicator"], (None, None))[1], "state": c["state"], "log_lr": c["log_lr"]}
            for c in movers
        ],
        "synthetic_share": round(synth, 2),
        "commit_hash": fc.commit_hash if fc else None,
    }


@app.get("/api/board")
def board(as_of: str | None = None, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    d = _as_of(as_of)
    qs = db.scalars(select(Question).where(Question.status == "open").order_by(Question.order)).all()
    return {"as_of": d.isoformat(), "questions": [_question_summary(db, q, d) for q in qs]}


@app.get("/api/questions/{code}")
def question_detail(code: str, as_of: str | None = None, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    d = _as_of(as_of)
    q = db.scalar(select(Question).where(Question.code == code))
    if q is None:
        raise HTTPException(404, "question not found")
    summary = _question_summary(db, q, d)
    fc = db.scalar(select(Forecast).where(Forecast.question_id == q.id, Forecast.as_of <= d).order_by(Forecast.as_of.desc()).limit(1))
    dec = fc.decomposition if fc else {}
    contributions = dec.get("machine", {}).get("contributions", [])
    ind_by_code = {i.code: i for i in q.indicators}
    detail = []
    for c in contributions:
        ind = ind_by_code.get(c["indicator"])
        ev = dict(c.get("evidence") or {})
        events = []
        if ev.get("event_ids"):
            for e in db.scalars(select(ThreatEvent).where(ThreatEvent.id.in_(ev["event_ids"]))).all():
                events.append(_event_row(e))
        detail.append(
            {
                "code": c["indicator"],
                "name_en": ind.name_en if ind else c["indicator"],
                "name_ar": ind.name_ar if ind else None,
                "description": ind.description if ind else None,
                "polarity": ind.polarity if ind else None,
                "lr_present": ind.lr_present if ind else None,
                "lr_absent": ind.lr_absent if ind else None,
                "rule": ind.rule if ind else None,
                "state": c["state"],
                "log_lr": c["log_lr"],
                "evidence": ev,
                "events": events,
            }
        )
    return {
        **summary,
        "resolution_criteria": q.resolution_criteria,
        "resolution_criteria_ar": q.resolution_criteria_ar,
        "decision_hooks_ar": q.decision_hooks_ar,
        "base_rate_note": q.base_rate_note,
        "opened_at": q.opened_at.isoformat(),
        "machine": dec.get("machine"),
        "panel": dec.get("panel"),
        "machine_weight": dec.get("machine_weight"),
        "indicators": detail,
        "history_90": engine_run.history(db, q.id, 90, d),
        "prev_hash": fc.prev_hash if fc else None,
    }


# ---------------------------------------------------------------------------
# Ledgers
# ---------------------------------------------------------------------------


def _event_row(e: ThreatEvent) -> dict:
    return {
        "id": e.id,
        "event_date": e.event_date.isoformat(),
        "event_type": e.event_type,
        "location_name": e.location_name,
        "country": e.country,
        "actor": e.actor.code if e.actor else None,
        "target": e.target_actor.code if e.target_actor else None,
        "fatalities": e.fatalities,
        "severity": e.severity,
        "description_en": e.description_en,
        "description_ar": e.description_ar,
        "provenance": e.provenance,
        "verification": e.verification,
        "is_synthetic": e.is_synthetic,
    }


@app.get("/api/events")
def events(days: int = 120, event_type: str | None = None, as_of: str | None = None, db: Session = Depends(get_session), user: User = Depends(current_user)) -> list[dict]:
    d = _as_of(as_of)
    stmt = select(ThreatEvent).where(ThreatEvent.event_date > d - timedelta(days=days), ThreatEvent.event_date <= d).order_by(ThreatEvent.event_date.desc())
    if event_type:
        stmt = stmt.where(ThreatEvent.event_type == event_type)
    return [_event_row(e) for e in db.scalars(stmt).all()]


@app.get("/api/series/{name}")
def series(name: str, days: int = 365, as_of: str | None = None, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    d = _as_of(as_of)
    pts = db.scalars(select(SeriesPoint).where(SeriesPoint.series == name, SeriesPoint.date > d - timedelta(days=days), SeriesPoint.date <= d).order_by(SeriesPoint.date)).all()
    return {
        "series": name,
        "unit": pts[0].unit if pts else None,
        "points": [{"date": p.date.isoformat(), "value": p.value, "is_synthetic": p.is_synthetic, "source": p.source} for p in pts],
    }


@app.get("/api/sources")
def sources(db: Session = Depends(get_session), user: User = Depends(current_user)) -> list[dict]:
    doc_stats = {
        sid: (n, last_fetch, last_pub)
        for sid, n, last_fetch, last_pub in db.execute(select(Document.source_id, func.count(Document.id), func.max(Document.fetched_at), func.max(Document.published_at)).group_by(Document.source_id))
    }
    out = []
    for s in db.scalars(select(Source).order_by(Source.tier, Source.code)).all():
        n, last_fetch, last_pub = doc_stats.get(s.id, (0, None, None))
        out.append({
            "code": s.code, "name": s.name, "tier": s.tier, "kind": s.kind, "url": s.url, "language": s.language, "licence_note": s.licence_note, "reuse_ok": s.reuse_ok,
            "documents": n, "last_fetched": last_fetch.isoformat(timespec="minutes") if last_fetch else None, "last_published": last_pub.isoformat()[:10] if last_pub else None,
        })
    return out


@app.get("/api/series")
def series_index(db: Session = Depends(get_session), user: User = Depends(current_user)) -> list[dict]:
    """Every series with its span, point count and how much of it is synthetic: the data freshness view."""
    rows = db.execute(
        select(SeriesPoint.series, func.count(SeriesPoint.id), func.min(SeriesPoint.date), func.max(SeriesPoint.date), func.sum(case((SeriesPoint.is_synthetic.is_(True), 1), else_=0)), func.max(SeriesPoint.unit))
        .group_by(SeriesPoint.series).order_by(SeriesPoint.series)
    ).all()
    out = []
    for name, n, lo, hi, synth, unit in rows:
        latest = db.scalar(select(SeriesPoint).where(SeriesPoint.series == name).order_by(SeriesPoint.date.desc()).limit(1))
        out.append({"series": name, "points": n, "first": lo.isoformat(), "last": hi.isoformat(), "synthetic": int(synth or 0), "unit": unit, "latest_value": latest.value if latest else None, "latest_source": latest.source if latest else None, "days_stale": (date.today() - hi).days})
    return out


# ---------------------------------------------------------------------------
# Position book
# ---------------------------------------------------------------------------


@app.get("/api/actors")
def actors(db: Session = Depends(get_session), user: User = Depends(current_user)) -> list[dict]:
    counts = dict(db.execute(select(PolicyObservation.actor_id, func.count(PolicyObservation.id)).group_by(PolicyObservation.actor_id)).all())
    return [
        {"code": a.code, "name_en": a.name_en, "name_ar": a.name_ar, "kind": a.kind, "observations": counts.get(a.id, 0)}
        for a in db.scalars(select(Actor).order_by(Actor.code)).all()
    ]


@app.get("/api/actors/{code}/book")
def actor_book(code: str, as_of: str | None = None, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    try:
        return policy_book.actor_book(db, code, _as_of(as_of))
    except KeyError:
        raise HTTPException(404, "actor not found")


@app.get("/api/actors/{code}/issues/{issue}/observations")
def observations(code: str, issue: str, db: Session = Depends(get_session), user: User = Depends(current_user)) -> list[dict]:
    return policy_book.observation_rows(db, code, issue)


@app.get("/api/issues")
def issues(db: Session = Depends(get_session), user: User = Depends(current_user)) -> list[dict]:
    return [
        {"code": i.code, "name_en": i.name_en, "name_ar": i.name_ar, "low_label_en": i.low_label_en, "high_label_en": i.high_label_en, "cap_code": i.cap_code}
        for i in db.scalars(select(Issue).order_by(Issue.code)).all()
    ]


# ---------------------------------------------------------------------------
# Calibration record
# ---------------------------------------------------------------------------


def _record_access(request: Request, db: Session = Depends(get_session)) -> None:
    if PUBLIC_RECORD:
        return
    current_user(request, db)


@app.get("/api/calibration")
def calibration(db: Session = Depends(get_session), _: None = Depends(_record_access)) -> dict:
    rows = db.scalars(select(Forecast).order_by(Forecast.id)).all()
    chain = [
        {"prev_hash": r.prev_hash, "question_code": r.question.code, "as_of": r.as_of, "final_prob": r.final_prob, "decomposition": r.decomposition, "commit_hash": r.commit_hash}
        for r in rows
    ]
    ok, bad = verify_chain(chain)
    by_h = {}
    for h in (30, 60, 90):
        by_h[str(h)] = scoring.summarise(engine_run.resolved_pairs(db, horizon_days=h)).as_dict()
    resolved = []
    for res in db.scalars(select(Resolution).order_by(Resolution.resolved_at.desc())).all():
        q = db.get(Question, res.question_id)
        fcs = db.scalars(select(Forecast).where(Forecast.question_id == q.id).order_by(Forecast.as_of)).all()
        resolved.append(
            {
                "code": q.code,
                "title_en": q.title_en,
                "title_ar": q.title_ar,
                "resolved_at": res.resolved_at.isoformat(),
                "outcome": res.outcome,
                "notes": res.notes,
                "base_rate": q.base_rate,
                "forecasts": [{"as_of": f.as_of.isoformat(), "final_prob": f.final_prob, "brier": scoring.brier(f.final_prob, res.outcome)} for f in fcs],
            }
        )
    return {
        "chain": {"length": len(chain), "verified": ok, "first_bad_index": bad, "head": chain[-1]["commit_hash"] if chain else None},
        "all": scoring.summarise(engine_run.resolved_pairs(db)).as_dict(),
        "by_horizon": by_h,
        "resolved": resolved,
    }


@app.get("/api/forecasts/chain")
def chain(limit: int = 200, db: Session = Depends(get_session), user: User = Depends(current_user)) -> list[dict]:
    rows = db.scalars(select(Forecast).order_by(Forecast.id.desc()).limit(limit)).all()
    return [
        {"id": r.id, "question": r.question.code, "as_of": r.as_of.isoformat(), "final_prob": r.final_prob, "prev_hash": r.prev_hash, "commit_hash": r.commit_hash, "committed_at": r.committed_at.isoformat()}
        for r in rows
    ]


class CommitRequest(BaseModel):
    as_of: str | None = None


@app.post("/api/forecasts/commit")
def commit_forecasts(req: CommitRequest, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    d = _as_of(req.as_of)
    out = engine_run.commit_all_open(db, d)
    raised = alert_engine.after_commit(db, out)
    auth.audit(db, user, "forecasts_committed", d.isoformat(), {"n": len(out), "alerts": raised})
    return {"as_of": d.isoformat(), "committed": [{"question": f.question.code, "final_prob": f.final_prob, "commit_hash": f.commit_hash} for f in out]}


# ---------------------------------------------------------------------------
# Briefs and tasking
# ---------------------------------------------------------------------------


@app.get("/api/briefs/{code}")
def brief(code: str, lang: str = Query("en", pattern="^(en|ar)$"), as_of: str | None = None, polish: bool = True, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    try:
        b = briefs.generate(db, code, _as_of(as_of), lang, polish=polish)
    except KeyError:
        raise HTTPException(404, "question not found")
    auth.audit(db, user, "brief_generated", code, {"lang": lang})
    return {"id": b.id, "question": code, "lang": b.lang, "generator": b.generator, "generated_at": b.generated_at.isoformat(), "content_md": b.content_md}


class TaskingIn(BaseModel):
    text: str
    requested_by: str | None = None


@app.post("/api/tasking")
def create_tasking(req: TaskingIn, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    t = TaskingRequest(text=req.text, requested_by=req.requested_by or user.username)
    db.add(t)
    db.commit()
    auth.audit(db, user, "tasking_created", str(t.id), {"text": req.text[:200]})
    return {"id": t.id, "status": t.status, "created_at": t.created_at.isoformat()}


@app.get("/api/tasking")
def list_tasking(db: Session = Depends(get_session), user: User = Depends(current_user)) -> list[dict]:
    return [
        {"id": t.id, "text": t.text, "requested_by": t.requested_by, "status": t.status, "created_at": t.created_at.isoformat(), "answer_md": t.answer_md,
         "answered_at": t.answered_at.isoformat() if t.answered_at else None, "question": db.get(Question, t.question_id).code if t.question_id else None}
        for t in db.scalars(select(TaskingRequest).order_by(TaskingRequest.created_at.desc())).all()
    ]


# ---------------------------------------------------------------------------
# Verification queue
# ---------------------------------------------------------------------------


@app.get("/api/verification/queue")
def verification_queue(db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    evs = db.scalars(select(ThreatEvent).where(ThreatEvent.verification == "pending").order_by(ThreatEvent.event_date.desc())).all()
    obs = db.scalars(select(PolicyObservation).where(PolicyObservation.verification == "pending").order_by(PolicyObservation.observed_at.desc())).all()
    return {
        "events": [_event_row(e) for e in evs],
        "observations": [
            {"id": o.id, "actor": o.actor.code, "issue": o.issue.code, "observed_at": o.observed_at.isoformat(), "track": o.track, "channel": o.channel, "cost_class": o.cost_class, "speaker_level": o.speaker_level, "language": o.language, "score": o.score, "source_grade": o.source_grade, "model_confidence": o.model_confidence, "text_excerpt": o.text_excerpt, "text_excerpt_en": o.text_excerpt_en, "provenance": o.provenance, "is_synthetic": o.is_synthetic}
            for o in obs
        ],
    }


class Decision(BaseModel):
    decision: str  # verified | rejected
    by: str
    score: float | None = None  # analysts may correct a stance score when verifying an observation


class BulkDecision(BaseModel):
    kind: str
    ids: list[int]
    decision: str


@app.post("/api/verification/bulk")
def verify_bulk(req: BulkDecision, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    if req.decision not in ("verified", "rejected"):
        raise HTTPException(400, "decision must be verified or rejected")
    model = ThreatEvent if req.kind == "event" else PolicyObservation if req.kind == "observation" else None
    if model is None:
        raise HTTPException(400, "kind must be event or observation")
    n = 0
    for row in db.scalars(select(model).where(model.id.in_(req.ids[:500]), model.verification == "pending")):
        row.verification, row.verified_by, row.verified_at = req.decision, user.username, datetime.utcnow()
        n += 1
    db.commit()
    auth.audit(db, user, f"{req.kind}_bulk_{req.decision}", None, {"n": n})
    return {"kind": req.kind, "decision": req.decision, "n": n}


@app.post("/api/verification/{kind}/{item_id}")
def verify(kind: str, item_id: int, req: Decision, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> dict:
    if req.decision not in ("verified", "rejected"):
        raise HTTPException(400, "decision must be verified or rejected")
    model = ThreatEvent if kind == "event" else PolicyObservation if kind == "observation" else None
    if model is None:
        raise HTTPException(400, "kind must be event or observation")
    row = db.get(model, item_id)
    if row is None:
        raise HTTPException(404, "not found")
    row.verification = req.decision
    row.verified_by = user.username
    row.verified_at = datetime.utcnow()
    if kind == "observation" and req.score is not None:
        row.score = max(-1.0, min(1.0, req.score))
    db.commit()
    auth.audit(db, user, f"{kind}_{req.decision}", str(item_id), {"score": req.score} if req.score is not None else {})
    return {"id": item_id, "kind": kind, "verification": row.verification}


# Serve the built front end when present (docker image copies it to /app/static). The app is a
# single-page client, so any non-API path returns index.html and the router takes over.
_static = os.getenv("RASAD_STATIC_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "static"))
if os.path.isdir(_static):  # pragma: no cover
    from fastapi.responses import FileResponse

    if os.path.isdir(os.path.join(_static, "assets")):
        app.mount("/assets", StaticFiles(directory=os.path.join(_static, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = os.path.join(_static, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_static, "index.html"))
