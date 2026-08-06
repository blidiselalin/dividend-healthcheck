"""
Interactive public demo pages for the pre-login Command Center.

Guided walkthrough: Overview → Income → Risk → Research → Import
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from services.dividend_terminology import term_help, term_label
from services.guest_playground import (
    BETA_DEMO_SYMBOLS,
    GUEST_MAX_HOLDINGS,
    GUEST_SPOTLIGHT_KEY,
    GuestDashboard,
    add_guest_holding,
    default_guest_holdings,
    remove_guest_holding,
    save_guest_holdings,
)
from services.guidance_analytics import track_guidance_event
from ui.beta_disclaimer import render_research_disclaimer
from ui.command_center_home import (
    DemoPage,
    PublicRoute,
    PublicView,
    apply_public_route,
    request_auth_panel,
)
from ui.design_system import (
    render_action_card,
    render_data_provenance,
    render_demo_progress,
    render_empty_state,
    render_info_panel,
    render_metric_strip,
    render_page_header,
    render_payout_list,
    render_section_header,
    render_ticker_chips,
)

# Session-only guided demo tour (not authenticated NBA).
_CC_TOUR_ADJUSTED = "cc_tour_adjusted"
_CC_TOUR_INCOME = "cc_tour_income_opened"
_CC_TOUR_RISK = "cc_tour_risk_opened"
_CC_TOUR_RESEARCH = "cc_tour_research_opened"
_CC_TOUR_IMPORT = "cc_tour_import_opened"
_ANALYTICS_LAST_KEY = "command_center_last_analytics"

_DEMO_STEPS = (
    DemoPage.OVERVIEW,
    DemoPage.INCOME,
    DemoPage.RISK,
    DemoPage.RESEARCH,
    DemoPage.IMPORT,
)
_DEMO_STEP_LABELS = ("Overview", "Income", "Risk", "Research", "Import")


@dataclass(frozen=True)
class DemoStep:
    title: str
    description: str
    action_label: str
    target_page: DemoPage | None  # None → create portfolio


def _track_once(event_name: str, *, dedupe_key: str, properties: dict | None = None) -> None:
    last = st.session_state.setdefault(_ANALYTICS_LAST_KEY, {})
    if not isinstance(last, dict):
        last = {}
        st.session_state[_ANALYTICS_LAST_KEY] = last
    if last.get(event_name) == dedupe_key:
        return
    last[event_name] = dedupe_key
    track_guidance_event(event_name, session=st.session_state, properties=properties)


def _mark_tour(key: str, *, step_id: str) -> None:
    if st.session_state.get(key):
        return
    st.session_state[key] = True
    track_guidance_event(
        "public_demo_step_completed",
        session=st.session_state,
        properties={"demo_page": step_id},
    )


def _tour_flags() -> tuple[bool, bool, bool, bool, bool]:
    return (
        bool(st.session_state.get(_CC_TOUR_ADJUSTED)),
        bool(st.session_state.get(_CC_TOUR_INCOME)),
        bool(st.session_state.get(_CC_TOUR_RISK)),
        bool(st.session_state.get(_CC_TOUR_RESEARCH)),
        bool(st.session_state.get(_CC_TOUR_IMPORT)),
    )


def _tour_completed_count() -> int:
    return sum(1 for done in _tour_flags() if done)


def resolve_next_demo_step() -> DemoStep:
    """Educational navigation for the public demo (not portfolio advice)."""
    adjusted, income, risk, research, import_seen = _tour_flags()
    if not adjusted:
        return DemoStep(
            title="Adjust sample shares",
            description="Change KO, JNJ, or O quantities to see estimated income update.",
            action_label="Stay on Overview",
            target_page=DemoPage.OVERVIEW,
        )
    if not income:
        return DemoStep(
            title="Compare estimated vs received concepts",
            description=(
                "Open Income to see estimated cash from holdings beside an "
                "illustrative receipt example — not real broker cash."
            ),
            action_label="Open Income",
            target_page=DemoPage.INCOME,
        )
    if not risk:
        return DemoStep(
            title="Inspect a portfolio attention signal",
            description="Review sample risk labels. These are educational review aids, not advice.",
            action_label="Open Risk",
            target_page=DemoPage.RISK,
        )
    if not research:
        return DemoStep(
            title="Review research evidence",
            description="Open Research to inspect yield history and library evidence for one holding.",
            action_label="Open Research",
            target_page=DemoPage.RESEARCH,
        )
    if not import_seen:
        return DemoStep(
            title="See how import works",
            description="Import is simulated here. Real broker files stay behind account creation.",
            action_label="Open Import",
            target_page=DemoPage.IMPORT,
        )
    return DemoStep(
        title="Create your portfolio",
        description="Save your try list privately and import a real IBKR statement when ready.",
        action_label="Create portfolio",
        target_page=None,
    )


def _severity_label(raw: str) -> str:
    text = (raw or "").strip().lower()
    if text in {"high", "risky"}:
        return "Needs attention"
    if text in {"medium", "watch"}:
        return "Review"
    if text in {"low"}:
        return "Monitor"
    return "Not enough data"


def _page_index(page: DemoPage) -> int:
    try:
        return _DEMO_STEPS.index(page)
    except ValueError:
        return 0


def _render_demo_chrome(active: DemoPage) -> None:
    """Progress + page nav + next-step card — same shell on every demo page."""
    render_demo_progress(
        list(_DEMO_STEP_LABELS),
        active_index=_page_index(active),
        completed_through=_tour_completed_count() - 1,
    )

    cols = st.columns(len(_DEMO_STEPS))
    for col, page, label in zip(cols, _DEMO_STEPS, _DEMO_STEP_LABELS):
        with col:
            selected = page == active
            text = f"{label} · active" if selected else label
            if st.button(
                text,
                key=f"cc_demo_nav_{page.value}",
                use_container_width=True,
                type="primary" if selected else "secondary",
            ):
                apply_public_route(PublicRoute(PublicView.DEMO, page))
                st.rerun()

    step = resolve_next_demo_step()
    done = _tour_completed_count()
    kicker = (
        "Guided demo complete"
        if done >= len(_DEMO_STEPS)
        else f"Next demo step · {done} of {len(_DEMO_STEPS)} complete"
    )
    render_action_card(step.title, step.description, kicker=kicker)
    if step.target_page is None:
        if st.button(
            step.action_label,
            key="cc_demo_step_auth",
            type="primary",
            use_container_width=True,
        ):
            request_auth_panel(source_section="demo_step")
            st.rerun()
    elif step.target_page != active:
        if st.button(
            step.action_label,
            key=f"cc_demo_step_{step.target_page.value}",
            type="primary",
            use_container_width=True,
        ):
            apply_public_route(PublicRoute(PublicView.DEMO, step.target_page))
            st.rerun()
    else:
        st.caption("Complete the action on this page, then continue with the next step.")


def _apply_share_updates(holdings: list) -> bool:
    changed = False
    for holding in holdings:
        key = f"cc_demo_shares_{holding.symbol}"
        new_shares = float(st.session_state.get(key, holding.shares))
        if abs(new_shares - holding.shares) > 1e-9:
            add_guest_holding(
                st.session_state,
                symbol=holding.symbol,
                shares=new_shares,
            )
            track_guidance_event(
                "guest_holding_quantity_changed",
                session=st.session_state,
                properties={"holding_count": len(holdings)},
            )
            _mark_tour(_CC_TOUR_ADJUSTED, step_id="adjust")
            changed = True
    return changed


def _render_overview(dashboard: GuestDashboard) -> None:
    render_page_header(
        "Start with the one thing that matters next.",
        "Sample portfolio only — adjust holdings and watch estimated income update.",
        kicker="Demo · Overview",
    )

    monthly = dashboard.annual_income_usd / 12 if dashboard.annual_income_usd else 0.0
    yield_label = (
        f"{dashboard.portfolio_yield_pct:.2f}%"
        if dashboard.portfolio_yield_pct is not None
        else "—"
    )
    render_metric_strip(
        [
            (
                "Estimated annual income",
                f"${dashboard.annual_income_usd:,.2f}",
                "Estimated",
                True,
            ),
            ("Monthly average", f"${monthly:,.2f}", "Estimated"),
            ("Portfolio yield", yield_label, "Estimated"),
            (
                "Sample value",
                f"${dashboard.portfolio_value_usd:,.2f}",
                f"{len(dashboard.holdings)} holdings",
            ),
        ]
    )
    render_data_provenance(
        "Guest sample · estimated from the shared market library · not a broker account."
    )

    render_section_header(
        "1 · Adjust sample holdings",
        f"Up to {GUEST_MAX_HOLDINGS} names. Changing shares updates estimated income.",
    )
    holdings = list(dashboard.holdings)
    if not holdings:
        render_empty_state(
            "No sample holdings",
            "Reset to KO, JNJ, and O to continue the walkthrough.",
            icon="📂",
        )
    else:
        cols = st.columns(len(holdings))
        for col, holding in zip(cols, holdings):
            key = f"cc_demo_shares_{holding.symbol}"
            if key not in st.session_state:
                st.session_state[key] = float(holding.shares)
            with col:
                st.number_input(
                    f"{holding.symbol} shares",
                    min_value=0.0,
                    max_value=10000.0,
                    step=1.0,
                    key=key,
                    help=f"Adjust sample shares for {holding.symbol}",
                )
        if _apply_share_updates(holdings):
            st.rerun()
        render_ticker_chips(
            [
                (
                    h.symbol,
                    f"{h.shares:.0f} sh · {h.company_name or h.symbol}",
                )
                for h in holdings
            ]
        )

    with st.expander("Add, remove, or reset sample holdings", expanded=False):
        st.caption("Optional — the walkthrough works with the default KO, JNJ, O list.")
        qcols = st.columns(3)
        for idx, symbol in enumerate(BETA_DEMO_SYMBOLS[:6]):
            with qcols[idx % 3]:
                if st.button(symbol, key=f"cc_demo_quick_{symbol}", use_container_width=True):
                    _, err = add_guest_holding(st.session_state, symbol=symbol, shares=10.0)
                    if err:
                        st.warning(err)
                    else:
                        _mark_tour(_CC_TOUR_ADJUSTED, step_id="adjust")
                        st.rerun()

        add_c1, add_c2, add_c3 = st.columns([2.2, 1, 1])
        with add_c1:
            symbol = st.text_input("Ticker", key="cc_demo_add_symbol", placeholder="e.g. VZ")
        with add_c2:
            shares = st.number_input(
                "Shares", min_value=1.0, value=10.0, step=1.0, key="cc_demo_add_shares"
            )
        with add_c3:
            if st.button("Add", type="primary", use_container_width=True, key="cc_demo_add_btn"):
                _, err = add_guest_holding(
                    st.session_state, symbol=(symbol or "").strip(), shares=shares
                )
                if err:
                    st.warning(err)
                else:
                    _mark_tour(_CC_TOUR_ADJUSTED, step_id="adjust")
                    st.rerun()

        if dashboard.holdings:
            rcols = st.columns(min(len(dashboard.holdings), GUEST_MAX_HOLDINGS))
            for col, holding in zip(rcols, dashboard.holdings):
                with col:
                    if st.button(
                        f"Remove {holding.symbol}",
                        key=f"cc_demo_remove_{holding.symbol}",
                        use_container_width=True,
                    ):
                        remove_guest_holding(st.session_state, holding.symbol)
                        _mark_tour(_CC_TOUR_ADJUSTED, step_id="adjust")
                        st.rerun()

        if st.button("Reset to KO, JNJ, O", key="cc_demo_reset", use_container_width=True):
            save_guest_holdings(st.session_state, default_guest_holdings())
            st.session_state[GUEST_SPOTLIGHT_KEY] = "KO"
            for holding in default_guest_holdings():
                st.session_state[f"cc_demo_shares_{holding.symbol}"] = float(holding.shares)
            _mark_tour(_CC_TOUR_ADJUSTED, step_id="adjust")
            st.rerun()

    if dashboard.next_payouts:
        render_section_header("Upcoming estimated payouts", "From the shared market library")
        render_payout_list(
            [
                (
                    p.symbol,
                    f"${p.amount_usd:,.2f}",
                    f"pay ~{(p.pay_date.strftime('%d %b') if p.pay_date else 'TBD')} · {p.status}",
                )
                for p in dashboard.next_payouts[:5]
            ]
        )


def _render_income_chart(dashboard: GuestDashboard) -> None:
    if not dashboard.monthly_forecast:
        render_empty_state(
            "No forecast yet",
            "Add sample holdings on Overview to see an illustrative monthly forecast.",
        )
        return
    rows = [{"Month": label, "Estimated USD": value} for label, value in dashboard.monthly_forecast]
    st.dataframe(rows, use_container_width=True, hide_index=True)
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
        style_yield_channel_figure(fig, height=280)
        st.plotly_chart(fig, use_container_width=True, key="cc_demo_income_chart")
    except Exception:
        st.bar_chart(dict(dashboard.monthly_forecast), height=260)


def _render_income(dashboard: GuestDashboard) -> None:
    _mark_tour(_CC_TOUR_INCOME, step_id="income")
    render_page_header(
        "Keep estimated and received income separate.",
        "This sample has no broker cash history — received figures below are illustrative only.",
        kicker="Demo · Income",
    )

    render_section_header(
        "Estimated next 12 months",
        "Calculated from guest holdings and the shared market library.",
    )
    render_metric_strip(
        [
            (
                term_label("annual_dividend_income"),
                f"${dashboard.annual_income_usd:,.2f}",
                "Estimated",
                True,
            ),
            (
                "Monthly average",
                f"${(dashboard.annual_income_usd / 12) if dashboard.annual_income_usd else 0:,.2f}",
                "Estimated",
            ),
            (
                "Holdings",
                str(len(dashboard.holdings)),
                "Sample list",
            ),
            (
                "Status",
                "Estimated",
                "Not broker cash",
            ),
        ]
    )
    render_data_provenance("Label: Estimated · Projected · Illustrative forecast")
    _render_income_chart(dashboard)

    if dashboard.next_payouts:
        render_section_header("Upcoming estimated payments", "Library-based projections")
        render_payout_list(
            [
                (
                    p.symbol,
                    f"${p.amount_usd:,.2f}",
                    f"pay ~{(p.pay_date.strftime('%d %b %Y') if p.pay_date else 'TBD')} · {p.status}",
                )
                for p in dashboard.next_payouts[:5]
            ]
        )

    render_section_header(
        "Illustrative received-income example",
        "Example only · not connected to a broker account.",
    )
    example_gross = 548.0
    example_tax = 82.0
    example_net = 466.0
    render_metric_strip(
        [
            (term_label("gross_dividend"), f"${example_gross:,.2f}", "Illustrative example"),
            (term_label("withholding_tax"), f"${example_tax:,.2f}", "Illustrative example"),
            (term_label("net_dividend"), f"${example_net:,.2f}", "Illustrative example"),
            ("Broker link", "None", "Public demo"),
        ]
    )
    render_info_panel(
        "Illustrative received-income example — not connected to a broker account. "
        "Authenticated portfolios use imported broker cash for received totals."
    )
    with st.expander("Dividend terminology", expanded=False):
        for term_id in (
            "received_dividend",
            "accrued_dividend",
            "estimated_dividend",
            "gross_dividend",
            "withholding_tax",
            "net_dividend",
        ):
            st.markdown(f"**{term_label(term_id)}** — {term_help(term_id)}")


def _render_risk(dashboard: GuestDashboard) -> None:
    _mark_tour(_CC_TOUR_RISK, step_id="risk")
    render_page_header(
        "Explain the signal before asking for attention.",
        "Sample safety alerts only — review aids, not buy or sell recommendations.",
        kicker="Demo · Risk",
    )
    if not dashboard.safety_alerts:
        render_empty_state(
            "No attention items right now",
            "Adjust the sample list on Overview, or continue to Research.",
            icon="✅",
        )
        render_info_panel(
            "Not enough data from the shared library for Watch / Risky signals on this sample."
        )
        return

    render_section_header(
        "Portfolio attention",
        "Ordered for review — each card explains the signal and suggested next look.",
    )
    for alert in dashboard.safety_alerts:
        severity = _severity_label(alert.severity)
        with st.expander(f"{severity} · {alert.symbol}", expanded=severity == "Needs attention"):
            st.markdown(f"**{alert.company or alert.symbol}**")
            st.write(alert.message)
            st.caption("Source: shared market library · portfolio row metrics")
            st.caption("Educational next step: compare payout, yield, and growth on Research.")


def _render_research(dashboard: GuestDashboard) -> None:
    _mark_tour(_CC_TOUR_RESEARCH, step_id="research")
    symbols = [h.symbol for h in dashboard.holdings] or ["KO"]
    default = st.session_state.get(GUEST_SPOTLIGHT_KEY) or symbols[0]
    if default not in symbols:
        default = symbols[0]

    render_page_header(
        "Inspect evidence for one holding.",
        "Yield history and library metrics — not a personalized recommendation.",
        kicker="Demo · Research",
    )
    spotlight = st.selectbox(
        "Research spotlight",
        options=symbols,
        index=symbols.index(default),
        key="cc_demo_research_spotlight",
        help="Guest spotlight symbol for educational research",
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
        st.info("No library data for this symbol yet. Try KO, JNJ, or O.")
        return

    stock = analysis.stock_data
    yld = getattr(stock, "dividend_yield_pct", None)
    payout = getattr(stock, "payout_ratio_pct", None)
    safety = getattr(stock, "dividend_safety_score", None)
    render_metric_strip(
        [
            ("Company", stock.name or spotlight, spotlight),
            (
                "Dividend yield",
                f"{yld:.2f}%" if yld is not None else "—",
                "Library",
            ),
            (
                "Payout ratio",
                f"{payout:.1f}%" if payout is not None else "—",
                "Library",
            ),
            (
                "Safety signal",
                f"{safety:.0f}" if safety is not None else "—",
                "Research aid",
                True,
            ),
        ]
    )
    render_data_provenance(
        "Existing research components reused — no separate public-demo score is calculated."
    )

    from ui.components import UIComponents

    UIComponents.display_yield_channel_chart(
        spotlight,
        years=10,
        channel_data=analysis.yield_channel,
        vector_doc=analysis.document,
        show_header=True,
    )
    render_research_disclaimer(compact=True)


def _render_import() -> None:
    _mark_tour(_CC_TOUR_IMPORT, step_id="import")
    render_page_header(
        "Preview import safely — then create an account.",
        "The public demo never accepts real broker files.",
        kicker="Demo · Import",
    )
    render_info_panel(
        "File upload is disabled here for security. After you create a portfolio, "
        "authenticated Import accepts supported IBKR activity statements."
    )

    render_section_header("What can be imported", "After authentication")
    st.markdown(
        "- Trades and open positions\n"
        "- Deposits and withdrawals\n"
        "- Dividends and withholding taxes\n"
        "- Fees and corporate actions"
    )

    render_section_header("Example import summary", "Illustrative only")
    render_metric_strip(
        [
            ("Imported records", "48", "Example"),
            ("Updated records", "3", "Example"),
            ("Skipped duplicates", "12", "Example"),
            ("Warnings", "0", "Example"),
        ]
    )
    with st.expander("Example reconciliation", expanded=True):
        for label, status in (
            ("Position quantities", "Matched"),
            ("Cash by currency", "Matched"),
            ("Gross dividends", "Matched"),
            ("Withholding tax", "Matched"),
            ("Net dividend cash", "Matched"),
        ):
            st.markdown(f"- {label}: **{status}**")

    if st.button(
        "Create portfolio to import your statement",
        type="primary",
        use_container_width=True,
        key="cc_demo_import_auth",
    ):
        request_auth_panel(source_section="import")
        st.rerun()


def render_public_demo(*, route: PublicRoute, dashboard: GuestDashboard) -> None:
    """Render the active demo page only (expensive research loads on Research)."""
    page = route.demo_page
    _track_once(
        "public_demo_started",
        dedupe_key="started",
        properties={"source_section": "demo"},
    )
    _track_once(
        "public_demo_page_viewed",
        dedupe_key=page.value,
        properties={"demo_page": page.value},
    )

    render_info_panel(
        "Interactive demo · session-only sample portfolio · no account required. "
        "Follow the next-step card to walk through Overview → Income → Risk → Research → Import."
    )
    _render_demo_chrome(page)

    if page == DemoPage.OVERVIEW:
        _render_overview(dashboard)
    elif page == DemoPage.INCOME:
        _render_income(dashboard)
    elif page == DemoPage.RISK:
        _render_risk(dashboard)
    elif page == DemoPage.RESEARCH:
        _render_research(dashboard)
    elif page == DemoPage.IMPORT:
        _render_import()
