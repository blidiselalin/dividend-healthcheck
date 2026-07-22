"""
Unified portfolio sidebar — reload actions and portfolio edits.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from services.portfolio_session import user_has_holdings_in_db
from ui.design_system import render_logo
from ui.portfolio_manage_panel import render_portfolio_manage_sidebar
from ui.portfolio_onboarding import (
    mark_onboarding_live_reload_requested,
    render_onboarding_sidebar_hint,
)
from ui.portfolio_risk_panel import _rebuild_attention_from_session
from ui.theme import portfolio_data_ready, sidebar_heading


def _go_portfolio_section(section_label: str) -> None:
    from ui.theme import PORTFOLIO_SECTION_BY_LABEL, resolve_portfolio_section_label

    section_key = PORTFOLIO_SECTION_BY_LABEL[resolve_portfolio_section_label(section_label)]
    from ui.portfolio_home import navigate_to_portfolio_section

    navigate_to_portfolio_section(section_key)


def _render_sidebar_quick_nav() -> None:
    st.sidebar.caption("Navigate")
    row1 = st.sidebar.columns(2)
    with row1[0]:
        if st.button("Home", key="sidebar_nav_home", use_container_width=True):
            from ui.portfolio_home import navigate_to_portfolio_home

            navigate_to_portfolio_home()
    with row1[1]:
        if st.button("Holdings", key="sidebar_nav_holdings", use_container_width=True):
            from ui.portfolio_home import navigate_to_portfolio_section

            navigate_to_portfolio_section("holdings")
    row2 = st.sidebar.columns(2)
    with row2[0]:
        if st.button("Dividends", key="sidebar_nav_dividends", use_container_width=True):
            _go_portfolio_section("Dividend income")
    with row2[1]:
        if st.button("Income & growth", key="sidebar_nav_growth", use_container_width=True):
            _go_portfolio_section("Dividend growth")
    row3 = st.sidebar.columns(2)
    with row3[0]:
        if st.button("Journal", key="sidebar_nav_journal", use_container_width=True):
            _go_portfolio_section("Purchase journal")
    with row3[1]:
        if st.button("Deposits", key="sidebar_nav_deposits", use_container_width=True):
            _go_portfolio_section("Deposits & benchmarks")


def _reload_live_data() -> None:
    from services.portfolio_refresh import schedule_portfolio_reload

    mark_onboarding_live_reload_requested()
    schedule_portfolio_reload(live_prices=True, sections=["all"])


def render_portfolio_sidebar() -> None:
    """Portfolio sidebar: reload + manage (insights live on Home)."""
    from ui.theme_mode import render_theme_toggle

    render_theme_toggle(sidebar=True)

    render_logo(tagline="Portfolio workspace", sidebar=True)
    _render_sidebar_quick_nav()
    st.sidebar.divider()
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
        loaded_at: datetime | None = st.session_state.get("portfolio_details_time")
        count = len(st.session_state.get("portfolio_details_rows") or [])
        when = loaded_at.strftime("%d %b %H:%M") if loaded_at else "cached"
        st.sidebar.caption(f"{count} holdings · updated {when}")
    elif user_has_holdings_in_db():
        if st.session_state.get("portfolio_fast_loaded"):
            st.sidebar.caption("Charts not loaded — open **Background tasks** to preload.")
        else:
            st.sidebar.caption(
                "Holdings not loaded yet — open **Background tasks** → **Load portfolio**."
            )
    else:
        st.sidebar.caption("No holdings yet — add a ticker under **Manage portfolio**.")

    if st.sidebar.button("Reload live data", type="primary", use_container_width=True):
        _reload_live_data()
        st.toast("Refreshing live prices in the background…")
        st.rerun()

    from ui.background_tasks_panel import render_background_tasks_panel

    render_background_tasks_panel()

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
