from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth.core import parse_token
from ..auth.models import User
from ..db import get_session

COOKIE = "rasad_session"


def current_user(request: Request, db: Session = Depends(get_session)) -> User:
    uid = parse_token(request.cookies.get(COOKIE))
    if uid is None:
        raise HTTPException(401, "not signed in")
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
