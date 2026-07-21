"""Beta trust copy, pricing placeholder, and research disclaimer."""

from __future__ import annotations

import streamlit as st

from ui.design_system import render_beta_badge, render_disclaimer_banner

RESEARCH_DISCLAIMER = (
    "This app is for dividend tracking and research only. It does not provide financial advice."
)

YIELD_HISTORY_HELP = (
    "Dividend yield history helps you understand whether the current yield is high, low, "
    "or normal compared with the stock's past."
)


def render_research_disclaimer(*, compact: bool = False) -> None:
    if compact:
        st.caption(RESEARCH_DISCLAIMER)
    else:
        render_disclaimer_banner(RESEARCH_DISCLAIMER)


def render_beta_pricing_placeholder(*, expanded: bool = False) -> None:
    with st.expander("Pricing (beta)", expanded=expanded):
        render_beta_badge(extra="Free during beta")
        st.markdown(
            """
            **No credit card required.**

            **Planned Pro pricing after launch:**
            $5/month or $40/year.
            """
        )
        st.caption("Stripe checkout is not enabled during beta.")
