"""
Sidebar controls to run portfolio background tasks on demand.
"""

from __future__ import annotations

import streamlit as st

from services.background_jobs import has_active_jobs
from services.background_task_prefs import (
    auto_background_tasks_enabled,
    set_auto_background_tasks_enabled,
)
from services.portfolio_session import user_has_holdings_in_db


def render_background_tasks_panel() -> None:
    """Background task preferences and manual triggers (off by default)."""
    with st.sidebar.expander("Background tasks", expanded=False):
        st.caption(
            "Automatic enrichment is **off by default** for faster startup. "
            "Use the buttons below to refresh data when you want it, or enable "
            "automatic tasks for future visits this session."
        )
        auto_enabled = st.checkbox(
            "Run background tasks automatically on load",
            value=auto_background_tasks_enabled(),
            key="background_tasks_auto_checkbox",
            help=(
                "When enabled, dividend sync, yield charts, stale price refresh, "
                "and similar jobs may start after the first screen loads."
            ),
        )
        if auto_enabled != auto_background_tasks_enabled():
            set_auto_background_tasks_enabled(auto_enabled)

        has_rows = bool(st.session_state.get("portfolio_details_rows"))
        busy = has_active_jobs()

        st.markdown("**Run now**")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button(
                "Load portfolio",
                use_container_width=True,
                disabled=not user_has_holdings_in_db() or busy,
                help="Read holdings from the shared library (no live prices)",
            ):
                from services.deferred_startup import trigger_portfolio_load

                trigger_portfolio_load()
                st.toast("Loading portfolio in the background…")
                st.rerun()
        with col_b:
            if st.button(
                "Live prices",
                use_container_width=True,
                disabled=not user_has_holdings_in_db() or busy,
                help="Fetch live quotes and refresh portfolio rows",
            ):
                from services.portfolio_refresh import schedule_portfolio_reload

                schedule_portfolio_reload(live_prices=True, sections=["all"])
                st.toast("Refreshing live prices in the background…")
                st.rerun()

        col_c, col_d = st.columns(2)
        with col_c:
            if st.button(
                "Sync dividends",
                use_container_width=True,
                disabled=not user_has_holdings_in_db() or busy,
                help="Record paid dividends from market history into your portfolio",
            ):
                from services.deferred_startup import schedule_forced_dividend_sync

                schedule_forced_dividend_sync()
                st.toast("Syncing dividends in the background…")
                st.rerun()
        with col_d:
            if st.button(
                "Yield charts",
                use_container_width=True,
                disabled=not has_rows or busy,
                help="Preload yield-channel charts for current holdings",
            ):
                from services.deferred_startup import trigger_yield_preload

                trigger_yield_preload()
                st.toast("Loading yield charts in the background…")
                st.rerun()

        if st.button(
            "Refresh stale prices",
            use_container_width=True,
            disabled=not has_rows or busy,
            help="Update only holdings whose cached quotes are marked stale",
        ):
            from services.deferred_startup import trigger_stale_price_refresh

            trigger_stale_price_refresh()
            st.toast("Refreshing stale prices…")
            st.rerun()

        if st.button(
            "Backfill thin history",
            use_container_width=True,
            disabled=not has_rows or busy,
            help="Enrich price/dividend history for holdings missing yield-chart data",
        ):
            from services.deferred_startup import trigger_portfolio_history_backfill

            trigger_portfolio_history_backfill()
            st.toast("Starting history backfill…")
            st.rerun()

        if busy:
            st.caption("A background task is already running — see progress above.")
