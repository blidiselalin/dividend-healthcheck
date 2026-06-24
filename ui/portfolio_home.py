"""
Simplified portfolio home — welcome, quick actions, and try-it examples.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

import streamlit as st

from auth.demo_portfolio import load_demo_ui_snapshot, reset_demo_database
from auth.test_user import is_test_user, sign_out_test_user, test_user_session_active
from auth.user_context import clear_portfolio_session_state, current_user, resolve_portfolio_db_path
from services.portfolio_details_service import PortfolioDetailRow
from services.portfolio_session import is_demo_session
from ui.app_about import render_app_about
from ui.theme import (
    PORTFOLIO_LABEL_BY_KEY,
    portfolio_data_ready,
    render_notice,
    render_portfolio_section_nav,
)

PORTFOLIO_VIEW_HOLDING = "holding"
PORTFOLIO_VIEW_OVERVIEW = "overview"

# Public for tests and docs — demo / test user only.
HOME_EXAMPLES: Sequence[dict] = (
    {
        "title": "Analyze a holding",
        "example": "e.g. Coca-Cola (KO)",
        "detail": "Yield channel, safety, and fundamentals — compared only with other names in your portfolio.",
        "action": "Open KO",
        "kind": "holding",
        "symbol": "KO",
    },
    {
        "title": "Compare positions",
        "example": "Holdings table",
        "detail": "Filter positions, open holding detail, and compare same-sector names you already own.",
        "action": "View holdings",
        "kind": "section",
        "section": "holdings",
    },
    {
        "title": "Track dividend income",
        "example": "Calendar & cash",
        "detail": "Monthly dividend calendar and estimated cash received after tax.",
        "action": "Open income",
        "kind": "section",
        "section": "dividends",
    },
)


def navigate_to_portfolio_home() -> None:
    """Leave admin, holding drill-down, or research and return to portfolio home."""
    from ui.admin_page import set_admin_console_active

    set_admin_console_active(False)
    st.session_state["portfolio_view_mode"] = PORTFOLIO_VIEW_OVERVIEW
    st.session_state.pop("portfolio_research_mode", None)
    st.session_state["portfolio_section_label"] = "Home"
    st.rerun()


def set_holding_selection(symbol: str, nav_tickers: Optional[List[str]] = None) -> None:
    st.session_state["portfolio_selected_symbol"] = symbol.strip().upper()
    st.session_state["portfolio_view_mode"] = PORTFOLIO_VIEW_HOLDING
    st.session_state["portfolio_analysis_ready"] = True
    st.session_state.pop("portfolio_research_mode", None)
    if nav_tickers is not None:
        st.session_state["portfolio_nav_tickers"] = [t.upper() for t in nav_tickers]
    st.rerun()


def set_sp500_research_selection(
    symbol: str,
    *,
    nav_symbols: Optional[List[str]] = None,
) -> None:
    """Open full analysis for an S&P name (may not be in the user's portfolio)."""
    symbol = symbol.strip().upper()
    st.session_state["portfolio_selected_symbol"] = symbol
    st.session_state["portfolio_view_mode"] = PORTFOLIO_VIEW_HOLDING
    st.session_state["portfolio_research_mode"] = True
    st.session_state["portfolio_analysis_ready"] = True
    if nav_symbols:
        st.session_state["portfolio_nav_tickers"] = [s.upper() for s in nav_symbols]
    else:
        st.session_state["portfolio_nav_tickers"] = [symbol]
    st.rerun()


def apply_example_action(example: dict) -> None:
    """Navigate per example card (used by UI and tests)."""
    kind = example.get("kind")
    if kind == "holding":
        symbol = (example.get("symbol") or "KO").upper()
        st.session_state["portfolio_selected_symbol"] = symbol
        st.session_state["portfolio_view_mode"] = PORTFOLIO_VIEW_HOLDING
        st.session_state["portfolio_analysis_ready"] = True
        st.session_state["portfolio_section_label"] = "Holdings"
    elif kind == "section":
        section_key = example.get("section", "holdings")
        label = PORTFOLIO_LABEL_BY_KEY.get(section_key, "Holdings")
        st.session_state["portfolio_section_label"] = label
        st.session_state["portfolio_view_mode"] = PORTFOLIO_VIEW_OVERVIEW


def render_test_user_banner() -> None:
    """Shown on portfolio home when validating as test user."""
    user = current_user()
    if not test_user_session_active() or not is_test_user(user):
        return

    render_notice(
        "<strong>Test mode</strong> — demo portfolio KO, JNJ, O. "
        "Try the examples below. Your Google account is not affected.",
        kind="info",
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Reset demo", use_container_width=True):
            reset_demo_database(resolve_portfolio_db_path())
            clear_portfolio_session_state()
            from auth.demo_portfolio import ensure_demo_database

            ensure_demo_database(resolve_portfolio_db_path())
            load_demo_ui_snapshot()
            st.rerun()
    with c2:
        if st.button("Reload demo", use_container_width=True):
            clear_portfolio_session_state()
            load_demo_ui_snapshot()
            st.rerun()
    with c3:
        if st.button("Exit test user", use_container_width=True):
            sign_out_test_user()
            st.rerun()


def render_try_it_examples(*, expanded: bool = False) -> None:
    """Guided examples — test user only (demo tickers KO, JNJ, O)."""
    if not is_demo_session():
        return

    with st.expander("Try it — 3 quick examples", expanded=expanded):
        st.caption("Examples open portfolio views — analysis compares holdings you already own.")
        for index, item in enumerate(HOME_EXAMPLES):
            st.markdown(f"**{item['title']}** — _{item['example']}_")
            st.write(item["detail"])
            key_suffix = item.get("symbol") or item.get("section") or str(index)
            if st.button(
                item["action"],
                key=f"portfolio_example_{item['kind']}_{key_suffix}",
            ):
                apply_example_action(item)
                st.rerun()
            if index < len(HOME_EXAMPLES) - 1:
                st.divider()


def render_real_user_getting_started() -> None:
    """Walkthrough for signed-in users with an empty portfolio."""
    st.markdown("### Your portfolio is empty")
    st.write(
        "Add your first holding to unlock the dashboard, holdings table, dividend "
        "calendar, and per-stock analysis. Market history comes from the shared "
        "S&P library; only your positions are stored in your account."
    )

    st.markdown("#### Get started in four steps")
    st.markdown(
        """
        1. In the **sidebar**, open **Manage portfolio** (expanded below if this is your first visit).
        2. Open the **Add ticker** tab — enter a symbol (e.g. `VZ`, `KO`, `JNJ`), share count, and average cost per share.
        3. Click **Add to portfolio** (Yahoo Finance validates the ticker unless you skip validation).
        4. Click **Reload live data** in the sidebar to load prices, scores, and charts for your holdings.
        """
    )

    st.markdown("#### What you can add next")
    st.markdown(
        """
        - **Purchase** tab — log buy dates and prices for cost-basis history.
        - **Deposit** tab — record monthly cash you add to the account.
        - **Holdings** section — after reload, filter positions and open full analysis per ticker.
        """
    )

    render_notice(
        "<strong>Tip:</strong> You can analyze any S&P stock above before adding it to your portfolio. "
        "Demo holdings (KO, JNJ, O) appear only in <strong>test user</strong> mode.",
        kind="info",
    )


def render_empty_home_demo() -> None:
    """Welcome when the test user has no cached rows yet."""
    render_app_about(expanded=True)
    render_test_user_banner()

    st.markdown("#### Welcome (test mode)")
    st.write(
        "Demo holdings load automatically. If the table is empty, "
        "click **Load demo portfolio**, then open the examples."
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Load demo portfolio", type="primary", use_container_width=True):
            from auth.demo_portfolio import ensure_demo_database

            ensure_demo_database(resolve_portfolio_db_path())
            load_demo_ui_snapshot()
            st.rerun()
    with c2:
        if st.button("Show examples", use_container_width=True):
            st.session_state["portfolio_show_examples"] = True
            st.rerun()

    default_expand = st.session_state.get("portfolio_show_examples", False)
    render_try_it_examples(expanded=bool(default_expand))


def render_empty_home() -> None:
    """Welcome when no portfolio snapshot is in session."""
    if is_demo_session():
        render_empty_home_demo()
        return

    with st.expander("About DividendScope", expanded=False):
        render_app_about(expanded=True)
    render_real_user_getting_started()


def render_stocks_overview(rows: List[PortfolioDetailRow]) -> None:
    """Compact positions table — worst performers first, row click opens analysis."""
    from ui.portfolio_positions_table import render_positions_table

    render_positions_table(rows)


def render_compact_summary(rows: List[PortfolioDetailRow]) -> None:
    from services.portfolio_analysis_preload import PortfolioAnalysisPreload
    from services.portfolio_month_dividends import cached_current_month_paid_dividends
    from ui.portfolio_summary import render_holdings_summary

    preload = None
    if st.session_state.get("portfolio_analysis_ready"):
        preload = PortfolioAnalysisPreload.from_caches(
            st.session_state.get("portfolio_stock_cache", {}),
            st.session_state.get("portfolio_yield_cache", {}),
            st.session_state.get("portfolio_vector_docs", {}),
        )

    month_paid = cached_current_month_paid_dividends(rows=rows, preload=preload)
    render_holdings_summary(
        rows,
        month_paid=month_paid,
        show_month_received=month_paid is not None,
    )

    st.divider()
    render_stocks_overview(rows)


def render_portfolio_home_header(
    rows: Optional[List[PortfolioDetailRow]],
) -> bool:
    render_app_about(expanded=False)
    render_test_user_banner()

    from ui.sp500_research_picker import render_sp500_research_picker

    render_sp500_research_picker(key_prefix="main_home")

    if not portfolio_data_ready() or not rows:
        st.divider()
        render_empty_home()
        return False

    st.divider()
    render_compact_summary(rows)
    render_portfolio_section_nav()
    render_try_it_examples(expanded=is_demo_session())
    st.divider()
    return True
