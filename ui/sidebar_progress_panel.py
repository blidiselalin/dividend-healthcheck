"""
Sidebar progress bars for background portfolio and admin tasks.
"""

from __future__ import annotations

from datetime import timedelta

import streamlit as st

from auth.user_context import is_app_admin
from services.background_jobs import has_active_jobs
from services.deferred_startup import (
    JOB_HISTORY_BACKFILL,
    JOB_LIVE_RELOAD,
    JOB_WARM_PORTFOLIO,
    JOB_YIELD_PRELOAD,
    apply_background_results,
    schedule_hourly_market_update,
    visible_jobs,
)
from ui.theme import sidebar_heading


@st.cache_data(ttl=120, show_spinner=False)
def _cached_thin_history_summary() -> dict:
    from services.stock_history_backfill import thin_history_summary

    return thin_history_summary()


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

    rerun_kinds = {JOB_YIELD_PRELOAD, JOB_WARM_PORTFOLIO, JOB_LIVE_RELOAD}
    if applied_kinds and any(kind in rerun_kinds for kind in applied_kinds):
        st.rerun()


def render_sidebar_progress() -> None:
    """Show active background jobs and poll while work is running."""
    jobs = visible_jobs(admin=is_app_admin())
    if jobs or has_active_jobs():
        with st.sidebar:
            _background_progress_fragment()
        return

    apply_background_results()


def render_admin_market_update_controls() -> None:
    """Admin-only control to refresh the shared stock library in the background."""
    if not is_app_admin():
        return

    try:
        summary = _cached_thin_history_summary()
        if summary["thin_history"]:
            st.sidebar.caption(
                f"Library history: {summary['yield_ready']}/{summary['total']} yield-ready · "
                f"{summary['thin_history']} need backfill"
            )
    except Exception:
        pass

    sidebar_heading("Admin")
    if st.sidebar.button(
        "Update stock library",
        use_container_width=True,
        help="Refresh prices and enrich stale symbols without blocking the UI",
        key="admin_hourly_market_update",
    ):
        job_id = schedule_hourly_market_update()
        if job_id:
            st.toast("Stock library update started in the background")
        else:
            st.toast("Update already running")
        st.rerun()

    if st.sidebar.button(
        "Backfill thin history",
        use_container_width=True,
        help="Fetch missing price/dividend series into stock_documents (yield channels)",
        key="admin_history_backfill",
    ):
        from services.deferred_startup import schedule_history_backfill

        job_id = schedule_history_backfill(limit=40)
        if job_id:
            st.toast("History backfill started in the background")
        else:
            st.toast("Backfill already running")
        st.rerun()

    if st.sidebar.button(
        "Sync history tables",
        use_container_width=True,
        help="Copy JSONB price/dividend arrays into stock_price_history / stock_dividend_history",
        key="admin_sync_history_tables",
    ):
        from services.deferred_startup import schedule_history_table_sync

        job_id = schedule_history_table_sync(limit=200)
        if job_id:
            st.toast("History table sync started in the background")
        else:
            st.toast("Sync already running")
        st.rerun()

    summary = st.session_state.get("last_hourly_update_summary")
    if summary:
        enrich = summary.get("enrich") or {}
        st.sidebar.caption(
            f"Last update: enriched {enrich.get('enriched', 0)} symbols "
            f"({summary.get('elapsed_seconds', '?')}s)"
        )
