from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import core as auth
from ..auth.models import ROLES, AuditLog, User
from ..db import get_session
from .deps import COOKIE, client_ip, cookie_secure, current_user, require_role

router = APIRouter(prefix="/api")
throttle = auth.LoginThrottle()


def _user_row(u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role, "active": u.active,
        "must_change_password": u.must_change_password, "created_at": u.created_at.isoformat(),
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "mfa_enabled": bool(u.totp_enabled), "recovery_codes_left": len(u.recovery_hashes or []) if u.totp_enabled else None,
    }


def _mfa_policy(db: Session) -> bool:
    from .admin_routes import get_setting

    return get_setting(db, "require_mfa").strip().lower() in ("1", "true", "yes", "on")


def _me_row(db: Session, u: User) -> dict:
    row = _user_row(u)
    row["must_enrol_mfa"] = u.id > 0 and _mfa_policy(db) and not u.totp_enabled
    return row


def _set_session(response: Response, request: Request, u: User) -> None:
    response.set_cookie(COOKIE, auth.token_for(u), max_age=auth.SESSION_TTL_SECONDS, httponly=True, samesite="lax", secure=cookie_secure(request), path="/")


class LoginIn(BaseModel):
    username: str
    password: str
    code: str | None = None  # authenticator code or a recovery code, when the account has two-factor sign-in


@router.post("/auth/login")
def login(req: LoginIn, request: Request, response: Response, db: Session = Depends(get_session)) -> dict:
    key = f"{req.username.lower()}|{client_ip(request)}"
    if throttle.blocked(key):
        raise HTTPException(429, "too many attempts; try again in 15 minutes")
    user = auth.authenticate(db, req.username, req.password)
    if user is None:
        throttle.hit(key)
        auth.audit(db, None, "login_failed", req.username.lower(), ip=client_ip(request))
        raise HTTPException(401, "wrong username or password")
    if user.totp_enabled:
        if not req.code:
            raise HTTPException(401, "mfa_required")
        if not auth.check_second_factor(db, user, req.code):
            throttle.hit(key)
            auth.audit(db, user, "login_failed_mfa", ip=client_ip(request))
            raise HTTPException(401, "mfa_invalid")
    throttle.clear(key)
    _set_session(response, request, user)
    auth.audit(db, user, "login", None, {"mfa": bool(user.totp_enabled)}, ip=client_ip(request))
    return _me_row(db, user)


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    response.delete_cookie(COOKIE, path="/")
    auth.audit(db, user, "logout", ip=client_ip(request))
    return {"ok": True}


