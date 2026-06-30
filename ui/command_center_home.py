"""
Pre-login Dividend Command Center — try 2–3 stocks before creating an account.
"""

from __future__ import annotations

import html as html_module
from typing import Callable

import streamlit as st

from services.guest_playground import (
    BETA_DEMO_SYMBOLS,
    GUEST_MAX_HOLDINGS,
    GUEST_SPOTLIGHT_KEY,
    GuestDashboard,
    add_guest_holding,
    build_guest_dashboard,
    guest_holdings_from_session,
    remove_guest_holding,
    save_guest_holdings,
)
from ui.beta_disclaimer import render_research_disclaimer
from ui.beta_feedback import render_beta_feedback
from ui.design_system import (
    PRODUCT_NAME,
    render_beta_badge,
    render_empty_state,
    render_feature_cards,
    render_html,
    render_logo,
    render_page_divider,
    render_payout_list,
    render_section_header,
    render_ticker_chips,
)
from ui.theme import inject_command_center_theme


def _render_hero_preview_card(dashboard: GuestDashboard) -> None:
    """Compact hero snapshot — details expand in the dashboard section below."""
    monthly_avg = dashboard.annual_income_usd / 12 if dashboard.annual_income_usd else 0
    total_value = sum(getattr(row, "current_value", 0) or 0 for row in dashboard.rows)
    portfolio_yield = (
        (dashboard.annual_income_usd / total_value * 100)
        if total_value > 0 and dashboard.annual_income_usd
        else None
    )
    yield_label = html_module.escape(
        f"{portfolio_yield:.2f}%" if portfolio_yield is not None else "—"
    )

    render_html(
        f'<div class="cc-preview-card" aria-label="Try portfolio preview">'
        f'<p class="cc-preview-label">Sample try list · session preview</p>'
        f'<div class="ds-metric-grid">'
        f'<div class="ds-metric-card ds-highlight"><p class="ds-metric-label">Est. annual income</p>'
        f'<p class="ds-metric-value">${dashboard.annual_income_usd:,.2f}</p></div>'
        f'<div class="ds-metric-card ds-highlight"><p class="ds-metric-label">Monthly average</p>'
        f'<p class="ds-metric-value">${monthly_avg:,.2f}</p></div>'
        f'<div class="ds-metric-card ds-highlight"><p class="ds-metric-label">Portfolio yield</p>'
        f'<p class="ds-metric-value">{yield_label}</p></div>'
        f"</div>"
        f"</div>"
    )


def _render_hero() -> None:
    left, right = st.columns([1.05, 0.95], gap="large")
    guest = guest_holdings_from_session(st.session_state)
    preview_dashboard = build_guest_dashboard(guest)
    with left:
        render_logo(tagline="Free during beta · dividend research")
        render_beta_badge()
        render_html(
            '<h1 class="cc-hero-title">'
            'Track <span class="ds-accent">dividend yield history</span> and future income in one place.'
            "</h1>"
            '<p class="cc-hero-sub">'
            "Try up to three dividend stocks with no account — then sign up free to save your portfolio."
            "</p>"
        )
    with right:
        _render_hero_preview_card(preview_dashboard)


def _render_demo_quick_picks() -> None:
    st.caption("Quick add:")
    symbols = BETA_DEMO_SYMBOLS[: min(len(BETA_DEMO_SYMBOLS), GUEST_MAX_HOLDINGS + 2)]
    cols = st.columns(len(symbols))
    for col, symbol in zip(cols, symbols):
        with col:
            if st.button(symbol, key=f"cc_demo_pick_{symbol}", use_container_width=True):
                _, err = add_guest_holding(st.session_state, symbol=symbol, shares=10.0)
                if err:
                    st.warning(err)
                else:
                    st.session_state[GUEST_SPOTLIGHT_KEY] = symbol
                    st.rerun()


def _render_search_and_playground() -> GuestDashboard:
    render_section_header(
        "Try dividend stocks",
        f"Add up to {GUEST_MAX_HOLDINGS} tickers — session only until you sign up. Starts with KO, JNJ, O.",
    )

    _render_demo_quick_picks()
    col_search, col_shares, col_add = st.columns([3, 1, 1])
    with col_search:
        symbol = st.text_input(
            "Search ticker",
            key="cc_symbol_search",
            placeholder="e.g. KO, JNJ, VZ",
            label_visibility="collapsed",
        )
    with col_shares:
        shares = st.number_input(
            "Shares",
            min_value=1.0,
            value=10.0,
            step=1.0,
            key="cc_symbol_shares",
            label_visibility="collapsed",
        )
    with col_add:
        add_clicked = st.button("Add", type="primary", use_container_width=True, key="cc_add_symbol")

    if add_clicked and symbol.strip():
        _, err = add_guest_holding(
            st.session_state,
            symbol=symbol.strip(),
            shares=shares,
        )
        if err:
            st.warning(err)
        else:
            st.toast(f"Added {symbol.strip().upper()} to your try list.")
            st.rerun()

    guest = guest_holdings_from_session(st.session_state)
    if guest:
        render_ticker_chips([(h.symbol, f"{h.shares:.0f} sh") for h in guest])
        remove_cols = st.columns(min(len(guest), GUEST_MAX_HOLDINGS))
        for col, holding in zip(remove_cols, guest):
            with col:
                if st.button(
                    f"Remove {holding.symbol}",
                    key=f"cc_remove_{holding.symbol}",
                    use_container_width=True,
                ):
                    remove_guest_holding(st.session_state, holding.symbol)
                    st.rerun()
        if st.button("Reset to sample list", key="cc_reset_sample"):
            from services.guest_playground import default_guest_holdings

            save_guest_holdings(st.session_state, default_guest_holdings())
            st.session_state[GUEST_SPOTLIGHT_KEY] = "KO"
            st.rerun()

    return build_guest_dashboard(guest)


