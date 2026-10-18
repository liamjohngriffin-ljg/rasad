"""Indicator rules: how an indicator's state is read from the ledgers on a given day.

Rule types (the `rule` JSON on an Indicator):
  event_count      {"type":"event_count","event_types":[...],"countries":[...],"actors":[...],"include_pending_extractions":false,
                    "window_days":14,"threshold":1,"min_severity":1}
  series_threshold {"type":"series_threshold","series":"war_risk_premium_hormuz_pct","op":">=",
                    "value":2.0,"lookback_days":14}
  series_change    {"type":"series_change","series":"hormuz_transits","window_days":14,
                    "baseline_days":90,"op":"<=","ratio":0.5}
  position_level   {"type":"position_level","actor":"IR","issue":"hormuz_posture","track":"stated",
                    "op":">=","value":0.4}
  divergence       {"type":"divergence","actor":"US","issue":"gulf_force_posture","op":">=","value":0.4}
  silence          {"type":"silence","actor":"IR","issue":"hormuz_posture"}
  change_point     {"type":"change_point","actor":"US","issue":"gulf_force_posture","track":"revealed",
                    "within_days":30,"direction":"down"}

Every evaluation returns a state and the evidence behind it (ledger ids, series values), which
is what the principal sees when a number is opened.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Actor, Indicator, SeriesPoint, ThreatEvent
from ..policy import book as policy_book
from ..policy import positions as P

OPS = {">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt, "==": operator.eq}


@dataclass
class EvaluatedState:
    state: str  # present | absent | unknown
    evidence: dict


def _event_count(db: Session, rule: dict, as_of: date) -> EvaluatedState:
    window = int(rule.get("window_days", 14))
    start = as_of - timedelta(days=window)
    stmt = select(ThreatEvent).where(
        ThreatEvent.event_date > start,
        ThreatEvent.event_date <= as_of,
        ThreatEvent.verification != "rejected",
    )
    if rule.get("event_types"):
        stmt = stmt.where(ThreatEvent.event_type.in_(rule["event_types"]))
    if rule.get("countries"):
        stmt = stmt.where(ThreatEvent.country.in_(rule["countries"]))
    if rule.get("min_severity"):
        stmt = stmt.where(ThreatEvent.severity >= int(rule["min_severity"]))
    if rule.get("actors"):
        actor_ids = db.scalars(select(Actor.id).where(Actor.code.in_(rule["actors"]))).all()
        stmt = stmt.where(ThreatEvent.actor_id.in_(actor_ids))
    candidates = db.scalars(stmt).all()
    # pending rows count only when they come from a source-confirmed connector (grade A or B);
    # model or lexicon extractions from wires (grade C and below) count once an analyst accepts them
    rows, excluded = [], 0
    for r in candidates:
        grade = str((r.provenance or {}).get("grade", "C3"))[:1].upper()
        if r.verification == "verified" or grade in ("A", "B") or rule.get("include_pending_extractions"):
            rows.append(r)
        else:
            excluded += 1
    threshold = int(rule.get("threshold", 1))
    return EvaluatedState(
        "present" if len(rows) >= threshold else "absent",
        {
            "count": len(rows),
            "threshold": threshold,
            "window_days": window,
            "event_ids": [r.id for r in rows][:25],
            "pending_extractions_excluded": excluded,
            "synthetic_share": round(sum(1 for r in rows if r.is_synthetic) / len(rows), 2) if rows else 0.0,
        },
    )


def _latest_series(db: Session, series: str, as_of: date, lookback: int) -> SeriesPoint | None:
    return db.scalar(
        select(SeriesPoint)
        .where(SeriesPoint.series == series, SeriesPoint.date <= as_of, SeriesPoint.date > as_of - timedelta(days=lookback))
        .order_by(SeriesPoint.date.desc())
        .limit(1)
    )


def _series_threshold(db: Session, rule: dict, as_of: date) -> EvaluatedState:
    pt = _latest_series(db, rule["series"], as_of, int(rule.get("lookback_days", 14)))
    if pt is None:
        return EvaluatedState("unknown", {"series": rule["series"], "reason": "no data in lookback"})
    ok = OPS[rule.get("op", ">=")](pt.value, float(rule["value"]))
    return EvaluatedState(
        "present" if ok else "absent",
        {"series": rule["series"], "date": pt.date.isoformat(), "value": pt.value, "unit": pt.unit, "op": rule.get("op", ">="), "threshold": rule["value"], "is_synthetic": pt.is_synthetic},
    )


def _series_change(db: Session, rule: dict, as_of: date) -> EvaluatedState:
    window = int(rule.get("window_days", 14))
    baseline = int(rule.get("baseline_days", 90))
    win_start = as_of - timedelta(days=window)
    base_start = win_start - timedelta(days=baseline)
    pts = db.scalars(
        select(SeriesPoint).where(SeriesPoint.series == rule["series"], SeriesPoint.date > base_start, SeriesPoint.date <= as_of)
    ).all()
    recent = [p.value for p in pts if p.date > win_start]
    base = [p.value for p in pts if p.date <= win_start]
    if not recent or not base:
        return EvaluatedState("unknown", {"series": rule["series"], "reason": "insufficient data"})
    r_mean = sum(recent) / len(recent)
    b_mean = sum(base) / len(base)
    ratio = None if b_mean == 0 else r_mean / b_mean
    if ratio is None:
        return EvaluatedState("unknown", {"series": rule["series"], "reason": "zero baseline"})
    ok = OPS[rule.get("op", "<=")](ratio, float(rule["ratio"]))
    return EvaluatedState(
        "present" if ok else "absent",
        {"series": rule["series"], "recent_mean": round(r_mean, 2), "baseline_mean": round(b_mean, 2), "ratio": round(ratio, 3), "op": rule.get("op", "<="), "threshold": rule["ratio"], "synthetic_share": round(sum(1 for p in pts if p.is_synthetic) / len(pts), 2)},
    )


def _position_level(db: Session, rule: dict, as_of: date) -> EvaluatedState:
    obs = policy_book.load_observations(db, rule["actor"], rule["issue"])
    est = P.estimate(obs, as_of, track=rule.get("track", "stated"))
    if est.score is None:
        return EvaluatedState("unknown", {"actor": rule["actor"], "issue": rule["issue"], "reason": "no position"})
    ok = OPS[rule.get("op", ">=")](est.score, float(rule["value"]))
    return EvaluatedState("present" if ok else "absent", {"actor": rule["actor"], "issue": rule["issue"], "track": rule.get("track", "stated"), **est.as_dict(), "op": rule.get("op", ">="), "threshold": rule["value"]})


def _divergence(db: Session, rule: dict, as_of: date) -> EvaluatedState:
    obs = policy_book.load_observations(db, rule["actor"], rule["issue"])
    stated = P.estimate(obs, as_of, track="stated")
    revealed = P.estimate(obs, as_of, track="revealed")
    d = P.divergence(stated, revealed)
    if d is None:
        return EvaluatedState("unknown", {"actor": rule["actor"], "issue": rule["issue"], "reason": "one track empty"})
    ok = OPS[rule.get("op", ">=")](d, float(rule["value"]))
    return EvaluatedState("present" if ok else "absent", {"actor": rule["actor"], "issue": rule["issue"], "divergence": round(d, 3), "stated": stated.as_dict(), "revealed": revealed.as_dict(), "threshold": rule["value"]})


def _silence(db: Session, rule: dict, as_of: date) -> EvaluatedState:
    obs = policy_book.load_observations(db, rule["actor"], rule["issue"])
    s = P.silence(obs, as_of, window_days=int(rule.get("window_days", 14)), baseline_days=int(rule.get("baseline_days", 90)))
    if s["ratio"] is None:
        return EvaluatedState("unknown", {"actor": rule["actor"], "issue": rule["issue"], **s})
    return EvaluatedState("present" if s["flagged"] else "absent", {"actor": rule["actor"], "issue": rule["issue"], **s})


def _change_point(db: Session, rule: dict, as_of: date) -> EvaluatedState:
    obs = policy_book.load_observations(db, rule["actor"], rule["issue"])
    start = as_of - timedelta(days=180)
    ser = P.series(obs, start, as_of, track=rule.get("track", "revealed"))
    cps = P.change_points(ser)
    within = int(rule.get("within_days", 30))
    recent = [c for c in cps if (as_of - date.fromisoformat(c["date"])).days <= within and (not rule.get("direction") or c["direction"] == rule["direction"])]
    if all(v is None for _, v in ser):
        return EvaluatedState("unknown", {"actor": rule["actor"], "issue": rule["issue"], "reason": "no series"})
    return EvaluatedState("present" if recent else "absent", {"actor": rule["actor"], "issue": rule["issue"], "change_points": cps, "recent": recent})


RULES = {
    "event_count": _event_count,
    "series_threshold": _series_threshold,
    "series_change": _series_change,
    "position_level": _position_level,
    "divergence": _divergence,
    "silence": _silence,
    "change_point": _change_point,
}


def evaluate(db: Session, indicator: Indicator, as_of: date) -> EvaluatedState:
    rule = indicator.rule or {}
    fn = RULES.get(rule.get("type"))
    if fn is None:
        return EvaluatedState("unknown", {"reason": f"unknown rule type {rule.get('type')!r}"})
    return fn(db, rule, as_of)
