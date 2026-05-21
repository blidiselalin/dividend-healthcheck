"""
What DividendScope is for — purpose, scope, data sources, and how to use it.
"""

from __future__ import annotations

import streamlit as st

from config import DATA_SOURCES, MAX_HISTORY_YEARS


def render_about_body() -> None:
    """Full about text (no expander wrapper)."""
    _render_purpose()
    st.divider()
    _render_what_you_manage()
    st.divider()
    _render_how_it_helps()
    st.divider()
    _render_data_sources()


def render_app_about(*, expanded: bool | None = None) -> None:
    """
    Explain the app's purpose, what it manages, and how analysis helps investors.

    If expanded is None, uses session state portfolio_show_about (default collapsed).
    """
    if expanded is None:
        expanded = bool(st.session_state.get("portfolio_show_about", False))

    with st.expander("What is DividendScope?", expanded=expanded):
        render_about_body()


def render_app_about_compact() -> None:
    """Short intro for login or narrow spaces."""
    st.markdown(
        "**DividendScope** helps dividend investors **manage a portfolio**, "
        "**compare** quality income stocks, and read **clear statistics** built from "
        "years of public market and dividend history."
    )


def _render_purpose() -> None:
    st.markdown("#### Purpose")
    st.markdown(
        """
        DividendScope is a private workspace for **long-term dividend investing**.
        It brings your holdings, cash flows, and stock research into one place so you
        can judge **safety**, **value**, and **income** with the same historical lens
        on every ticker — not just a live price quote.
        """
    )


def _render_what_you_manage() -> None:
    st.markdown("#### What you manage here")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            """
            **Your portfolio**
            - Positions (shares, cost, dividends received)
            - Purchase journal and monthly deposits
            - Performance vs money you put in (€ / $)

            **Income view**
            - Dividend calendar and cash received
            - Dividend growth per share over time
            """
        )
    with col2:
        st.markdown(
            """
            **Research library (shared for all users)**
            - **S&P analysed stocks** — one server-wide database of historical prices and dividends
            - Same-sector comparison against your other holdings

            **Watchlists** (after reload)
            - Buy ideas (value + yield zones)
            - High-risk holdings only when severity is real
            """
        )


def _render_how_it_helps() -> None:
    st.markdown("#### How it helps you decide")
    st.markdown(
        f"""
        | Goal | What the app does |
        |------|-------------------|
        | **Identify** candidates | Yield **channels** (fair / expensive zones), dividend **safety** and growth scores, and **buy opportunity** flags when price and fundamentals align |
        | **Compare** stocks | Side-by-side scores for **other holdings in the same sector**; holding vs analysed history on one screen |
        | **Clear statistics** | Up to **{MAX_HISTORY_YEARS} years** of dividend and price context from the analysed library; portfolio KPIs, CAGR, allocation, and monthly income charts |

        Each holding can be opened for a full report: yield zone chart, key ratios,
        analyst context where available, and how that name fits your portfolio weight.
        Use **Data & history behind this analysis** on any holding to see exact
        date ranges, reload times, and sources used for scores and charts.
        """
    )


def _render_data_sources() -> None:
    st.markdown("#### Where the history comes from")
    st.markdown(
        f"""
        Statistics are built from **public, competitive market sources**, combined in a
        local **analysed stocks** database for fast repeat lookups:

        - **{DATA_SOURCES['primary']}** — live prices and market fields when you reload
        - **{DATA_SOURCES['fundamentals']}** — payout, earnings, and balance-sheet style inputs
        - **{DATA_SOURCES['analyst']}** — consensus views where published
        - **{DATA_SOURCES['historical']}** — dividend and price history for trends and growth

        Your portfolio amounts (shares, deposits, purchases) stay **in your account only**.
        The **S&P historical library** (`/data/vectordb` on the server) is **shared by every user**;
        reload updates live prices for your positions when you choose.
        """
    )
    st.caption(
        "Educational tool only — not investment advice. Always verify data before acting."
    )
