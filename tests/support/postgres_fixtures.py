"""Reset PostgreSQL pool state and skip helpers for integration tests."""

from __future__ import annotations

import os
import uuid

import pytest


def postgres_configured() -> bool:
    return bool(
        (os.environ.get("DATABASE_URL") or os.environ.get("DIVIDENDSCOPE_DATABASE_URL") or "").strip()
    )


@pytest.fixture
def postgres_env(monkeypatch):
    """Ensure DATABASE_URL is set (CI provides it)."""
    url = os.environ.get("DATABASE_URL") or os.environ.get("DIVIDENDSCOPE_DATABASE_URL")
    if not url:
        monkeypatch.setenv("DATABASE_URL", "postgresql://dividendscope:test@127.0.0.1:5432/dividendscope")
    yield


@pytest.fixture(autouse=False)
def reset_db_connection_state():
    """Clear connection pool between tests so schema can re-apply cleanly."""
    import db.connection as db

    db._pool = None
    db._schema_ready = False
    yield
    db._pool = None
    db._schema_ready = False


@pytest.fixture
def pg_user_id() -> str:
    return f"test-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def skip_without_postgres():
    if not postgres_configured():
        pytest.skip("DATABASE_URL not set — integration test requires PostgreSQL")
