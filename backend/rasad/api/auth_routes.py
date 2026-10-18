from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
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
    }


class LoginIn(BaseModel):
    username: str
    password: str


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
    throttle.clear(key)
    response.set_cookie(COOKIE, auth.make_token(user.id), max_age=auth.SESSION_TTL_SECONDS, httponly=True, samesite="lax", secure=cookie_secure(request), path="/")
    auth.audit(db, user, "login", ip=client_ip(request))
    return _user_row(user)


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    response.delete_cookie(COOKIE, path="/")
    auth.audit(db, user, "logout", ip=client_ip(request))
    return {"ok": True}


@router.get("/auth/me")
def me(user: User = Depends(current_user)) -> dict:
    return _user_row(user)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.post("/auth/password")
def change_password(req: PasswordChange, request: Request, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    if not auth.verify_password(req.current_password, user.password_hash):
        raise HTTPException(400, "current password is wrong")
    if len(req.new_password) < 10:
        raise HTTPException(400, "new password must be at least 10 characters")
    user.password_hash = auth.hash_password(req.new_password)
    user.must_change_password = False
    db.commit()
    auth.audit(db, user, "password_changed", ip=client_ip(request))
    return {"ok": True}


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
