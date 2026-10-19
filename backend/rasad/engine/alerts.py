"""Alerts: the things an analyst who was not watching needs to see first.

Raised by the daily commit and by the poll:
  indicator_flip   an indicator changed state between the previous commit and this one
  forecast_move    the committed probability moved by RASAD_ALERT_MOVE_POINTS or more in a day
  severe_event     a new event of severity 4+ landed (pending or verified) in the last day
  series_break     a watched daily series fell to half, or doubled, against its 30-day mean
  chain_broken     the commitment chain failed verification
  resolution_due   an open question resolves within 7 days

Each alert has a dedupe key so a condition that persists raises once; acknowledging clears it
from the inbox but not from the record. An optional SMTP digest sends unacknowledged alerts.
"""

from __future__ import annotations

import os
import smtplib
from datetime import date, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Alert, Forecast, Question, SeriesPoint, ThreatEvent
from .commitment import verify_chain

MOVE_POINTS = float(os.getenv("RASAD_ALERT_MOVE_POINTS", "10"))
WATCHED_SERIES = ("hormuz_transits", "bab_el_mandeb_transits", "hormuz_tanker_transits", "bab_el_mandeb_tanker_transits")


def _raise(db: Session, *, kind: str, severity: int, key: str, title_en: str, title_ar: str | None = None, question_code: str | None = None, detail: dict | None = None) -> Alert | None:
    if db.scalar(select(Alert).where(Alert.dedupe_key == key)):
        return None
    a = Alert(kind=kind, severity=severity, dedupe_key=key, title_en=title_en, title_ar=title_ar, question_code=question_code, detail=detail or {})
    db.add(a)
    return a


def after_commit(db: Session, forecasts: list[Forecast]) -> int:
    """Compare each new forecast with the previous commit for its question."""
    n = 0
    for fc in forecasts:
        q = fc.question
        prev = db.scalar(select(Forecast).where(Forecast.question_id == fc.question_id, Forecast.as_of < fc.as_of).order_by(Forecast.as_of.desc()).limit(1))
        if prev is None:
            continue
        move = (fc.final_prob - prev.final_prob) * 100
        if abs(move) >= MOVE_POINTS:
            direction = "up" if move > 0 else "down"
            if _raise(db, kind="forecast_move", severity=3 if abs(move) >= 2 * MOVE_POINTS else 2, key=f"move:{q.code}:{fc.as_of.isoformat()}", question_code=q.code,
                      title_en=f"{q.title_en[:90]}: {direction} {abs(move):.0f} points to {fc.final_prob * 100:.0f} percent",
                      title_ar=f"{(q.title_ar or q.title_en)[:90]}: {'ارتفاع' if move > 0 else 'انخفاض'} {abs(move):.0f} نقطة إلى {fc.final_prob * 100:.0f} بالمئة",
                      detail={"from": prev.final_prob, "to": fc.final_prob, "prev_as_of": prev.as_of.isoformat(), "as_of": fc.as_of.isoformat()}):
                n += 1
        prev_states = {c["indicator"]: c["state"] for c in (prev.decomposition or {}).get("machine", {}).get("contributions", [])}
        names = {i.code: (i.name_en, i.name_ar) for i in q.indicators}
        for c in (fc.decomposition or {}).get("machine", {}).get("contributions", []):
            before = prev_states.get(c["indicator"])
            if before is None or before == c["state"] or "unknown" in (before, c["state"]):
                continue
            name_en, name_ar = names.get(c["indicator"], (c["indicator"], None))
            if _raise(db, kind="indicator_flip", severity=2, key=f"flip:{q.code}:{c['indicator']}:{fc.as_of.isoformat()}", question_code=q.code,
                      title_en=f"{name_en}: {before} to {c['state']}", title_ar=f"{name_ar or name_en}: {before} إلى {c['state']}",
                      detail={"indicator": c["indicator"], "from": before, "to": c["state"], "log_lr": c.get("log_lr"), "as_of": fc.as_of.isoformat()}):
                n += 1
    db.commit()
    return n


