"""Beta trust copy, pricing placeholder, and research disclaimer."""

from __future__ import annotations

import streamlit as st

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
        st.info(RESEARCH_DISCLAIMER)


def render_beta_badge() -> None:
    st.markdown(
        """
        <span style="
            display:inline-block;
            background:#ecfdf5;
            color:#047857;
            border:1px solid #a7f3d0;
            border-radius:999px;
            padding:0.2rem 0.65rem;
            font-size:0.78rem;
            font-weight:600;
            margin-bottom:0.5rem;
        ">Free during beta · No credit card required</span>
        """,
        unsafe_allow_html=True,
    )


def render_beta_pricing_placeholder(*, expanded: bool = False) -> None:
    with st.expander("Pricing (beta)", expanded=expanded):
        st.markdown(
            """
            **Free during beta.**  
            No credit card required.

            **Planned Pro pricing after launch:**  
            $5/month or $40/year.
            """
        )
        st.caption("Stripe checkout is not enabled during beta.")
