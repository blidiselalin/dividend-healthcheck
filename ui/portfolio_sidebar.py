"""
Unified portfolio sidebar — reload actions and portfolio edits.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import streamlit as st

from services.portfolio_ui_cache import hydrate_session_from_disk
from ui.portfolio_manage_panel import render_portfolio_manage_sidebar
from ui.portfolio_onboarding import mark_onboarding_live_reload_requested, render_onboarding_sidebar_hint
from ui.portfolio_risk_panel import _rebuild_attention_from_session
from services.portfolio_session import user_has_holdings_in_db
from ui.theme import portfolio_data_ready, sidebar_heading


def _reload_live_data() -> None:
    from services.portfolio_refresh import schedule_portfolio_reload

    mark_onboarding_live_reload_requested()
    schedule_portfolio_reload(live_prices=True, sections=["all"])


def render_portfolio_sidebar() -> None:
    """Portfolio sidebar: reload + manage (insights live on Home)."""
    if not st.session_state.get("portfolio_details_rows"):
        hydrate_session_from_disk()

    sidebar_heading("Portfolio")
    render_onboarding_sidebar_hint()
    if st.sidebar.button(
        "Home",
        use_container_width=True,
        type="primary",
        key="nav_portfolio_home",
        help="Return to portfolio home (summary, research, and overview)",
    ):
        from ui.portfolio_home import navigate_to_portfolio_home

        navigate_to_portfolio_home()

    if portfolio_data_ready():
        loaded_at: Optional[datetime] = st.session_state.get("portfolio_details_time")
        count = len(st.session_state.get("portfolio_details_rows") or [])
        when = loaded_at.strftime("%d %b %H:%M") if loaded_at else "cached"
        st.sidebar.caption(f"{count} holdings · updated {when}")
    elif user_has_holdings_in_db():
        if st.session_state.get("portfolio_fast_loaded"):
            st.sidebar.caption("Loading charts in background…")
        else:
            st.sidebar.caption("Loading from library… use **Reload live data** for fresh prices.")
    else:
        st.sidebar.caption("No holdings yet — add a ticker under **Manage portfolio**.")

    if st.sidebar.button("Reload live data", type="primary", use_container_width=True):
        _reload_live_data()
        st.toast("Refreshing live prices in the background…")
        st.rerun()

    if portfolio_data_ready() and st.sidebar.button(
        "Refresh watchlists",
        use_container_width=True,
        help="Fast refresh of buy/risk lists (no new prices)",
    ):
        with st.spinner("Updating…"):
            _rebuild_attention_from_session()
        st.rerun()

    from ui.portfolio_risk_panel import render_portfolio_risk_monitor

    render_portfolio_risk_monitor()

    from ui.analysis_evidence import render_portfolio_session_evidence

    render_portfolio_session_evidence(expanded=False)

    st.sidebar.divider()
    render_portfolio_manage_sidebar()
