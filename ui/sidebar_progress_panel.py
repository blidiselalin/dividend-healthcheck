"""
Background job progress for portfolio sidebar tasks.

Progress bars render inside the **Background tasks** expander
(``ui/background_tasks_panel``), not at the top of the sidebar.
"""

from __future__ import annotations

from datetime import timedelta

import streamlit as st

from auth.user_context import is_app_admin
from services.background_jobs import has_active_jobs
from services.deferred_startup import (
    JOB_LIVE_RELOAD,
    JOB_PORTFOLIO_DB_REFRESH,
    JOB_WARM_PORTFOLIO,
    JOB_YIELD_PRELOAD,
    apply_background_results,
    visible_jobs,
)

_RERUN_KINDS = {
    JOB_YIELD_PRELOAD,
    JOB_WARM_PORTFOLIO,
    JOB_LIVE_RELOAD,
    JOB_PORTFOLIO_DB_REFRESH,
}


def _render_job_rows(jobs: list) -> None:
    for job in jobs:
        label = job.label
        if job.message:
            label = f"{job.label} — {job.message}"
        if job.status == "error":
            st.error(f"{job.label}: {job.error or 'failed'}")
            continue
        if job.status in ("queued", "running"):
            st.progress(job.progress, text=label)
        elif job.status == "done":
            st.success(f"{label} ✓")


def render_inline_background_progress(*, poll: bool = False) -> bool:
    """
    Render active background jobs in the current container.

    Returns True when any job row was shown.
    """
    applied_kinds = apply_background_results()
    jobs = visible_jobs(admin=is_app_admin())
    if not jobs and not applied_kinds:
        return False

    st.markdown("**Progress**")
    _render_job_rows(jobs)

    if poll and applied_kinds and any(kind in _RERUN_KINDS for kind in applied_kinds):
        st.rerun()

    return True


@st.fragment(run_every=timedelta(seconds=2))
def _background_progress_poll_fragment() -> None:
    applied_kinds = apply_background_results()
    jobs = visible_jobs(admin=is_app_admin())
    if not jobs:
        return

    st.markdown("**Progress**")
    _render_job_rows(jobs)

    if applied_kinds and any(kind in _RERUN_KINDS for kind in applied_kinds):
        st.rerun()


def render_background_tasks_progress() -> None:
    """Poll and show job progress inside the Background tasks expander."""
    jobs = visible_jobs(admin=is_app_admin())
    if jobs or has_active_jobs():
        _background_progress_poll_fragment()
        return

    render_inline_background_progress(poll=False)


def render_sidebar_progress() -> None:
    """Apply completed background jobs on each rerun (no top-of-sidebar UI)."""
    apply_background_results()
