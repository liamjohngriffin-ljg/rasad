from __future__ import annotations

import os
from datetime import date

import pytest

os.environ.setdefault("RASAD_MODEL_PROVIDER", "rules")

from rasad.db import reset_engine_for_tests, session_factory  # noqa: E402
from rasad.seed import load as seed_load  # noqa: E402

AS_OF = date(2026, 10, 18)


@pytest.fixture(scope="session")
def seeded_db_url(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "test.db"
    url = f"sqlite:///{path}"
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


@pytest.fixture
def client(seeded_db_url):
    from fastapi.testclient import TestClient

    from rasad.api.app import app

    return TestClient(app)