def _render_monthly_income_chart(dashboard: GuestDashboard) -> None:
    if not dashboard.monthly_forecast:
        render_empty_state(
            "No forecast yet",
            "Add a ticker to see projected monthly dividend income.",
            icon="📅",
        )
        return

    render_section_header(
        "Monthly dividend cash",
        "Next 12 months · estimated from the shared library",
    )
    try:
        import plotly.graph_objects as go
        from utils.chart_theme import chart_palette, style_yield_channel_figure

        palette = chart_palette()

        labels = [label for label, _ in dashboard.monthly_forecast]
        values = [value for _, value in dashboard.monthly_forecast]
        fig = go.Figure(
            data=[
                go.Bar(
                    x=labels,
                    y=values,
                    marker_color=palette["primary"],
                    hovertemplate="%{x}<br>$%{y:,.2f}<extra></extra>",
                )
            ]
        )
        fig.update_layout(xaxis_title="Month", yaxis_title="USD")
        style_yield_channel_figure(fig, height=300)
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        st.bar_chart(
            {label: amount for label, amount in dashboard.monthly_forecast},
            height=300,
        )


def _render_demo_dashboard(dashboard: GuestDashboard) -> None:
    render_section_header(
        "Income preview",
        "Upcoming payouts and ranked income for your try list.",
    )
    if not dashboard.library_ready:
        render_empty_state(
            "Library not loaded yet",
            "Research data will appear here once the shared library is available on this server.",
            icon="📚",
        )
        return

    if dashboard.next_payouts:
        render_payout_list(
            [
                (
                    payout.symbol,
                    f"${payout.amount_usd:,.2f}",
                    f"pay ~{(payout.pay_date.strftime('%d %b') if payout.pay_date else 'TBD')} · {payout.status}",
                )
                for payout in dashboard.next_payouts[:5]
            ]
        )
    else:
        st.caption("No upcoming payouts on the try list yet.")

    if dashboard.rows:
        ranked = sorted(
            dashboard.rows,
            key=lambda row: getattr(row, "annual_income", 0) or 0,
            reverse=True,
        )
        render_section_header("Income by holding", "Estimated annual cash from your try list")
        render_payout_list(
            [
                (
                    row.ticker,
                    f"${getattr(row, 'annual_income', 0) or 0:,.2f}/yr",
                    f"yield {getattr(row, 'dividend_yield_pct', 0):.2f}%"
                    if getattr(row, "dividend_yield_pct", None) is not None
                    else "income n/a",
                )
                for row in ranked[:GUEST_MAX_HOLDINGS]
            ]
        )

    _render_monthly_income_chart(dashboard)


def _render_feature_cards() -> None:
    render_section_header(f"What you get with {PRODUCT_NAME}", "Free during beta — full dividend workspace after sign-up.")
    render_feature_cards(
        [
            ("💵", "Track income", "Calendar, cash received, and a 12-month dividend forecast."),
            ("🛡️", "Yield channels", "See if today's yield is high or low vs a stock's own history."),
            ("📈", "Portfolio view", "Holdings, growth, journal, and benchmarks after you create an account."),
        ]
    )


def _render_yield_preview(dashboard: GuestDashboard) -> None:
    guest = dashboard.holdings
    if not guest:
        return
    symbols = [h.symbol for h in guest]
    default = st.session_state.get(GUEST_SPOTLIGHT_KEY) or symbols[0]
    if default not in symbols:
        default = symbols[0]

    with st.expander("Preview: dividend yield channels (one stock)", expanded=False):
        spotlight = st.selectbox(
            "Ticker",
            options=symbols,
            index=symbols.index(default),
            key="cc_spotlight_pick",
            label_visibility="collapsed",
        )
        st.session_state[GUEST_SPOTLIGHT_KEY] = spotlight

        with st.spinner(f"Loading {spotlight}…"):
            from services.stock_analysis_service import load_independent_stock_analysis

            analysis = load_independent_stock_analysis(
                spotlight,
                include_yield_channel=True,
                apply_live_price=False,
                fetch_realtime_prices=False,
            )

        if not analysis:
            st.info("No library data for this symbol yet.")
            return

        from ui.components import UIComponents

        UIComponents.display_yield_channel_chart(
            spotlight,
            years=10,
            channel_data=analysis.yield_channel,
            vector_doc=analysis.document,
            show_header=True,
        )
        render_research_disclaimer(compact=True)


def _render_signup_block(auth_block: Callable[[], None]) -> None:
    render_section_header(
        "Create your free portfolio",
        "Sign up with Google to save holdings — no credit card during beta.",
    )
    render_research_disclaimer(compact=True)
    auth_block()


def render_command_center_page(*, auth_block: Callable[[], None]) -> None:
    """Focused pre-login homepage for the free beta try experience."""
    inject_command_center_theme()
    _spacer, _theme = st.columns([6, 1.35])
    with _theme:
        from ui.theme_mode import render_theme_toggle

        render_theme_toggle()
    _render_hero()
    render_page_divider()
    dashboard = _render_search_and_playground()
    render_page_divider()
    _render_demo_dashboard(dashboard)
    render_page_divider()
    _render_feature_cards()
    _render_yield_preview(dashboard)
    render_beta_feedback(page="Command Center (pre-login)", key_suffix="command_center")
    _render_signup_block(auth_block)
    st.caption(f"{PRODUCT_NAME} · dividend research only · not financial advice.")
