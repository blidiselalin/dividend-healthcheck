"""Tests for background task preference gating."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.background_task_prefs import (
    AUTO_BACKGROUND_TASKS_KEY,
    auto_background_tasks_enabled,
    set_auto_background_tasks_enabled,
)


def test_auto_background_tasks_disabled_by_default() -> None:
    mock_st = MagicMock()
    mock_st.session_state = {}
    with patch.dict("sys.modules", {"streamlit": mock_st}):
        assert auto_background_tasks_enabled() is False


def test_set_auto_background_tasks_enabled() -> None:
    state: dict = {}
    mock_st = MagicMock()
    mock_st.session_state = state
    with patch.dict("sys.modules", {"streamlit": mock_st}):
        set_auto_background_tasks_enabled(True)
        assert state[AUTO_BACKGROUND_TASKS_KEY] is True


def test_schedule_startup_tasks_skips_when_auto_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_st = MagicMock()
    mock_st.session_state = {}
    monkeypatch.setitem(__import__("sys").modules, "streamlit", mock_st)

    with (
        patch("services.deferred_startup.schedule_dividend_sync_if_needed") as sync,
        patch("services.deferred_startup.schedule_coverage_badge_refresh") as cov,
    ):
        from services.deferred_startup import schedule_startup_tasks

        schedule_startup_tasks(is_demo=False, has_holdings=True)
        sync.assert_not_called()
        cov.assert_not_called()


def test_schedule_startup_tasks_runs_when_auto_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_st = MagicMock()
    mock_st.session_state = {AUTO_BACKGROUND_TASKS_KEY: True}
    monkeypatch.setitem(__import__("sys").modules, "streamlit", mock_st)

    with (
        patch("services.deferred_startup.schedule_dividend_sync_if_needed") as sync,
        patch("services.deferred_startup._library_reload_needed", return_value=False),
        patch("services.deferred_startup.schedule_portfolio_warm_if_needed"),
        patch("services.deferred_startup.schedule_yield_preload_if_needed"),
        patch("services.deferred_startup.schedule_stale_price_refresh_if_needed"),
        patch("services.deferred_startup.schedule_coverage_badge_refresh"),
        patch("services.deferred_startup.schedule_auto_backfill_if_needed"),
    ):
        from services.deferred_startup import schedule_startup_tasks

        schedule_startup_tasks(is_demo=False, has_holdings=True)
        sync.assert_called_once()
