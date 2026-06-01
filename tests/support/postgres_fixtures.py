"""Reset PostgreSQL pool state and skip helpers for integration tests."""

from __future__ import annotations

import os
import uuid

import pytest

_postgres_reachable: bool | None = None


def postgres_configured() -> bool:
    return bool(
        (os.environ.get("DATABASE_URL") or os.environ.get("DIVIDENDSCOPE_DATABASE_URL") or "").strip()
    )


def postgres_reachable() -> bool:
    """Return True when DATABASE_URL points at a live server (cached per session)."""
    global _postgres_reachable
    if _postgres_reachable is not None:
        return _postgres_reachable
    if not postgres_configured():
        _postgres_reachable = False
        return False
    url = os.environ.get("DATABASE_URL") or os.environ.get("DIVIDENDSCOPE_DATABASE_URL")
    try:
        import psycopg

        with psycopg.connect(url, connect_timeout=2):
            pass
        _postgres_reachable = True
    except Exception:
        _postgres_reachable = False
    return _postgres_reachable


@pytest.fixture
def postgres_env(monkeypatch):
    """Enable Postgres mode for tests that mock the database layer."""
    monkeypatch.delenv("PYTEST_USE_SQLITE", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://mock:mock@127.0.0.1:59999/mockdb")
    import db.connection as db

    db._pool = None
    db._schema_ready = False
    yield
    db._pool = None
    db._schema_ready = False


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
    if not postgres_reachable():
        pytest.skip("PostgreSQL unavailable — integration test requires a live DATABASE_URL")
