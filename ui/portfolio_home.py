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
from ui.app_about import render_app_about
from ui.theme import (
    PORTFOLIO_LABEL_BY_KEY,
    portfolio_data_ready,
    render_notice,
)

PORTFOLIO_VIEW_HOLDING = "holding"
PORTFOLIO_VIEW_OVERVIEW = "overview"

# Public for tests and docs.
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


def set_holding_selection(symbol: str, nav_tickers: Optional[List[str]] = None) -> None:
    st.session_state["portfolio_selected_symbol"] = symbol
    st.session_state["portfolio_view_mode"] = PORTFOLIO_VIEW_HOLDING
    st.session_state["portfolio_analysis_ready"] = True
    if nav_tickers is not None:
        st.session_state["portfolio_nav_tickers"] = nav_tickers
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
    """Three guided examples for new or exploring users."""
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


def render_empty_home() -> None:
    """Welcome when no portfolio snapshot is in session."""
    render_app_about(expanded=True)
    render_test_user_banner()

    st.markdown("#### Welcome")
    if test_user_session_active():
        st.write(
            "Demo holdings load automatically. If the table is empty, "
            "click **Load demo portfolio**, then open the examples."
        )
    else:
        st.write("Track dividend portfolios, review buy ideas, and analyze holdings side by side.")

    c1, c2 = st.columns(2)
    with c1:
        label = "Load demo portfolio" if test_user_session_active() else "Load my portfolio"
        if st.button(label, type="primary", use_container_width=True):
            if test_user_session_active():
                from auth.demo_portfolio import ensure_demo_database

                ensure_demo_database(resolve_portfolio_db_path())
                load_demo_ui_snapshot()
            else:
                from ui.portfolio_sidebar import _reload_live_data

                with st.spinner("Loading portfolio…"):
                    _reload_live_data()
            st.rerun()
    with c2:
        if st.button("Show examples", use_container_width=True):
            st.session_state["portfolio_show_examples"] = True
            st.session_state["portfolio_show_about"] = True
            st.rerun()

    default_expand = test_user_session_active() or st.session_state.get(
        "portfolio_show_examples", False
    )
    render_try_it_examples(expanded=bool(default_expand))

    if not test_user_session_active():
        st.markdown("---")
        st.caption(
            "Sign up with Google · add holdings under **Manage portfolio** · "
            "**Reload live data** for market prices."
        )


def render_compact_summary(rows: List[PortfolioDetailRow]) -> None:
    total_value = sum(row.current_value or 0.0 for row in rows)
    total_acquisition = sum(row.acquisition_value for row in rows)
    total_profit = total_value - total_acquisition
    profit_pct = (total_profit / total_acquisition * 100) if total_acquisition else None
    total_income = sum(row.annual_income or 0.0 for row in rows)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Holdings", len(rows))
    c2.metric("Value", f"${total_value:,.0f}")
    c3.metric(
        "P/L",
        f"${total_profit:+,.0f}",
        f"{profit_pct:+.1f}%" if profit_pct is not None else None,
    )
    c4.metric(
        "Yield",
        f"{(total_income / total_value * 100):.2f}%" if total_value else "—",
        help=f"Annual income ${total_income:,.0f}",
    )

    ranked = sorted(rows, key=lambda r: r.current_value or 0.0, reverse=True)[:8]
    if not ranked:
        return

    st.caption("Tap a ticker to open its analysis")
    cols = st.columns(4)
    for index, row in enumerate(ranked):
        with cols[index % 4]:
            if st.button(
                row.ticker,
                key=f"home_quick_{row.ticker}",
                use_container_width=True,
                help=f"${(row.current_value or 0):,.0f}",
            ):
                set_holding_selection(
                    row.ticker,
                    nav_tickers=[item.ticker for item in ranked],
                )


def render_portfolio_home_header(
    rows: Optional[List[PortfolioDetailRow]],
) -> bool:
    render_app_about(expanded=False)
    render_test_user_banner()

    if not portfolio_data_ready() or not rows:
        render_empty_home()
        return False

    render_compact_summary(rows)
    render_try_it_examples(expanded=test_user_session_active())
    st.divider()
    return True
