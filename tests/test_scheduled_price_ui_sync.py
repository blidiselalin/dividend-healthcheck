"""Tests for scheduled library price → portfolio UI sync."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


def _mock_streamlit(state: dict) -> MagicMock:
    mock_st = MagicMock()
    mock_st.session_state = state
    return mock_st


def test_scheduled_price_ui_sync_baselines_without_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First observation of last_run_at should not rebuild an already-fresh session."""
    now = datetime.now()
    state = {
        "portfolio_details_rows": [object()],
        "portfolio_details_time": now,
    }
    mock_st = _mock_streamlit(state)
    monkeypatch.setitem(__import__("sys").modules, "streamlit", mock_st)

    with (
        patch("services.portfolio_session.is_demo_session", return_value=False),
        patch(
            "services.price_refresh_scheduler.scheduler_status",
            return_value={
                "enabled": True,
                "last_run_at": (now - timedelta(minutes=5)).isoformat(timespec="seconds"),
                "interval_seconds": 1800,
            },
        ),
        patch("services.deferred_startup.schedule_portfolio_refresh") as refresh,
    ):
        from services.deferred_startup import (
            _UI_APPLIED_LIBRARY_PRICE_REFRESH_AT,
            schedule_scheduled_price_ui_sync_if_needed,
        )

        assert schedule_scheduled_price_ui_sync_if_needed() is None
        refresh.assert_not_called()
        assert state[_UI_APPLIED_LIBRARY_PRICE_REFRESH_AT]


def test_scheduled_price_ui_sync_queues_when_daemon_advances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now()
    earlier = (now - timedelta(minutes=40)).isoformat(timespec="seconds")
    latest = now.isoformat(timespec="seconds")
    state = {
        "portfolio_details_rows": [object()],
        "portfolio_details_time": now - timedelta(minutes=40),
        "_ui_applied_library_price_refresh_at": earlier,
    }
    mock_st = _mock_streamlit(state)
    monkeypatch.setitem(__import__("sys").modules, "streamlit", mock_st)

    with (
        patch("services.portfolio_session.is_demo_session", return_value=False),
        patch(
            "services.price_refresh_scheduler.scheduler_status",
            return_value={
                "enabled": True,
                "last_run_at": latest,
                "interval_seconds": 1800,
            },
        ),
        patch("services.deferred_startup._job_running", return_value=False),
        patch(
            "services.deferred_startup.schedule_portfolio_refresh",
            return_value="job-1",
        ) as refresh,
    ):
        from services.deferred_startup import schedule_scheduled_price_ui_sync_if_needed

        assert schedule_scheduled_price_ui_sync_if_needed() == "job-1"
        refresh.assert_called_once_with(live_prices=False)
        assert state["_ui_queued_library_price_refresh_at"] == latest


def test_scheduled_price_ui_sync_skips_when_scheduler_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"portfolio_details_rows": [object()]}
    mock_st = _mock_streamlit(state)
    monkeypatch.setitem(__import__("sys").modules, "streamlit", mock_st)

    with (
        patch("services.portfolio_session.is_demo_session", return_value=False),
        patch(
            "services.price_refresh_scheduler.scheduler_status",
            return_value={"enabled": False, "last_run_at": None, "interval_seconds": 1800},
        ),
        patch("services.deferred_startup.schedule_portfolio_refresh") as refresh,
    ):
        from services.deferred_startup import schedule_scheduled_price_ui_sync_if_needed

        assert schedule_scheduled_price_ui_sync_if_needed() is None
        refresh.assert_not_called()


def test_scheduled_price_ui_sync_not_gated_on_auto_background(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UI sync must run even when optional auto-background tasks are off."""
    now = datetime.now()
    earlier = (now - timedelta(minutes=40)).isoformat(timespec="seconds")
    latest = now.isoformat(timespec="seconds")
    state = {
        "portfolio_details_rows": [object()],
        "portfolio_details_time": now - timedelta(minutes=40),
        "_ui_applied_library_price_refresh_at": earlier,
        # auto background key absent / false
    }
    mock_st = _mock_streamlit(state)
    monkeypatch.setitem(__import__("sys").modules, "streamlit", mock_st)

    with (
        patch("services.portfolio_session.is_demo_session", return_value=False),
        patch(
            "services.price_refresh_scheduler.scheduler_status",
            return_value={
                "enabled": True,
                "last_run_at": latest,
                "interval_seconds": 1800,
            },
        ),
        patch("services.deferred_startup._job_running", return_value=False),
        patch(
            "services.deferred_startup.schedule_portfolio_refresh",
            return_value="job-2",
        ) as refresh,
        patch(
            "services.background_task_prefs.auto_background_tasks_enabled",
            return_value=False,
        ),
    ):
        from services.deferred_startup import schedule_scheduled_price_ui_sync_if_needed

        assert schedule_scheduled_price_ui_sync_if_needed() == "job-2"
        refresh.assert_called_once_with(live_prices=False)
