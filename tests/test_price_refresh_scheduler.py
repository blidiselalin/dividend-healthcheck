"""Tests for the 5-minute price refresh scheduler."""
# ruff: noqa: S101

from __future__ import annotations

from unittest.mock import patch

import pytest

from services.price_refresh_scheduler import (
    run_price_refresh_once,
    scheduler_status,
    start_price_refresh_scheduler,
)


def test_run_price_refresh_once_updates_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIVIDENDSCOPE_DISABLE_PRICE_SCHEDULER", raising=False)
    with patch(
        "services.db_price_refresh.refresh_market_library_prices",
        return_value={"total": 3, "updated": 2, "skipped": 1, "errors": 0},
    ):
        stats = run_price_refresh_once()
    assert stats["updated"] == 2
    status = scheduler_status()
    assert status["last_stats"]["updated"] == 2
    assert status["last_run_at"] is not None


def test_start_price_refresh_scheduler_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.price_refresh_scheduler as mod

    monkeypatch.setattr(mod, "_started", False)
    monkeypatch.delenv("DIVIDENDSCOPE_DISABLE_PRICE_SCHEDULER", raising=False)
    monkeypatch.delenv("PYTEST_USE_SQLITE", raising=False)
    with patch.object(mod, "_refresh_loop"):
        assert mod.start_price_refresh_scheduler(interval_seconds=300) is True
        assert mod.start_price_refresh_scheduler(interval_seconds=300) is False


def test_scheduler_disabled_under_pytest_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_USE_SQLITE", "1")
    assert start_price_refresh_scheduler() is False
    assert scheduler_status()["enabled"] is False
