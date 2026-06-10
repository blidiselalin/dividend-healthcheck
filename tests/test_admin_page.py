"""Tests for admin console scheduling and coverage helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.sp500_peers_service import top_dividend_coverage_stats


def test_top_dividend_coverage_stats_counts_universe(monkeypatch):
    monkeypatch.setattr(
        "data_ingestion.dividend_universe.get_top_dividend_symbols",
        lambda: ["KO", "PEP", "JNJ"],
    )
    store = MagicMock()
    store.count_symbols_in.return_value = 2
    monkeypatch.setattr("services.sp500_peers_service._store", lambda: store)

    stats = top_dividend_coverage_stats(force=True)
    assert stats["universe_total"] == 3
    assert stats["analysed_top_dividend"] == 2
    assert stats["pct_covered"] == pytest.approx(66.67, rel=0.1)


def test_schedule_ensure_sp500_requires_admin(monkeypatch):
    monkeypatch.setattr("auth.user_context.is_app_admin", lambda: False)
    from services.deferred_startup import schedule_ensure_sp500

    assert schedule_ensure_sp500() is None


def test_schedule_ensure_top_dividend_starts_job(monkeypatch):
    monkeypatch.setattr("auth.user_context.is_app_admin", lambda: True)
    with patch("services.deferred_startup.start_job", return_value="job-1") as start:
        from services.deferred_startup import schedule_ensure_top_dividend

        job_id = schedule_ensure_top_dividend(limit=5)
        assert job_id == "job-1"
        assert start.call_args.kwargs.get("admin_only") is True


def test_schedule_ensure_sp500_starts_job(monkeypatch):
    monkeypatch.setattr("auth.user_context.is_app_admin", lambda: True)
    with patch("services.deferred_startup.start_job", return_value="job-2") as start:
        from services.deferred_startup import schedule_ensure_sp500

        job_id = schedule_ensure_sp500(limit=10)
        assert job_id == "job-2"
        start.assert_called_once()
        assert start.call_args[0][0] == "ensure_sp500"


def test_schedule_price_refresh_requires_admin(monkeypatch):
    monkeypatch.setattr("auth.user_context.is_app_admin", lambda: False)
    from services.deferred_startup import schedule_price_refresh

    assert schedule_price_refresh() is None


def test_schedule_price_refresh_starts_job(monkeypatch):
    monkeypatch.setattr("auth.user_context.is_app_admin", lambda: True)
    with patch("services.deferred_startup.start_job", return_value="job-3") as start:
        from services.deferred_startup import schedule_price_refresh

        job_id = schedule_price_refresh()
        assert job_id == "job-3"
        assert start.call_args[0][0] == "price_refresh"
        assert start.call_args.kwargs.get("admin_only") is True


def test_admin_console_session_helpers(monkeypatch):
    session: dict = {}
    monkeypatch.setattr("streamlit.session_state", session, raising=False)

    from ui.admin_page import (
        is_admin_console_active,
        set_admin_console_active,
    )

    assert is_admin_console_active() is False
    set_admin_console_active(True)
    assert is_admin_console_active() is True
    set_admin_console_active(False)
    assert is_admin_console_active() is False
