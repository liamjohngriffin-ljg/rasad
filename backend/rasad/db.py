from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = get_settings().database_url
        kwargs = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, future=True, **kwargs)
        if url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _fk_on(dbapi_conn, _):  # pragma: no cover - trivial
                dbapi_conn.execute("PRAGMA foreign_keys=ON")

        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (registers tables)

    engine = get_engine()
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)


def _add_missing_columns(engine) -> None:
    """Forward-only schema catch-up for columns added after a database was created. Tables
    come from create_all; columns added to an existing table are appended here with their
    declared type and no constraint, which is what every release so far has needed."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"]: c for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing:
                    ctype = col.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {ctype}'))
                    continue
                # widened string columns (PostgreSQL enforces lengths; SQLite ignores them)
                want = getattr(col.type, "length", None)
                have_len = getattr(existing[col.name]["type"], "length", None)
                if engine.dialect.name == "postgresql" and want and have_len and have_len < want:
                    conn.execute(text(f'ALTER TABLE {table.name} ALTER COLUMN "{col.name}" TYPE VARCHAR({want})'))


def reset_engine_for_tests(url: str) -> None:
    """Point the module at a fresh database (used by the test suite)."""
    global _engine, _SessionLocal
    get_settings().database_url = url
    _engine = None
    _SessionLocal = None
    init_db()
