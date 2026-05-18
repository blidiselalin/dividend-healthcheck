"""
Sidebar portfolio risk monitor — uses cached session data; refresh on demand only.
"""

from __future__ import annotations

from datetime import datetime
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
from services.portfolio_ui_cache import hydrate_session_from_disk, save_session_cache

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
    save_session_cache()


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
    if not force:
        if get_cached_attention_summary() and st.session_state.get("portfolio_details_rows"):
            return get_cached_attention_summary()
        hydrate_session_from_disk()
        if get_cached_attention_summary() and st.session_state.get("portfolio_details_rows"):
            return get_cached_attention_summary()

    if st.session_state.get(SESSION_REFRESHING_KEY):
        return get_cached_attention_summary()

    st.session_state[SESSION_REFRESHING_KEY] = True
    try:
        if force:
            from services.portfolio_vector_sync import link_portfolio_in_vector_db

            link_portfolio_in_vector_db()
        if rows is None or preload is None:
            from services.portfolio_details_service import PortfolioDetailsService

            rows, preload = PortfolioDetailsService().build_rows_with_cache(
                use_live_prices=force,
            )
        store_portfolio_payload(rows, preload)
        summary = monitor.build_summary(rows, preload, include_news=include_news)
        st.session_state[SESSION_SUMMARY_KEY] = monitor.summary_to_store(summary)
        st.session_state[SESSION_CHECKED_AT_KEY] = datetime.now()
        return summary
    finally:
        st.session_state[SESSION_REFRESHING_KEY] = False


def _rebuild_attention_from_session() -> Optional[AttentionSummary]:
    """Recompute risk/opportunity lists from cached rows (no network)."""
    rows = st.session_state.get("portfolio_details_rows")
    if not rows:
        return None
    from services.portfolio_analysis_preload import PortfolioAnalysisPreload

    preload = PortfolioAnalysisPreload(
        stock_data=st.session_state.get("portfolio_stock_cache", {}),
        yield_channels=st.session_state.get("portfolio_yield_cache", {}),
        vector_docs=st.session_state.get("portfolio_vector_docs", {}),
    )
    monitor = PortfolioRiskMonitorService()
    summary = monitor.build_summary(rows, preload)
    st.session_state[SESSION_SUMMARY_KEY] = monitor.summary_to_store(summary)
    return summary


@st.fragment
def _portfolio_risk_sidebar_fragment() -> None:
    """Show cached risk data; full scan only when the user requests it."""
    hydrate_session_from_disk()

    summary = get_cached_attention_summary()
    if summary is None and st.session_state.get("portfolio_details_rows"):
        summary = _rebuild_attention_from_session()

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
        st.caption(f"Last full reload: {checked_at.strftime('%Y-%m-%d %H:%M')}")

    if summary is None:
        st.info(
            "No portfolio snapshot yet. Use **Reload live data** in the sidebar "
            "to load holdings and run the first scan (~1–2 min)."
        )
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

    if summary.opportunity_total > 0:
        c1, c2 = st.columns(2)
        c1.metric("Buy opportunities", summary.opportunity_total)
        c2.metric("High priority", summary.high_count)
        opp_df = service.to_dataframe(summary, list_kind="opportunity")
        with st.expander(
            f"Buy opportunities ({summary.opportunity_total})",
            expanded=summary.total == 0,
        ):
            st.caption(
                "Green / deep-value yield zones with supportive fundamentals — "
                "candidates worth researching for a buy."
            )
            st.dataframe(
                opp_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "Weight %": st.column_config.NumberColumn(format="%.2f%%"),
                    "Profit %": st.column_config.NumberColumn(format="%+.2f%%"),
                },
            )

    if summary.total == 0:
        st.success("No high-risk holdings flagged.")
    else:
        st.metric("High risk", summary.total)
        watch_df = service.to_dataframe(summary, list_kind="risk")
        with st.expander(
            f"High-risk watchlist ({summary.total})",
            expanded=True,
        ):
            st.caption(
                "Only compounded, high-severity issues (deep losses, sell ratings, "
                "expensive zones while underwater)."
            )
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
        "Refresh risk scan",
        key="portfolio_risk_manual_refresh",
        help="Re-run attention rules on cached holdings (no live price fetch)",
    ):
        with st.spinner("Updating watchlists…"):
            _rebuild_attention_from_session()
        st.rerun()
        return

    if st.button(
        "Reload portfolio & scan",
        key="portfolio_risk_full_reload",
        help="Fetch live prices, rebuild charts, and refresh all watchlists (~1–2 min)",
    ):
        with st.spinner("Reloading portfolio…"):
            refresh_portfolio_risks(force=True)
        st.rerun()
