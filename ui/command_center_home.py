"""
Pre-login Dividend Command Center — try 2–3 stocks before creating an account.
"""

from __future__ import annotations

from typing import Callable

import streamlit as st

from config import DATA_SOURCES
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
from ui.beta_disclaimer import render_beta_badge, render_beta_pricing_placeholder, render_research_disclaimer
from ui.beta_feedback import render_beta_feedback
from ui.theme import inject_command_center_theme, render_notice


def _render_hero() -> None:
    render_beta_badge()
    st.markdown(
        """
        <div class="cc-hero">
            <p class="cc-hero-eyebrow">DividendScope · Beta</p>
            <h1 class="cc-hero-title">Track dividend yield history and future income in one place.</h1>
            <p class="cc-hero-sub">
                Analyze dividend yield trends, historical payouts, upcoming payments,
                and estimated portfolio income — past reliability, current safety, future cash.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "Explore dividend dashboard",
            type="primary",
            use_container_width=True,
            key="cc_cta_explore_dashboard",
        ):
            st.session_state["cc_scroll_demo"] = True
            st.rerun()
    with c2:
        if st.button(
            "Search a stock",
            use_container_width=True,
            key="cc_cta_search_stock",
        ):
            st.session_state["cc_focus_search"] = True
            st.rerun()


def _render_demo_quick_picks() -> None:
    st.caption("Try a popular dividend stock:")
    cols = st.columns(min(len(BETA_DEMO_SYMBOLS), 5))
    for index, symbol in enumerate(BETA_DEMO_SYMBOLS[:5]):
        with cols[index]:
            if st.button(symbol, key=f"cc_demo_pick_{symbol}", use_container_width=True):
                _, err = add_guest_holding(st.session_state, symbol=symbol, shares=10.0)
                if err:
                    st.warning(err)
                else:
                    st.session_state[GUEST_SPOTLIGHT_KEY] = symbol
                    st.session_state["cc_scroll_demo"] = True
                    st.rerun()
    more = BETA_DEMO_SYMBOLS[5:]
    if more:
        cols2 = st.columns(len(more))
        for col, symbol in zip(cols2, more):
            with col:
                if st.button(symbol, key=f"cc_demo_pick2_{symbol}", use_container_width=True):
                    _, err = add_guest_holding(st.session_state, symbol=symbol, shares=10.0)
                    if err:
                        st.warning(err)
                    else:
                        st.session_state[GUEST_SPOTLIGHT_KEY] = symbol
                        st.session_state["cc_scroll_demo"] = True
                        st.rerun()


def _render_search_and_playground() -> GuestDashboard:
    if st.session_state.pop("cc_focus_search", False):
        st.info("Enter a ticker below to analyze dividend yield and income.")

    st.markdown("#### Search a stock")
    _render_demo_quick_picks()
    col_search, col_shares = st.columns([3, 1])
    with col_search:
        symbol = st.text_input(
            "Search ticker",
            key="cc_symbol_search",
            placeholder="e.g. KO, JNJ, VZ, O",
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

    c1, c2, _ = st.columns([1, 1, 2])
    with c1:
        add_clicked = st.button("Add to try list", type="primary", key="cc_add_symbol")
    with c2:
        reset_clicked = st.button("Reset sample portfolio", key="cc_reset_sample")

    if reset_clicked:
        from services.guest_playground import default_guest_holdings

        save_guest_holdings(st.session_state, default_guest_holdings())
        st.session_state[GUEST_SPOTLIGHT_KEY] = "KO"
        st.rerun()

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
    st.caption(
        f"**Try list** ({len(guest)}/{GUEST_MAX_HOLDINGS}) — session only until you create an account. "
        "Sample starts with KO, JNJ, O."
    )

    if guest:
        chip_cols = st.columns(min(len(guest), GUEST_MAX_HOLDINGS))
        for col, holding in zip(chip_cols, guest):
            with col:
                st.markdown(f"**{holding.symbol}** · {holding.shares:.0f} sh")
                if st.button(f"Remove {holding.symbol}", key=f"cc_remove_{holding.symbol}"):
                    remove_guest_holding(st.session_state, holding.symbol)
                    st.rerun()

    return build_guest_dashboard(guest)


def _render_demo_dashboard(dashboard: GuestDashboard) -> None:
    show_demo = st.session_state.pop("cc_scroll_demo", False)
    st.markdown("#### Your dividend outlook (try portfolio)")
    if show_demo:
        st.success("Demo dashboard — projected income and upcoming payouts for your try list.")
    if not dashboard.library_ready:
        render_notice(
            "Shared market library is empty on this server — run ingest to see live forecasts. "
            "You can still sign up and add holdings.",
            kind="warning",
        )
        return

    m1, m2, m3, m4 = st.columns(4)
    forecast_total = sum(amount for _, amount in dashboard.monthly_forecast)
    m1.metric(
        "Next 12 months (est.)",
        f"${forecast_total:,.2f}",
        help="Sum of projected dividend cash across the next 12 months for your try list.",
    )
    m2.metric(
        "Annual income run-rate",
        f"${dashboard.annual_income_usd:,.2f}",
        help="Trailing annual dividend per share × shares held (from shared library).",
    )
    m3.metric(
        "Monthly average (est.)",
        f"${dashboard.annual_income_usd / 12:,.2f}" if dashboard.annual_income_usd else "—",
        help="Annual run-rate divided by 12.",
    )
    m4.metric(
        "Upcoming payouts",
        str(len(dashboard.next_payouts)),
        help="Scheduled or received payments this month and next.",
    )

    if dashboard.monthly_forecast:
        try:
            import plotly.graph_objects as go

            labels = [label for label, _ in dashboard.monthly_forecast]
            values = [value for _, value in dashboard.monthly_forecast]
            fig = go.Figure(
                data=[
                    go.Bar(
                        x=labels,
                        y=values,
                        marker_color="rgba(28, 131, 225, 0.75)",
                    )
                ]
            )
            fig.update_layout(
                title="Monthly dividend cash (next 12 months)",
                xaxis_title="Month",
                yaxis_title="USD",
                height=320,
                margin=dict(l=20, r=20, t=40, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.bar_chart(
                {label: amount for label, amount in dashboard.monthly_forecast},
                height=320,
            )

    if dashboard.next_payouts:
        st.markdown("**Upcoming dividend payments**")
        for payout in dashboard.next_payouts[:5]:
            when = payout.pay_date.strftime("%d %b") if payout.pay_date else "TBD"
            st.caption(
                f"**{payout.symbol}** · ${payout.amount_usd:,.2f} · pay ~{when} · {payout.status}"
            )

    if dashboard.safety_alerts:
        st.markdown("**Dividend health alerts**")
        for alert in dashboard.safety_alerts[:4]:
            icon = "🔴" if alert.severity == "high" else "🟠"
            st.caption(f"{icon} **{alert.symbol}** — {alert.message}")

    if dashboard.rows:
        ranked = sorted(
            dashboard.rows,
            key=lambda row: getattr(row, "annual_income", 0) or 0,
            reverse=True,
        )
        st.markdown("**Holdings by dividend income**")
        for row in ranked[:GUEST_MAX_HOLDINGS]:
            income = getattr(row, "annual_income", None)
            yld = getattr(row, "dividend_yield_pct", None)
            st.caption(
                f"**{row.ticker}** · ${income:,.2f}/yr"
                + (f" · yield {yld:.2f}%" if yld is not None else "")
                if income
                else f"**{row.ticker}** · income not available yet"
            )


def _render_feature_cards() -> None:
    st.markdown("#### Why investors use DividendScope")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("##### Track income")
        st.write(
            "See dividends received, upcoming ex-dates, and a 12-month cash forecast — "
            "not just today's price."
        )
    with c2:
        st.markdown("##### Analyze safety")
        st.write(
            "Payout ratio, dividend streak, yield zones, and risk watchlists flag "
            "reliability issues early."
        )
    with c3:
        st.markdown("##### Forecast growth")
        st.write(
            "Per-share dividend history and portfolio growth charts connect past raises "
            "to future income."
        )


def _render_sample_report(dashboard: GuestDashboard) -> None:
    guest = dashboard.holdings
    if not guest:
        return
    symbols = [h.symbol for h in guest]
    default = st.session_state.get(GUEST_SPOTLIGHT_KEY) or symbols[0]
    if default not in symbols:
        default = symbols[0]
    spotlight = st.selectbox(
        "Sample stock report",
        options=symbols,
        index=symbols.index(default),
        key="cc_spotlight_pick",
    )
    st.session_state[GUEST_SPOTLIGHT_KEY] = spotlight

    with st.spinner(f"Loading {spotlight} from shared library…"):
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

    data = analysis.stock_data
    from services.dividend_health import assess_dividend_health
    from ui.components import UIComponents

    health = assess_dividend_health(data)
    UIComponents.display_dividend_section(
        data,
        symbol=spotlight,
        vector_doc=analysis.document,
    )
    st.divider()
    UIComponents.display_yield_channel_chart(
        spotlight,
        years=10,
        channel_data=analysis.yield_channel,
        vector_doc=analysis.document,
        show_header=True,
    )
    st.caption(f"Dividend health summary: **{health.label}**")


def _render_import_options() -> None:
    st.markdown("#### Bring your portfolio")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("##### Manual entry")
        st.write("Add tickers one by one above, or after sign-up under **Manage portfolio**.")
    with c2:
        st.markdown("##### CSV import")
        st.write("Coming soon — upload a broker export to seed holdings and journal.")
    with c3:
        st.markdown("##### Broker sync")
        st.write("Planned — read-only connections for major brokers.")


def _render_trust_section() -> None:
    st.markdown("#### Data & privacy")
    st.markdown(
        f"""
        - **Sources:** {DATA_SOURCES['primary']} (prices), {DATA_SOURCES['fundamentals']} (fundamentals),
          {DATA_SOURCES['historical']} (dividend history)
        - **Your portfolio** is stored per account in PostgreSQL — try-list data stays in this browser session until you sign up
        - **Shared library** powers research for all users; your share counts and cost basis are never shared
        """
    )
    render_research_disclaimer(compact=True)


def _render_ctas(auth_block: Callable[[], None]) -> None:
    st.markdown("---")
    st.markdown("#### Ready to save your portfolio?")
    st.write(
        "Create a free account to keep holdings, run live reloads in the background, "
        "and unlock the full workspace (journal, deposits, benchmarks, watchlists)."
    )
    render_beta_pricing_placeholder()
    if st.button(
        "Start with one stock",
        type="secondary",
        use_container_width=False,
        key="cc_cta_one_stock",
    ):
        st.session_state["cc_focus_search"] = True
        st.rerun()
    auth_block()


def render_command_center_page(*, auth_block: Callable[[], None]) -> None:
    """Full-width pre-login homepage."""
    inject_command_center_theme()
    _render_hero()
    dashboard = _render_search_and_playground()
    st.divider()
    _render_demo_dashboard(dashboard)
    st.divider()
    _render_feature_cards()
    st.divider()
    with st.expander("Sample stock report — dividend yield history & payout history", expanded=True):
        _render_sample_report(dashboard)
    st.divider()
    _render_import_options()
    st.divider()
    _render_trust_section()
    render_beta_feedback(page="Command Center (pre-login)", key_suffix="command_center")
    _render_ctas(auth_block)