@router.get("/auth/me")
def me(db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    return _me_row(db, user)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.post("/auth/password")
def change_password(req: PasswordChange, request: Request, response: Response, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    if not auth.verify_password(req.current_password, user.password_hash):
        raise HTTPException(400, "current password is wrong")
    if len(req.new_password) < 10:
        raise HTTPException(400, "new password must be at least 10 characters")
    user.password_hash = auth.hash_password(req.new_password)
    user.must_change_password = False
    user.session_version = (user.session_version or 0) + 1  # every other session ends
    db.commit()
    _set_session(response, request, user)
    auth.audit(db, user, "password_changed", ip=client_ip(request))
    return {"ok": True}


@router.post("/auth/sessions/revoke")
def revoke_sessions(request: Request, response: Response, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    """Sign out everywhere else: older cookies stop working, this browser gets a fresh one."""
    if user.id <= 0:
        raise HTTPException(400, "API keys have no sessions")
    user.session_version = (user.session_version or 0) + 1
    db.commit()
    _set_session(response, request, user)
    auth.audit(db, user, "sessions_revoked", ip=client_ip(request))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Two-factor sign-in (TOTP)
# ---------------------------------------------------------------------------


@router.post("/auth/mfa/setup")
def mfa_setup(request: Request, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    """Start enrolment: a new secret is stored (not yet active) and returned with a QR code."""
    from ..auth import totp
    from .admin_routes import get_setting

    if user.id <= 0:
        raise HTTPException(400, "API keys cannot enrol")
    if user.totp_enabled:
        raise HTTPException(400, "two-factor sign-in is already on; turn it off first to re-enrol")
    user.totp_secret = totp.new_secret()
    user.totp_last_step = None
    db.commit()
    issuer = get_setting(db, "product_name") or "Rasad"
    uri = totp.uri(user.totp_secret, user.username, issuer)
    auth.audit(db, user, "mfa_setup_started", ip=client_ip(request))
    return {"secret": user.totp_secret, "uri": uri, "qr_svg": totp.qr_svg(uri)}


class CodeIn(BaseModel):
    code: str


@router.post("/auth/mfa/enable")
def mfa_enable(req: CodeIn, request: Request, response: Response, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    from ..auth import totp

    if user.id <= 0 or not user.totp_secret or user.totp_enabled:
        raise HTTPException(400, "start enrolment first")
    step = totp.verify(user.totp_secret, req.code)
    if step is None:
        raise HTTPException(400, "that code does not match; check the device clock and try the next code")
    codes = totp.new_recovery_codes()
    user.totp_enabled, user.totp_last_step = True, step
    user.recovery_hashes = [totp.hash_recovery(c) for c in codes]
    user.session_version = (user.session_version or 0) + 1
    db.commit()
    _set_session(response, request, user)
    auth.audit(db, user, "mfa_enabled", ip=client_ip(request))
    return {"ok": True, "recovery_codes": codes}


class PasswordIn(BaseModel):
    password: str


@router.post("/auth/mfa/disable")
def mfa_disable(req: PasswordIn, request: Request, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    if user.id <= 0 or not auth.verify_password(req.password, user.password_hash):
        raise HTTPException(400, "password is wrong")
    if _mfa_policy(db):
        raise HTTPException(400, "two-factor sign-in is required by your administrator")
    user.totp_enabled, user.totp_secret, user.recovery_hashes, user.totp_last_step = False, None, None, None
    db.commit()
    auth.audit(db, user, "mfa_disabled", ip=client_ip(request))
    return {"ok": True}


@router.post("/auth/mfa/recovery")
def mfa_new_recovery(req: PasswordIn, request: Request, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    from ..auth import totp

    if user.id <= 0 or not user.totp_enabled or not auth.verify_password(req.password, user.password_hash):
        raise HTTPException(400, "password is wrong or two-factor sign-in is off")
    codes = totp.new_recovery_codes()
    user.recovery_hashes = [totp.hash_recovery(c) for c in codes]
    db.commit()
    auth.audit(db, user, "mfa_recovery_regenerated", ip=client_ip(request))
    return {"recovery_codes": codes}


# ---------------------------------------------------------------------------
# Admin: users and audit log
# ---------------------------------------------------------------------------


class UserIn(BaseModel):
    username: str
    display_name: str | None = None
    role: str = "viewer"
    password: str


@router.get("/users")
def list_users(db: Session = Depends(get_session), _: User = Depends(require_role("admin"))) -> list[dict]:
    return [_user_row(u) for u in db.scalars(select(User).order_by(User.username)).all()]


@router.post("/users")
def add_user(req: UserIn, request: Request, db: Session = Depends(get_session), admin: User = Depends(require_role("admin"))) -> dict:
    from .. import licence

    st = licence.current()
    active = db.scalar(select(func.count(User.id)).where(User.active.is_(True))) or 0
    if active >= st.seats:
        raise HTTPException(403, f"seat limit reached ({st.seats} seats, {st.mode} mode); install a licence with more seats")
    if req.role not in ROLES:
        raise HTTPException(400, f"role must be one of {ROLES}")
    if len(req.password) < 10:
        raise HTTPException(400, "password must be at least 10 characters")
    try:
        u = auth.create_user(db, req.username, req.password, req.role, req.display_name, must_change=True)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    auth.audit(db, admin, "user_created", u.username, {"role": u.role}, ip=client_ip(request))
    return _user_row(u)


class UserPatch(BaseModel):
    role: str | None = None
    active: bool | None = None
    display_name: str | None = None
    password: str | None = None
    reset_mfa: bool | None = None  # a lost phone: the user enrols again at next sign-in


@router.patch("/users/{user_id}")
def patch_user(user_id: int, req: UserPatch, request: Request, db: Session = Depends(get_session), admin: User = Depends(require_role("admin"))) -> dict:
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "no such user")
    changes: dict = {}
    if req.role is not None:
        if req.role not in ROLES:
            raise HTTPException(400, "bad role")
        if u.id == admin.id and req.role != "admin":
            raise HTTPException(400, "you cannot remove your own admin role")
        u.role, changes["role"] = req.role, req.role
    if req.active is not None:
        if u.id == admin.id and not req.active:
            raise HTTPException(400, "you cannot deactivate yourself")
        u.active, changes["active"] = req.active, req.active
    if req.display_name is not None:
        u.display_name, changes["display_name"] = req.display_name, req.display_name
    if req.password is not None:
        if len(req.password) < 10:
            raise HTTPException(400, "password must be at least 10 characters")
        u.password_hash, u.must_change_password, changes["password"] = auth.hash_password(req.password), True, "reset"
        u.session_version = (u.session_version or 0) + 1
    if req.reset_mfa:
        u.totp_enabled, u.totp_secret, u.recovery_hashes, u.totp_last_step = False, None, None, None
        u.session_version = (u.session_version or 0) + 1
        changes["mfa"] = "reset"
    if req.active is False:
        u.session_version = (u.session_version or 0) + 1
    db.commit()
    auth.audit(db, admin, "user_updated", u.username, changes, ip=client_ip(request))
    return _user_row(u)


@router.get("/audit")
def audit_log(limit: int = 200, db: Session = Depends(get_session), _: User = Depends(require_role("admin"))) -> list[dict]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 1000))).all()
    return [{"id": r.id, "at": r.at.isoformat(), "user": r.username, "action": r.action, "target": r.target, "detail": r.detail, "ip": r.ip} for r in rows]


@router.get("/health", include_in_schema=False)
def health() -> dict:
    return {"ok": True, "at": datetime.utcnow().isoformat()}
