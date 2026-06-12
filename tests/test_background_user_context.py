"""Tests for background user binding in worker threads."""
# ruff: noqa: S101

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import patch

from auth.user_context import bind_background_user_id, current_user_id
from services.background_jobs import apply_completed_jobs, start_job


def test_bind_background_user_id_visible_in_worker_thread() -> None:
    seen: list[str | None] = []

    def run() -> None:
        with bind_background_user_id("user-abc"):
            seen.append(current_user_id())

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(timeout=2)
    assert seen == ["user-abc"]


def test_background_job_binds_scheduled_user_id() -> None:
    captured: list[str | None] = []

    def worker(progress: Any) -> Any:
        captured.append(current_user_id())
        return {"ok": True}

    with patch("auth.user_context.current_user_id", return_value="user-xyz"):
        job_id = start_job(
            "user_bind_test",
            "Bind user",
            worker,
            scope="user-bind-scope",
            dedupe=False,
        )

    assert job_id is not None
    deadline = time.time() + 5
    while time.time() < deadline and not captured:
        time.sleep(0.05)

    assert captured == ["user-xyz"]

    applied = []
    apply_completed_jobs(
        {"user_bind_test": lambda result: applied.append(result)},
        scope="user-bind-scope",
    )
    assert applied == [{"ok": True}]