def after_poll(db: Session, since: datetime | None = None) -> int:
    n = 0
    since = since or (datetime.utcnow() - timedelta(days=1))
    recent = date.today() - timedelta(days=14)  # a backfill of old reports must not read as news
    for e in db.scalars(select(ThreatEvent).where(ThreatEvent.severity >= 4, ThreatEvent.is_synthetic.is_(False), ThreatEvent.created_at >= since, ThreatEvent.event_date >= recent, ThreatEvent.verification != "rejected").order_by(ThreatEvent.id)):
        src = (e.provenance or {}).get("source", "")
        if e.verification != "verified" and str((e.provenance or {}).get("grade", "C"))[:1].upper() not in ("A", "B"):
            continue  # an unverified lexicon extraction is not news until an analyst accepts it
        if _raise(db, kind="severe_event", severity=3 if e.severity >= 5 else 2, key=f"event:{e.id}", title_en=f"{e.event_date.isoformat()} {e.event_type} {e.country or ''}: {e.description_en[:140]}",
                  title_ar=e.description_ar[:160] if e.description_ar else None, detail={"event_id": e.id, "source": src, "verification": e.verification}):
            n += 1
    today = date.today()
    for series in WATCHED_SERIES:
        latest = db.scalar(select(SeriesPoint).where(SeriesPoint.series == series, SeriesPoint.is_synthetic.is_(False)).order_by(SeriesPoint.date.desc()).limit(1))
        if latest is None or (today - latest.date).days > 10:
            continue
        mean = db.scalar(select(func.avg(SeriesPoint.value)).where(SeriesPoint.series == series, SeriesPoint.date < latest.date, SeriesPoint.date >= latest.date - timedelta(days=30), SeriesPoint.is_synthetic.is_(False)))
        if not mean:
            continue
        ratio = latest.value / mean
        if ratio <= 0.5 or ratio >= 2.0:
            if _raise(db, kind="series_break", severity=3 if ratio <= 0.35 else 2, key=f"series:{series}:{latest.date.isoformat()}",
                      title_en=f"{series} at {latest.value:.0f} on {latest.date.isoformat()} against a 30-day mean of {mean:.0f}",
                      title_ar=f"{series}: {latest.value:.0f} في {latest.date.isoformat()} مقابل متوسط 30 يوماً {mean:.0f}",
                      detail={"series": series, "value": latest.value, "mean_30d": round(mean, 1), "ratio": round(ratio, 2)}):
                n += 1
    for q in db.scalars(select(Question).where(Question.status == "open")):
        days = (q.resolves_at - today).days
        if 0 <= days <= 7:
            if _raise(db, kind="resolution_due", severity=2, key=f"due:{q.code}:{q.resolves_at.isoformat()}", question_code=q.code,
                      title_en=f"{q.code} resolves on {q.resolves_at.isoformat()}: record the outcome", title_ar=f"{q.code} يُحسم في {q.resolves_at.isoformat()}: سجّل النتيجة",
                      detail={"resolves_at": q.resolves_at.isoformat()}):
                n += 1
    rows = [
        {"prev_hash": r.prev_hash, "question_code": r.question.code, "as_of": r.as_of, "final_prob": r.final_prob, "decomposition": r.decomposition, "commit_hash": r.commit_hash}
        for r in db.scalars(select(Forecast).order_by(Forecast.id))
    ]
    ok, bad = verify_chain(rows)
    if not ok:
        if _raise(db, kind="chain_broken", severity=3, key=f"chain:{bad}", title_en=f"Commitment chain failed verification at index {bad}", title_ar="فشل التحقق من سلسلة الالتزام", detail={"first_bad_index": bad, "length": len(rows)}):
            n += 1
    db.commit()
    return n


def unacknowledged(db: Session, limit: int = 100) -> list[Alert]:
    return db.scalars(select(Alert).where(Alert.acknowledged_at.is_(None)).order_by(Alert.severity.desc(), Alert.created_at.desc()).limit(limit)).all()


def send_digest(db: Session) -> dict:
    """Email unacknowledged alerts to RASAD_DIGEST_TO when SMTP is configured. Returns what
    happened; never raises, since a mail failure must not stop the pipeline."""
    host, to = os.getenv("RASAD_SMTP_HOST"), os.getenv("RASAD_DIGEST_TO")
    if not host or not to:
        return {"sent": False, "reason": "RASAD_SMTP_HOST or RASAD_DIGEST_TO not set"}
    alerts = unacknowledged(db)
    if not alerts:
        return {"sent": False, "reason": "nothing unacknowledged"}
    base = os.getenv("RASAD_PUBLIC_URL", "").rstrip("/")
    lines = [f"Rasad digest, {datetime.utcnow():%Y-%m-%d %H:%M} UTC: {len(alerts)} unacknowledged alerts", ""]
    for a in alerts:
        link = f" {base}/q/{a.question_code}" if base and a.question_code else ""
        lines.append(f"[{'!' * a.severity}] {a.created_at:%Y-%m-%d} {a.kind}: {a.title_en}{link}")
    msg = EmailMessage()
    msg["Subject"] = f"[{os.getenv('RASAD_MARKING', 'OFFICIAL')}] Rasad: {len(alerts)} alerts"
    msg["From"] = os.getenv("RASAD_SMTP_FROM", "rasad@localhost")
    msg["To"] = to
    msg.set_content("\n".join(lines))
    try:
        port = int(os.getenv("RASAD_SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=30) as s:
            if os.getenv("RASAD_SMTP_STARTTLS", "true").lower() in ("1", "true", "yes"):
                s.starttls()
            user, pw = os.getenv("RASAD_SMTP_USER"), os.getenv("RASAD_SMTP_PASSWORD")
            if user and pw:
                s.login(user, pw)
            s.send_message(msg)
        return {"sent": True, "alerts": len(alerts), "to": to}
    except Exception as exc:  # noqa: BLE001
        return {"sent": False, "reason": f"{type(exc).__name__}: {exc}"[:200]}
