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
from ui.beta_disclaimer import render_beta_pricing_placeholder, render_research_disclaimer
from ui.beta_feedback import render_beta_feedback
from ui.design_system import (
    PRODUCT_NAME,
    render_app_footer,
    render_beta_badge,
    render_chart_card_header,
    render_empty_state,
    render_feature_cards,
    render_logo,
    render_metric_grid,
    render_page_divider,
    render_payout_list,
    render_section_header,
    render_ticker_chips,
    sparkline_bars,
)
from ui.theme import inject_command_center_theme


def _render_hero_preview_card(dashboard: GuestDashboard) -> None:
    forecast_total = sum(amount for _, amount in dashboard.monthly_forecast)
    monthly_avg = dashboard.annual_income_usd / 12 if dashboard.annual_income_usd else 0
    total_value = sum(getattr(row, "current_value", 0) or 0 for row in dashboard.rows)
    portfolio_yield = (
        (dashboard.annual_income_usd / total_value * 100)
        if total_value > 0 and dashboard.annual_income_usd
        else None
    )
    next_payout = dashboard.next_payouts[0] if dashboard.next_payouts else None
    next_label = "Not available yet"
    if next_payout:
        when = next_payout.pay_date.strftime("%d %b") if next_payout.pay_date else "TBD"
        next_label = f"{next_payout.symbol} · ${next_payout.amount_usd:,.0f} · {when}"

    spark_values = [v for _, v in dashboard.monthly_forecast[:12]]
    spark_html = sparkline_bars(spark_values) if spark_values else ""

    alerts_html = ""
    for alert in dashboard.safety_alerts[:3]:
        icon = "🔴" if alert.severity == "high" else "🟠"
        alerts_html += f'<p class="cc-alert-row">{icon} <span><strong>{alert.symbol}</strong> — {alert.message}</span></p>'

    if not alerts_html:
        alerts_html = '<p class="cc-alert-row">✓ <span>No high-severity alerts on try list</span></p>'

    yield_label = f"{portfolio_yield:.2f}%" if portfolio_yield is not None else "—"

    st.markdown(
        f"""
        <div class="cc-preview-card" aria-label="Demo dashboard preview">
          <p class="cc-preview-label">Live preview · try portfolio</p>
          <div class="ds-metric-grid">
            <div class="ds-metric-card ds-highlight">
              <p class="ds-metric-label">Projected annual income</p>
              <p class="ds-metric-value">${dashboard.annual_income_usd:,.2f}</p>
            </div>
            <div class="ds-metric-card ds-highlight">
              <p class="ds-metric-label">Monthly average</p>
              <p class="ds-metric-value">${monthly_avg:,.2f}</p>
            </div>
            <div class="ds-metric-card ds-highlight">
              <p class="ds-metric-label">Portfolio yield</p>
              <p class="ds-metric-value">{yield_label}</p>
            </div>
            <div class="ds-metric-card ds-highlight">
              <p class="ds-metric-label">Next 12 months</p>
              <p class="ds-metric-value">${forecast_total:,.2f}</p>
            </div>
            <div class="ds-metric-card ds-highlight">
              <p class="ds-metric-label">Next payment</p>
              <p class="ds-metric-value" style="font-size:0.92rem">{next_label}</p>
            </div>
            <div class="ds-metric-card">
              <p class="ds-metric-label">Upcoming payouts</p>
              <p class="ds-metric-value">{len(dashboard.next_payouts)}</p>
            </div>
          </div>
          <p class="ds-metric-label" style="margin-top:0.75rem">Mini yield income trend (12 mo)</p>
          {spark_html}
          <p class="ds-metric-label" style="margin-top:0.65rem">Dividend health alerts</p>
          {alerts_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_hero(dashboard: GuestDashboard) -> None:
    left, right = st.columns([1.05, 0.95], gap="large")
    with left:
        render_logo(tagline="Beta · Dividend research dashboard")
        render_beta_badge()
        st.markdown(
            """
            <h1 class="cc-hero-title">
              Track <span class="ds-accent">dividend yield history</span> and future income in one place.
            </h1>
            <p class="cc-hero-sub">
                Analyze dividend yield trends, historical payouts, upcoming payments,
                and estimated portfolio income.
            </p>
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
    with right:
        _render_hero_preview_card(dashboard)


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
        render_ticker_chips([(h.symbol, f"{h.shares:.0f} sh") for h in guest])
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
    render_section_header(
        "Dividend dashboard",
        "Projected income, upcoming payouts, and health signals for your try list.",
    )
    if show_demo:
        st.success("Demo dashboard — projected income and upcoming payouts for your try list.")
    if not dashboard.library_ready:
        render_empty_state(
            "Library not loaded yet",
            "Run ingest on this server to see live forecasts. You can still sign up and add holdings.",
            icon="📚",
        )
        return

    forecast_total = sum(amount for _, amount in dashboard.monthly_forecast)
    render_metric_grid(
        [
            ("Next 12 months (est.)", f"${forecast_total:,.2f}", "Projected cash", True),
            ("Annual income", f"${dashboard.annual_income_usd:,.2f}", "Run-rate", True),
            (
                "Monthly average",
                f"${dashboard.annual_income_usd / 12:,.2f}" if dashboard.annual_income_usd else "—",
                "Estimated",
                True,
            ),
            ("Upcoming payouts", str(len(dashboard.next_payouts)), "This & next month", False),
        ]
    )

    if dashboard.monthly_forecast:
        render_chart_card_header(
            "Monthly dividend cash",
            "Next 12 months · estimated from shared library",
        )
        try:
            import plotly.graph_objects as go
            from utils.chart_theme import PALETTE, style_figure

            labels = [label for label, _ in dashboard.monthly_forecast]
            values = [value for _, value in dashboard.monthly_forecast]
            fig = go.Figure(
                data=[
                    go.Bar(
                        x=labels,
                        y=values,
                        marker_color=PALETTE["primary"],
                        hovertemplate="%{x}<br>$%{y:,.2f}<extra></extra>",
                    )
                ]
            )
            fig.update_layout(
                xaxis_title="Month",
                yaxis_title="USD",
                height=320,
                margin=dict(l=20, r=20, t=20, b=20),
            )
            style_figure(fig, legend=False)
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.bar_chart(
                {label: amount for label, amount in dashboard.monthly_forecast},
                height=320,
            )
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        render_empty_state(
            "No forecast data",
            "Add tickers to your try list to see projected monthly income.",
            icon="📅",
        )

    if dashboard.next_payouts:
        render_section_header("Upcoming dividend payments", "This month and next · estimated dates")
        render_payout_list(
            [
                (
                    payout.symbol,
                    f"${payout.amount_usd:,.2f}",
                    f"pay ~{(payout.pay_date.strftime('%d %b') if payout.pay_date else 'TBD')} · {payout.status}",
                )
                for payout in dashboard.next_payouts[:6]
            ]
        )

    if dashboard.safety_alerts:
        render_section_header("Dividend health alerts", "Simple research flags — not financial advice")
        for alert in dashboard.safety_alerts[:4]:
            icon = "🔴" if alert.severity == "high" else "🟠"
            import html as html_module

            msg = html_module.escape(alert.message)
            sym = html_module.escape(alert.symbol)
            st.markdown(
                f'<p class="cc-alert-row">{icon} <span><strong>{sym}</strong> — {msg}</span></p>',
                unsafe_allow_html=True,
            )

    if dashboard.rows:
        ranked = sorted(
            dashboard.rows,
            key=lambda row: getattr(row, "annual_income", 0) or 0,
            reverse=True,
        )
        render_section_header("Holdings by dividend income", "Ranked by estimated annual cash")
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


def _render_feature_cards() -> None:
    render_section_header(f"Why investors use {PRODUCT_NAME}", "Research-grade dividend context in one workspace.")
    render_feature_cards(
        [
            ("💵", "Track income", "Dividends received, upcoming ex-dates, and a 12-month cash forecast — not just today's price."),
            ("🛡️", "Analyze safety", "Payout ratio, dividend streak, yield zones, and watchlists flag reliability issues early."),
            ("📈", "Forecast growth", "Per-share dividend history and portfolio growth charts connect past raises to future income."),
        ]
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
    guest = guest_holdings_from_session(st.session_state)
    preview_dashboard = build_guest_dashboard(guest)
    _render_hero(preview_dashboard)
    render_page_divider()
    dashboard = _render_search_and_playground()
    st.divider()
    _render_demo_dashboard(dashboard)
    render_page_divider()
    _render_feature_cards()
    render_page_divider()
    with st.expander("Sample stock report — dividend yield history & payout history", expanded=True):
        _render_sample_report(dashboard)
    st.divider()
    _render_import_options()
    st.divider()
    _render_trust_section()
    render_beta_feedback(page="Command Center (pre-login)", key_suffix="command_center")
    _render_ctas(auth_block)
    render_app_footer()
