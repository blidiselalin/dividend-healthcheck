"""
Unified portfolio sidebar — reload actions and portfolio edits.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import streamlit as st

from services.portfolio_ui_cache import hydrate_session_from_disk
from ui.portfolio_manage_panel import render_portfolio_manage_sidebar
from ui.portfolio_risk_panel import _rebuild_attention_from_session, refresh_portfolio_risks
from services.portfolio_session import user_has_holdings_in_db
from ui.theme import portfolio_data_ready, sidebar_heading


def _reload_live_data() -> None:
    from ui.portfolio_details_view import _load_portfolio_payload
    from ui.portfolio_risk_panel import store_portfolio_payload

    rows, preload = _load_portfolio_payload(use_live_prices=True)
    store_portfolio_payload(rows, preload)
    refresh_portfolio_risks(force=True, rows=rows, preload=preload)


def render_portfolio_sidebar() -> None:
    """Portfolio sidebar: reload + manage (insights live on Overview)."""
    hydrate_session_from_disk()

    sidebar_heading("Portfolio")
    if portfolio_data_ready():
        loaded_at: Optional[datetime] = st.session_state.get("portfolio_details_time")
        count = len(st.session_state.get("portfolio_details_rows") or [])
        when = loaded_at.strftime("%d %b %H:%M") if loaded_at else "cached"
        st.sidebar.caption(f"{count} holdings · updated {when}")
    elif user_has_holdings_in_db():
        st.sidebar.caption("First load ~1–2 min, then opens from cache.")
    else:
        st.sidebar.caption("No holdings yet — add a ticker under **Manage portfolio**.")

    if st.sidebar.button("Reload live data", type="primary", use_container_width=True):
        with st.spinner("Reloading…"):
            _reload_live_data()
        st.rerun()

    if portfolio_data_ready() and st.sidebar.button(
        "Refresh watchlists",
        use_container_width=True,
        help="Fast refresh of buy/risk lists (no new prices)",
    ):
        with st.spinner("Updating…"):
            _rebuild_attention_from_session()
        st.rerun()

    from ui.analysis_evidence import render_portfolio_session_evidence

    render_portfolio_session_evidence(expanded=False)

    st.sidebar.divider()
    render_portfolio_manage_sidebar()
