"""
Thread-safe background job registry for Streamlit.

Workers run in daemon threads and must not touch ``st.session_state``.
Completed results are merged on the main thread via ``apply_completed_jobs()``.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from utils.logging_config import get_logger

logger = get_logger("dividendscope.background")

ProgressCallback = Callable[[float, str], None]

_JOB_STORE: dict[str, dict[str, BackgroundJob]] = {}
_STORE_LOCK = threading.Lock()

_DONE_TTL = timedelta(minutes=3)


@dataclass
class BackgroundJob:
    id: str
    kind: str
    label: str
    status: str = "queued"  # queued | running | done | error
    progress: float = 0.0
    message: str = ""
    result: Any = None
    error: str | None = None
    applied: bool = False
    admin_only: bool = False
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None


def session_scope() -> str:
    """Stable key for the current user/session (process-local)."""
    try:
        from auth.user_context import current_user

        user = current_user()
        if user and user.id:
            return str(user.id)
    except Exception:  # noqa: S110
        pass
    return "local"


def _prune_scope(scope: str) -> None:
    jobs = _JOB_STORE.get(scope)
    if not jobs:
        return
    cutoff = datetime.now() - _DONE_TTL
    for job_id, job in list(jobs.items()):
        if job.status in ("done", "error") and job.applied:
            finished = job.finished_at or job.started_at
            if finished < cutoff:
                del jobs[job_id]


def list_jobs(*, scope: str | None = None, include_finished: bool = True) -> list[BackgroundJob]:
    scope_key = scope or session_scope()
    with _STORE_LOCK:
        _prune_scope(scope_key)
        jobs = list(_JOB_STORE.get(scope_key, {}).values())
    jobs.sort(key=lambda job: job.started_at)
    if include_finished:
        return jobs
    return [job for job in jobs if job.status in ("queued", "running")]


def has_active_jobs(*, scope: str | None = None) -> bool:
    return any(
        job.status in ("queued", "running")
        for job in list_jobs(scope=scope, include_finished=False)
    )


def get_job(job_id: str, *, scope: str | None = None) -> BackgroundJob | None:
    scope_key = scope or session_scope()
    with _STORE_LOCK:
        return _JOB_STORE.get(scope_key, {}).get(job_id)


def _find_running_kind(scope: str, kind: str) -> BackgroundJob | None:
    with _STORE_LOCK:
        for job in _JOB_STORE.get(scope, {}).values():
            if job.kind == kind and job.status in ("queued", "running"):
                return job
    return None


def start_job(  # noqa: C901
    kind: str,
    label: str,
    worker: Callable[[ProgressCallback], Any],
    *,
    dedupe: bool = True,
    admin_only: bool = False,
    scope: str | None = None,
) -> str | None:
    """
    Start a background job. Returns job id, or None when dedupe skips a duplicate.
    """
    scope_key = scope or session_scope()
    if dedupe and _find_running_kind(scope_key, kind) is not None:
        return None

    job_id = uuid.uuid4().hex[:12]
    job = BackgroundJob(id=job_id, kind=kind, label=label, admin_only=admin_only)
    captured_user_id: str | None = None
    try:
        from auth.user_context import current_user_id

        captured_user_id = current_user_id()
    except Exception:  # noqa: S110
        pass

    def _progress(value: float, message: str = "") -> None:
        # _STORE_LOCK makes this callback safe to call from the worker thread.
        # Each session has its own scope_key, so concurrent sessions do not
        # share state.  If multi-user parallelism grows, consider per-session
        # locks to reduce contention.
        with _STORE_LOCK:
            stored = _JOB_STORE.get(scope_key, {}).get(job_id)
            if stored is None:
                return
            stored.progress = max(0.0, min(1.0, float(value)))
            if message:
                stored.message = message

    def _run() -> None:
        from auth.user_context import bind_background_user_id

        with _STORE_LOCK:
            stored = _JOB_STORE.get(scope_key, {}).get(job_id)
            if stored:
                stored.status = "running"
                stored.message = "Starting…"
        try:
            with bind_background_user_id(captured_user_id):
                result = worker(_progress)
            with _STORE_LOCK:
                stored = _JOB_STORE.get(scope_key, {}).get(job_id)
                if stored:
                    stored.status = "done"
                    stored.progress = 1.0
                    stored.result = result
                    stored.message = stored.message or "Complete"
                    stored.finished_at = datetime.now()
            logger.info("Background job done kind=%s id=%s", kind, job_id)
        except Exception as exc:
            logger.warning("Background job failed kind=%s id=%s: %s", kind, job_id, exc)
            with _STORE_LOCK:
                stored = _JOB_STORE.get(scope_key, {}).get(job_id)
                if stored:
                    stored.status = "error"
                    stored.error = str(exc)
                    stored.message = "Failed"
                    stored.finished_at = datetime.now()

    with _STORE_LOCK:
        _JOB_STORE.setdefault(scope_key, {})[job_id] = job

    threading.Thread(target=_run, daemon=True, name=f"bg-{kind}").start()
    return job_id


def apply_completed_jobs(
    handlers: dict[str, Callable[[Any], None]],
    *,
    scope: str | None = None,
) -> list[str]:
    """
    Apply finished job results on the main thread.

    Returns kinds of jobs that were applied (empty when none).
    """
    scope_key = scope or session_scope()
    applied_kinds: list[str] = []
    with _STORE_LOCK:
        jobs = list(_JOB_STORE.get(scope_key, {}).values())

    for job in jobs:
        if job.status != "done" or job.applied or job.result is None:
            continue
        handler = handlers.get(job.kind)
        if handler is None:
            continue
        try:
            handler(job.result)
            job.applied = True
            applied_kinds.append(job.kind)
        except Exception as exc:
            logger.warning("Could not apply background job %s: %s", job.id, exc)
            job.status = "error"
            job.error = str(exc)

    return applied_kinds


def acknowledge_jobs(
    *,
    statuses: tuple[str, ...] = ("error",),
    scope: str | None = None,
) -> None:
    """Mark finished jobs acknowledged so UI polling can stop (e.g. shown errors)."""
    scope_key = scope or session_scope()
    with _STORE_LOCK:
        for job in _JOB_STORE.get(scope_key, {}).values():
            if job.status in statuses and not job.applied:
                job.applied = True
