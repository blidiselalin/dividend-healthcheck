"""
Sidebar portfolio risk monitor: runs on app load and refreshes every hour.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

import streamlit as st

from services.portfolio_analysis_preload import PortfolioAnalysisPreload
from services.portfolio_attention_service import (
    AttentionSummary,
    PortfolioAttentionService,
    normalize_attention_summary,
)
from services.portfolio_details_service import PortfolioDetailRow
from services.portfolio_risk_monitor_service import PortfolioRiskMonitorService

SESSION_SUMMARY_KEY = "portfolio_attention_summary"
SESSION_CHECKED_AT_KEY = "portfolio_risk_checked_at"
SESSION_REFRESHING_KEY = "portfolio_risk_refresh_in_progress"


def store_portfolio_payload(
    rows: List[PortfolioDetailRow],
    preload: PortfolioAnalysisPreload,
) -> None:
    """Keep portfolio session state in sync with the risk monitor."""
    st.session_state["portfolio_details_rows"] = list(rows)
    st.session_state["portfolio_stock_cache"] = preload.stock_data
    st.session_state["portfolio_yield_cache"] = preload.yield_channels
    st.session_state["portfolio_vector_docs"] = preload.vector_docs
    st.session_state["portfolio_details_time"] = datetime.now()
    st.session_state["portfolio_analysis_ready"] = True
    st.session_state["portfolio_show_analysis"] = True


def get_cached_attention_summary() -> Optional[AttentionSummary]:
    return normalize_attention_summary(
        PortfolioRiskMonitorService.summary_from_store(
            st.session_state.get(SESSION_SUMMARY_KEY)
        )
    )


def refresh_portfolio_risks(
    *,
    force: bool = False,
    include_news: bool = False,
    rows: Optional[List[PortfolioDetailRow]] = None,
    preload: Optional[PortfolioAnalysisPreload] = None,
) -> Optional[AttentionSummary]:
    """
    Reload portfolio data if needed, evaluate all holdings, store full risk list.
    """
    monitor = PortfolioRiskMonitorService()
    checked_at = st.session_state.get(SESSION_CHECKED_AT_KEY)
    if not force and not monitor.is_stale(checked_at) and get_cached_attention_summary():
        return get_cached_attention_summary()

    if st.session_state.get(SESSION_REFRESHING_KEY):
        return get_cached_attention_summary()

    st.session_state[SESSION_REFRESHING_KEY] = True
    try:
        from services.portfolio_vector_sync import link_portfolio_in_vector_db

        link_portfolio_in_vector_db()
        if rows is None or preload is None:
            rows, preload = monitor.load_portfolio_payload()
        store_portfolio_payload(rows, preload)
        summary = monitor.build_summary(rows, preload, include_news=include_news)
        st.session_state[SESSION_SUMMARY_KEY] = monitor.summary_to_store(summary)
        st.session_state[SESSION_CHECKED_AT_KEY] = datetime.now()
        return summary
    finally:
        st.session_state[SESSION_REFRESHING_KEY] = False


@st.fragment(run_every=timedelta(hours=1))
def _portfolio_risk_sidebar_fragment() -> None:
    """Scan all holdings on load; show every flagged ticker; re-scan every hour."""
    from config import is_cloud_runtime

    deferred = st.session_state.get("portfolio_risk_cloud_deferred", False)
    if deferred and is_cloud_runtime():
        _render_risk_sidebar_content(get_cached_attention_summary())
        if st.button(
            "Run portfolio scan (~1–2 min)",
            key="portfolio_risk_cloud_start",
            help="Loads live prices and builds the risk watchlist (required on cloud)",
        ):
            st.session_state["portfolio_risk_cloud_deferred"] = False
            with st.spinner("Scanning portfolio for risk flags…"):
                refresh_portfolio_risks(force=True)
            st.rerun()
        return

    summary = get_cached_attention_summary()
    checked_at = st.session_state.get(SESSION_CHECKED_AT_KEY)
    monitor = PortfolioRiskMonitorService()

    if summary is None or monitor.is_stale(checked_at):
        with st.spinner("Scanning portfolio for risk flags…"):
            summary = refresh_portfolio_risks(force=True)

    _render_risk_sidebar_content(summary)


def render_portfolio_risk_monitor() -> None:
    """Mount the hourly risk fragment in the sidebar (Streamlit fragment API requirement)."""
    with st.sidebar:
        _portfolio_risk_sidebar_fragment()


def _render_risk_sidebar_content(summary: Optional[AttentionSummary] = None) -> None:
    """Render inside `with st.sidebar` (use st.*, not st.sidebar.*)."""
    st.markdown("### Portfolio risks")
    if st.session_state.get(SESSION_REFRESHING_KEY):
        st.caption("Scan in progress…")
        return

    summary = normalize_attention_summary(summary or get_cached_attention_summary())
    checked_at: Optional[datetime] = st.session_state.get(SESSION_CHECKED_AT_KEY)

    if checked_at:
        st.caption(
            f"Last scan: {checked_at.strftime('%Y-%m-%d %H:%M')} · "
            "auto-refresh every hour"
        )

    if summary is None:
        st.info("Risk scan has not completed yet.")
        return

    service = PortfolioAttentionService()
    if summary.dividend_total > 0:
        with st.expander(
            f"Dividend attention ({summary.dividend_total})",
            expanded=False,
        ):
            st.dataframe(
                service.to_dataframe(summary, list_kind="dividend"),
                width="stretch",
                hide_index=True,
                column_config={
                    "Weight %": st.column_config.NumberColumn(format="%.2f%%"),
                    "Profit %": st.column_config.NumberColumn(format="%+.2f%%"),
                },
            )

    if summary.total == 0:
        st.success("No negative risk flags.")
    else:
        c1, c2 = st.columns(2)
        c1.metric("At risk", summary.total)
        c2.metric("High priority", summary.high_count)

        watch_df = service.to_dataframe(summary, list_kind="risk")
        with st.expander(
            f"Risk watchlist ({summary.total})",
            expanded=True,
        ):
            st.dataframe(
                watch_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "Weight %": st.column_config.NumberColumn(format="%.2f%%"),
                    "Profit %": st.column_config.NumberColumn(format="%+.2f%%"),
                },
            )

    if st.button(
        "Refresh risk scan now",
        key="portfolio_risk_manual_refresh",
        help="Reload live prices and re-run all attention rules",
    ):
        with st.spinner("Re-scanning…"):
            refresh_portfolio_risks(force=True)
        st.rerun()
