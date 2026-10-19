from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from .models import ROLES, AuditLog, User

PBKDF2_ITERATIONS = 310_000
SESSION_TTL_SECONDS = 12 * 3600
_secret_cache: bytes | None = None


def secret_key() -> bytes:
    """Signing key: RASAD_SECRET if set, otherwise generated once and kept in the data dir so
    sessions survive restarts and the key never leaves the host."""
    global _secret_cache
    if _secret_cache:
        return _secret_cache
    env = os.getenv("RASAD_SECRET")
    if env:
        _secret_cache = env.encode("utf-8")
        return _secret_cache
    path = os.path.join(get_settings().data_dir, "secret.key")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        with open(path, "rb") as f:
            _secret_cache = f.read().strip()
    else:
        _secret_cache = secrets.token_hex(32).encode("utf-8")
        with open(path, "wb") as f:
            f.write(_secret_cache)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return _secret_cache


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, dk_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(user_id: int, ttl: int = SESSION_TTL_SECONDS, session_version: int | None = 0) -> str:
    payload = _b64(json.dumps({"uid": user_id, "sv": session_version or 0, "exp": int(time.time()) + ttl, "n": secrets.token_hex(4)}).encode())
    sig = _b64(hmac.new(secret_key(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def parse_token(token: str | None) -> int | None:
    t = parse_token_full(token)
    return t[0] if t else None


def parse_token_full(token: str | None) -> tuple[int, int] | None:
    """(user id, session version) from a valid, unexpired token."""
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    expected = _b64(hmac.new(secret_key(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(_unb64(payload))
    except Exception:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return int(data["uid"]), int(data.get("sv", 0))


def token_for(user: User) -> str:
    return make_token(user.id, session_version=user.session_version or 0)


def check_second_factor(db: Session, user: User, code: str | None) -> bool:
    """True when the user has no second factor, or `code` is a fresh TOTP code or an unused
    recovery code (which is then spent)."""
    from . import totp

    if not user.totp_enabled or not user.totp_secret:
        return True
    if not code:
        return False
    step = totp.verify(user.totp_secret, code, last_step=user.totp_last_step)
    if step is not None:
        user.totp_last_step = step
        db.commit()
        return True
    h = totp.hash_recovery(code)
    left = list(user.recovery_hashes or [])
    if h in left:
        left.remove(h)
        user.recovery_hashes = left
        db.commit()
        return True
    return False


def create_user(db: Session, username: str, password: str, role: str = "viewer", display_name: str | None = None, *, must_change: bool = False) -> User:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    username = username.strip().lower()
    if db.scalar(select(User).where(User.username == username)):
        raise ValueError("username already exists")
    u = User(username=username, display_name=display_name or username, role=role, password_hash=hash_password(password), must_change_password=must_change)
    db.add(u)
    db.commit()
    return u


def authenticate(db: Session, username: str, password: str) -> User | None:
    u = db.scalar(select(User).where(User.username == username.strip().lower()))
    if u is None or not u.active or not verify_password(password, u.password_hash):
        return None
    u.last_login_at = datetime.utcnow()
    db.commit()
    return u


def audit(db: Session, user: User | None, action: str, target: str | None = None, detail: dict | None = None, ip: str | None = None) -> None:
    db.add(AuditLog(user_id=user.id if user else None, username=user.username if user else None, action=action, target=target, detail=detail or {}, ip=ip))
    db.commit()


def bootstrap_admin(db: Session) -> str | None:
    """Create the first admin if the users table is empty. The password comes from
    RASAD_ADMIN_PASSWORD or is generated and written once to <data_dir>/admin-password.txt.
    Returns the generated password when one was made, else None."""
    if db.scalar(select(User).limit(1)) is not None:
        return None
    pw = os.getenv("RASAD_ADMIN_PASSWORD")
    generated = None
    if not pw:
        pw = generated = secrets.token_urlsafe(12)
        path = os.path.join(get_settings().data_dir, "admin-password.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(pw + "\n")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    create_user(db, os.getenv("RASAD_ADMIN_USERNAME", "admin"), pw, "admin", "Administrator", must_change=generated is not None)
    return generated


class LoginThrottle:
    """Ten failed attempts per key per quarter hour, in memory; enough for a single instance."""

    def __init__(self, limit: int = 10, window: int = 900) -> None:
        self.limit, self.window = limit, window
        self._hits: dict[str, list[float]] = {}

    def blocked(self, key: str) -> bool:
        now = time.time()
        hits = [t for t in self._hits.get(key, []) if now - t < self.window]
        self._hits[key] = hits
        return len(hits) >= self.limit

    def hit(self, key: str) -> None:
        self._hits.setdefault(key, []).append(time.time())

    def clear(self, key: str) -> None:
        self._hits.pop(key, None)
