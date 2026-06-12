"""Shared fixtures for live PostgreSQL integration tests."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _require_postgres(skip_without_postgres: Any) -> None:
    """Skip the whole module when DATABASE_URL is unset or Postgres is down."""
