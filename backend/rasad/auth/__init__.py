"""Accounts, sessions and the audit log.

Roles: viewer (board, positions, record, briefs), analyst (viewer plus the verification queue,
panel entry and forecast commits), admin (analyst plus user management). Passwords are
PBKDF2-SHA256; sessions are signed cookies carrying only the user id and an expiry. Every
state-changing action is written to the audit log with the user who did it.
"""
