from __future__ import annotations

import os
from datetime import date

import pytest

os.environ.setdefault("RASAD_MODEL_PROVIDER", "rules")
os.environ.setdefault("RASAD_SECRET", "test-secret")
os.environ.setdefault("RASAD_ADMIN_PASSWORD", "bootstrap-admin-pw")

# a throwaway vendor key so the suite runs licensed (the real vendor key never enters the repo)
import json as _json  # noqa: E402
import tempfile as _tempfile  # noqa: E402

_lic_dir = _tempfile.mkdtemp(prefix="rasad-lic-")
from rasad import licence as _licence  # noqa: E402

_pub = _licence.keygen(os.path.join(_lic_dir, "vendor.key"))
_licence.VENDOR_PUBLIC_KEY_B64 = _pub  # tests patch the constant; the product has no override
with open(os.path.join(_lic_dir, "licence.json"), "w", encoding="utf-8") as _f:
    _json.dump(_licence.issue(os.path.join(_lic_dir, "vendor.key"), licensee="Test suite", seats=50, expires="2099-01-01", features=["core", "arabic", "api", "model", "export"]), _f)
os.environ["RASAD_LICENCE_FILE"] = os.path.join(_lic_dir, "licence.json")

from rasad.db import reset_engine_for_tests, session_factory  # noqa: E402
from rasad.seed import load as seed_load  # noqa: E402

AS_OF = date(2026, 10, 18)


@pytest.fixture(scope="session")
def seeded_db_url(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "test.db"
    # RASAD_TEST_DATABASE_URL=postgresql+psycopg://... runs the whole suite against PostgreSQL
    url = os.getenv("RASAD_TEST_DATABASE_URL") or f"sqlite:///{path}"
    reset_engine_for_tests(url)
    seed_load.seed(AS_OF, history_days=10)
    return url


@pytest.fixture
def db(seeded_db_url):
    s = session_factory()()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture(scope="session")
def users(seeded_db_url):
    from rasad.auth.core import create_user

    s = session_factory()()
    try:
        create_user(s, "admin", "admin-password-1", "admin", "Admin")
        create_user(s, "ana", "analyst-password-1", "analyst", "Analyst")
        create_user(s, "viewer", "viewer-password-1", "viewer", "Viewer")
    finally:
        s.close()
    return {"admin": "admin-password-1", "ana": "analyst-password-1", "viewer": "viewer-password-1"}


def _client_as(username: str, password: str):
    from fastapi.testclient import TestClient

    from rasad.api.app import app

    c = TestClient(app, headers={"X-Rasad-Client": "tests"})
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def client(seeded_db_url, users):
    """Signed in as an analyst (the role most tests need)."""
    return _client_as("ana", users["ana"])


@pytest.fixture
def admin_client(seeded_db_url, users):
    return _client_as("admin", users["admin"])


@pytest.fixture
def viewer_client(seeded_db_url, users):
    return _client_as("viewer", users["viewer"])


@pytest.fixture
def anon_client(seeded_db_url, users):
    from fastapi.testclient import TestClient

    from rasad.api.app import app

    return TestClient(app, headers={"X-Rasad-Client": "tests"})
