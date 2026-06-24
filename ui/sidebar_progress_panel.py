"""
Sidebar progress bars for background portfolio and admin tasks.
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


@st.fragment(run_every=timedelta(seconds=2))
def _background_progress_fragment() -> None:
    applied_kinds = apply_background_results()
    jobs = visible_jobs(admin=is_app_admin())
    if not jobs and not applied_kinds:
        return

    st.markdown(
        '<p class="ds-sidebar-heading">Background tasks</p>',
        unsafe_allow_html=True,
    )
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

    rerun_kinds = {
        JOB_YIELD_PRELOAD,
        JOB_WARM_PORTFOLIO,
        JOB_LIVE_RELOAD,
        JOB_PORTFOLIO_DB_REFRESH,
    }
    if applied_kinds and any(kind in rerun_kinds for kind in applied_kinds):
        st.rerun()


def render_sidebar_progress() -> None:
    """Show active background jobs and poll while work is running."""
    jobs = visible_jobs(admin=is_app_admin())
    if jobs or has_active_jobs():
        with st.sidebar:
            if not is_app_admin() or not st.session_state.get("admin_console_active"):
                _background_progress_fragment()
        return

    apply_background_results()
