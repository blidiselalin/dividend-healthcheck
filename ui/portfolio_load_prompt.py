"""Prompt to load portfolio session rows when the DB already has holdings."""

from __future__ import annotations

import streamlit as st

from ui.theme import render_notice


def render_portfolio_load_prompt(*, key_prefix: str = "portfolio") -> None:
    """Offer a synchronous load when holdings exist in the DB but not in session."""
    render_notice(
        "<strong>Portfolio not loaded in this session.</strong> "
        "Load holdings from the database now, or use **Background tasks** → "
        "<strong>Load portfolio</strong> in the sidebar.",
        kind="info",
    )
    if st.button(
        "Load portfolio now",
        type="primary",
        key=f"{key_prefix}_load_portfolio_now",
        use_container_width=False,
    ):
        from services.portfolio_refresh import reload_portfolio_after_data_import

        reload_portfolio_after_data_import(section_label="Home")
        st.rerun()
