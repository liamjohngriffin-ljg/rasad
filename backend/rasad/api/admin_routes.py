"""Product administration: licence, API keys, settings (branding and marking), data exports."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import secrets
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import licence
from ..auth import core as auth
from ..auth.models import ROLES, ApiKey, Setting, User
from ..config import get_settings
from ..db import get_session
from ..models import Forecast, PolicyObservation, SeriesPoint, ThreatEvent
from .deps import require_feature, current_user, require_role

router = APIRouter(prefix="/api", tags=["admin"])

SETTING_KEYS = {
    "org_name": "", "product_name": "Rasad", "marking": os.getenv("RASAD_MARKING", "OFFICIAL"), "default_lang": "en", "accent": "#d9a441",
    "logo_data_url": "", "footer_note": "", "public_url": os.getenv("RASAD_PUBLIC_URL", ""), "digest_to": os.getenv("RASAD_DIGEST_TO", ""),
    "require_mfa": os.getenv("RASAD_REQUIRE_MFA", "false"),
    "webhook_url": os.getenv("RASAD_WEBHOOK_URL", ""), "webhook_kind": os.getenv("RASAD_WEBHOOK_KIND", "teams"),
    "webhook_min_severity": os.getenv("RASAD_WEBHOOK_MIN_SEVERITY", "2"),
}


def get_setting(db: Session, key: str) -> str:
    row = db.get(Setting, key)
    if row is None:
        return SETTING_KEYS.get(key, "")
    return str((row.value or {}).get("v", SETTING_KEYS.get(key, "")))


def all_settings(db: Session) -> dict:
    out = dict(SETTING_KEYS)
    for row in db.scalars(select(Setting)):
        if row.key in out:
            out[row.key] = str((row.value or {}).get("v", out[row.key]))
    return out


# ---------------------------------------------------------------------------
# Licence
# ---------------------------------------------------------------------------


@router.get("/licence")
def licence_state(db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    st = licence.current()
    seats_used = db.scalar(select(func.count(User.id)).where(User.active.is_(True))) or 0
    return {**st.as_dict(), "seats_used": seats_used, "evaluation_seats": licence.EVALUATION_SEATS}


class LicenceUpload(BaseModel):
    document: dict


@router.post("/licence")
def licence_upload(req: LicenceUpload, db: Session = Depends(get_session), admin: User = Depends(require_role("admin"))) -> dict:
    try:
        payload = licence.verify(req.document)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    path = os.getenv("RASAD_LICENCE_FILE") or os.path.join(get_settings().data_dir, "licence.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(req.document, f, indent=1)
    st = licence.current(refresh=True)
    auth.audit(db, admin, "licence_installed", payload.get("licence_id"), {"licensee": payload.get("licensee"), "expires": payload.get("expires")})
    return st.as_dict()


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


def _key_row(k: ApiKey) -> dict:
    return {"id": k.id, "name": k.name, "prefix": k.prefix, "role": k.role, "created_by": k.created_by, "created_at": k.created_at.isoformat(), "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None, "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None}


class ApiKeyIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    role: str = "viewer"


@router.get("/keys")
def list_keys(db: Session = Depends(get_session), admin: User = Depends(require_role("admin"))) -> list[dict]:
    return [_key_row(k) for k in db.scalars(select(ApiKey).order_by(ApiKey.created_at.desc()))]


@router.post("/keys", status_code=201, dependencies=[Depends(require_feature("api"))])
def create_key(req: ApiKeyIn, db: Session = Depends(get_session), admin: User = Depends(require_role("admin"))) -> dict:
    if req.role not in ROLES:
        raise HTTPException(400, "unknown role")
    token = "rsk_" + secrets.token_urlsafe(32)
    k = ApiKey(name=req.name, prefix=token[:12], key_hash=hashlib.sha256(token.encode()).hexdigest(), role=req.role, created_by=admin.username)
    db.add(k)
    db.commit()
    auth.audit(db, admin, "api_key_created", req.name, {"role": req.role})
    return {**_key_row(k), "token": token}


@router.delete("/keys/{key_id}")
def revoke_key(key_id: int, db: Session = Depends(get_session), admin: User = Depends(require_role("admin"))) -> dict:
    k = db.get(ApiKey, key_id)
    if k is None:
        raise HTTPException(404, "key not found")
    k.revoked_at = datetime.utcnow()
    db.commit()
    auth.audit(db, admin, "api_key_revoked", k.name)
    return _key_row(k)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


# settings that carry a credential: never shown to non-admins, shown masked to admins
SECRET_SETTINGS = {"webhook_url"}
MASK = "••••"


def _public_settings(db: Session, user: User) -> dict:
    out = all_settings(db)
    for k in SECRET_SETTINGS:
        v = out.get(k) or ""
        out[k] = (MASK + v[-6:] if v else "") if user.role == "admin" else ""
    return out


@router.get("/settings")
def read_settings(db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    return _public_settings(db, user)


class SettingsIn(BaseModel):
    values: dict[str, str]


@router.put("/settings")
def write_settings(req: SettingsIn, db: Session = Depends(get_session), admin: User = Depends(require_role("admin"))) -> dict:
    changed = []
    for k, v in req.values.items():
        if k not in SETTING_KEYS:
            raise HTTPException(400, f"unknown setting {k}")
        if k == "logo_data_url" and len(v) > 200_000:
            raise HTTPException(400, "logo too large (200 KB limit)")
        if k in SECRET_SETTINGS and v.startswith(MASK):
            continue  # the masked value came back unchanged from the form
        if k == "webhook_url" and v:
            from .. import licence
            from ..engine import notify

            if not licence.current().has("api"):
                raise HTTPException(403, "not in your licence: api (API keys and the team channel)")
            try:
                notify.check_url(v)
            except ValueError as exc:
                raise HTTPException(400, str(exc))
        row = db.get(Setting, k)
        if row is None:
            db.add(Setting(key=k, value={"v": v}, updated_by=admin.username))
        else:
            row.value, row.updated_by = {"v": v}, admin.username
        changed.append(k)
    db.commit()
    auth.audit(db, admin, "settings_updated", None, {"keys": changed})
    return _public_settings(db, admin)


@router.post("/settings/webhook/test", dependencies=[Depends(require_feature("api"))])
def test_webhook(db: Session = Depends(get_session), admin: User = Depends(require_role("admin"))) -> dict:
    from ..engine import notify

    res = notify.send_test(db)
    auth.audit(db, admin, "webhook_tested", None, {"ok": res.get("ok")})
    if not res.get("ok"):
        raise HTTPException(400, res.get("error", "webhook failed"))
    return res


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


def _cell(v):
    """Text that a spreadsheet would run as a formula (=, +, -, @, tab, CR) is prefixed with a quote:
    feed and analyst text must never execute when an export is opened in Excel."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def _csv(rows: list[dict], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: _cell(json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in r.items()})
    data = ("﻿" + buf.getvalue()).encode("utf-8")
    return StreamingResponse(io.BytesIO(data), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/export/events.csv", dependencies=[Depends(require_feature("export"))])
def export_events(days: int = Query(365, ge=1, le=5000), verified_only: bool = False, db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))):
    since = date.today() - timedelta(days=days)
    stmt = select(ThreatEvent).where(ThreatEvent.event_date >= since).order_by(ThreatEvent.event_date)
    if verified_only:
        stmt = stmt.where(ThreatEvent.verification == "verified")
    rows = [{"id": e.id, "event_date": e.event_date.isoformat(), "event_type": e.event_type, "country": e.country, "location": e.location_name, "lat": e.lat, "lon": e.lon, "severity": e.severity, "fatalities": e.fatalities, "actor": e.actor.code if e.actor else None, "target": e.target_actor.code if e.target_actor else None, "description_en": e.description_en, "description_ar": e.description_ar, "source": (e.provenance or {}).get("source"), "url": (e.provenance or {}).get("url"), "grade": (e.provenance or {}).get("grade"), "incident_no": (e.provenance or {}).get("incident_no"), "verification": e.verification, "verified_by": e.verified_by, "is_synthetic": e.is_synthetic} for e in db.scalars(stmt)]
    auth.audit(db, user, "export", "events.csv", {"rows": len(rows)})
    return _csv(rows, f"rasad-events-{date.today().isoformat()}.csv")


