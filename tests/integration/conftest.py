"""Shared fixtures for live PostgreSQL integration tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _require_postgres(skip_without_postgres):
    """Skip the whole module when DATABASE_URL is unset or Postgres is down."""
