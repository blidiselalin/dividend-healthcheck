"""Tests for background job scheduling."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from services.background_jobs import (
    apply_completed_jobs,
    has_active_jobs,
    list_jobs,
    session_scope,
    start_job,
)


def test_start_job_runs_worker_and_applies_result():
    scope = "test-scope"
    applied = []

    def worker(progress):
        progress(0.5, "halfway")
        return {"value": 42}

    job_id = start_job("test_kind", "Test job", worker, scope=scope, dedupe=False)
    assert job_id is not None

    deadline = time.time() + 5
    while time.time() < deadline:
        jobs = list_jobs(scope=scope)
        if jobs and jobs[0].status == "done":
            break
        time.sleep(0.05)

    jobs = list_jobs(scope=scope)
    assert len(jobs) == 1
    assert jobs[0].status == "done"
    assert jobs[0].progress == 1.0

    def handler(result):
        applied.append(result["value"])

    assert apply_completed_jobs({"test_kind": handler}, scope=scope) is True
    assert applied == [42]
    assert jobs[0].applied is True


def test_start_job_dedupes_same_kind():
    scope = "dedupe-scope"

    def worker(progress):
        time.sleep(0.2)
        return True

    first = start_job("dup_kind", "First", worker, scope=scope)
    second = start_job("dup_kind", "Second", worker, scope=scope)
    assert first is not None
    assert second is None
    assert has_active_jobs(scope=scope) is True


def test_schedule_yield_preload_skips_when_ready(monkeypatch):
    mock_st = MagicMock()
    mock_st.session_state = {
        "portfolio_analysis_ready": True,
        "portfolio_fast_loaded": True,
        "portfolio_details_rows": [MagicMock(ticker="AAPL")],
    }
    monkeypatch.setitem(__import__("sys").modules, "streamlit", mock_st)

    with patch("services.background_jobs.start_job") as start:
        from services.deferred_startup import schedule_yield_preload_if_needed

        schedule_yield_preload_if_needed()
        start.assert_not_called()


def test_session_scope_falls_back_to_local():
    with patch("auth.user_context.current_user", return_value=None):
        assert session_scope() == "local"