@router.get("/export/observations.csv", dependencies=[Depends(require_feature("export"))])
def export_observations(days: int = Query(365, ge=1, le=5000), db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))):
    since = date.today() - timedelta(days=days)
    rows = [{"id": o.id, "observed_at": o.observed_at.isoformat(), "actor": o.actor.code, "issue": o.issue.code, "track": o.track, "channel": o.channel, "cost_class": o.cost_class, "speaker_level": o.speaker_level, "language": o.language, "score": o.score, "source_grade": o.source_grade, "model_confidence": o.model_confidence, "text_excerpt": o.text_excerpt, "text_excerpt_en": o.text_excerpt_en, "source": (o.provenance or {}).get("source"), "url": (o.provenance or {}).get("url"), "verification": o.verification, "is_synthetic": o.is_synthetic} for o in db.scalars(select(PolicyObservation).where(PolicyObservation.observed_at >= since).order_by(PolicyObservation.observed_at))]
    auth.audit(db, user, "export", "observations.csv", {"rows": len(rows)})
    return _csv(rows, f"rasad-observations-{date.today().isoformat()}.csv")


@router.get("/export/series.csv", dependencies=[Depends(require_feature("export"))])
def export_series(name: str = Query(min_length=2, max_length=80, pattern="^[a-z0-9_]+$"), days: int = Query(1000, ge=1, le=5000), db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))):
    since = date.today() - timedelta(days=days)
    rows = [{"series": p.series, "date": p.date.isoformat(), "value": p.value, "unit": p.unit, "source": p.source, "is_synthetic": p.is_synthetic} for p in db.scalars(select(SeriesPoint).where(SeriesPoint.series == name, SeriesPoint.date >= since).order_by(SeriesPoint.date))]
    auth.audit(db, user, "export", f"series:{name}", {"rows": len(rows)})
    return _csv(rows, f"rasad-{name}-{date.today().isoformat()}.csv")


@router.get("/export/forecasts.csv", dependencies=[Depends(require_feature("export"))])
def export_forecasts(db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))):
    rows = [{"id": f.id, "question": f.question.code, "as_of": f.as_of.isoformat(), "machine_prob": f.machine_prob, "panel_prob": f.panel_prob, "final_prob": f.final_prob, "prev_hash": f.prev_hash, "commit_hash": f.commit_hash} for f in db.scalars(select(Forecast).order_by(Forecast.id))]
    auth.audit(db, user, "export", "forecasts.csv", {"rows": len(rows)})
    return _csv(rows, f"rasad-forecasts-{date.today().isoformat()}.csv")


@router.get("/export/forecasts.json", dependencies=[Depends(require_feature("export"))])
def export_forecasts_json(db: Session = Depends(get_session), user: User = Depends(require_role("analyst"))) -> list[dict]:
    """The full commitment log with decompositions, for independent verification of the chain."""
    return [{"id": f.id, "question": f.question.code, "as_of": f.as_of.isoformat(), "final_prob": f.final_prob, "decomposition": f.decomposition, "prev_hash": f.prev_hash, "commit_hash": f.commit_hash} for f in db.scalars(select(Forecast).order_by(Forecast.id))]
