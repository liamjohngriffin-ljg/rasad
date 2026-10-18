"""Operator CLI for accounts.

  python -m rasad.auth.cli create <username> <role> [display name]     prompts for a password
  python -m rasad.auth.cli password <username>                          reset a password
  python -m rasad.auth.cli role <username> <role>
  python -m rasad.auth.cli deactivate <username>
  python -m rasad.auth.cli list
"""

from __future__ import annotations

import getpass
import sys

from sqlalchemy import select

from ..db import init_db, session_factory
from .core import create_user, hash_password
from .models import ROLES, User


def main(argv: list[str]) -> None:
    init_db()
    db = session_factory()()
    try:
        cmd = argv[0] if argv else "list"
        if cmd == "create":
            username, role = argv[1], argv[2]
            display = " ".join(argv[3:]) or username
            pw = getpass.getpass("Password: ")
            if pw != getpass.getpass("Again: "):
                print("passwords differ")
                return
            u = create_user(db, username, pw, role, display)
            print(f"created {u.username} ({u.role})")
        elif cmd == "password":
            u = db.scalar(select(User).where(User.username == argv[1].lower()))
            if u is None:
                print("no such user")
                return
            pw = getpass.getpass("New password: ")
            u.password_hash = hash_password(pw)
            u.must_change_password = False
            db.commit()
            print("updated")
        elif cmd == "role":
            u = db.scalar(select(User).where(User.username == argv[1].lower()))
            if u is None or argv[2] not in ROLES:
                print("no such user or bad role")
                return
            u.role = argv[2]
            db.commit()
            print(f"{u.username} is now {u.role}")
        elif cmd == "deactivate":
            u = db.scalar(select(User).where(User.username == argv[1].lower()))
            if u is None:
                print("no such user")
                return
            u.active = False
            db.commit()
            print("deactivated")
        else:
            for u in db.scalars(select(User).order_by(User.username)).all():
                print(f"{u.username:20s} {u.role:8s} {'active' if u.active else 'inactive':8s} last login {u.last_login_at or '-'}")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
