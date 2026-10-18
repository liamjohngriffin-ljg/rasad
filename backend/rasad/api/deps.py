from __future__ import annotations

import hashlib
from datetime import datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.core import parse_token
from ..auth.models import ApiKey, User
from ..db import get_session

COOKIE = "rasad_session"
CLIENT_HEADER = "x-rasad-client"  # sent by the web client on every state-changing call; a cross-site form cannot add it
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def _api_key_user(db: Session, token: str) -> User | None:
    if not token.startswith("rsk_"):
        return None
    h = hashlib.sha256(token.encode()).hexdigest()
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == h))
    if key is None or key.revoked_at is not None:
        return None
    key.last_used_at = datetime.utcnow()
    db.commit()
    # a transient user object: never persisted, carries the key's role and name
    return User(id=-key.id, username=f"key:{key.name}", display_name=f"API key {key.name}", role=key.role, password_hash="", active=True, must_change_password=False)


def current_user(request: Request, db: Session = Depends(get_session)) -> User:
    authz = request.headers.get("authorization", "")
    if authz.lower().startswith("bearer "):
        u = _api_key_user(db, authz[7:].strip())
        if u is None:
            raise HTTPException(401, "invalid API key")
        return u
    uid = parse_token(request.cookies.get(COOKIE))
    if uid is None:
        raise HTTPException(401, "not signed in")
    if request.method not in SAFE_METHODS and request.headers.get(CLIENT_HEADER) is None:
        raise HTTPException(403, "missing client header")
    user = db.get(User, uid)
    if user is None or not user.active:
        raise HTTPException(401, "not signed in")
    return user


def require_role(*roles: str):
    order = {"viewer": 0, "analyst": 1, "admin": 2}
    minimum = min(order[r] for r in roles)

    def dep(user: User = Depends(current_user)) -> User:
        if order.get(user.role, -1) < minimum:
            raise HTTPException(403, f"requires {roles[0]} role")
        return user

    return dep


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def cookie_secure(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
