"""
Interactive public demo pages for the pre-login Command Center.

Guided walkthrough: Overview → Income → Risk → Create portfolio
Research and Sample import remain optional secondary routes.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from services.dividend_terminology import term_help, term_label
from services.guest_playground import (
    GUEST_IMPORT_CONFIRM_KEY,
    GUEST_IMPORT_PREVIEW_KEY,
    GUEST_INCOME_CONFIRM_KEY,
    GUEST_MAX_HOLDINGS,
    GUEST_SPOTLIGHT_KEY,
    GuestDashboard,
    add_guest_holding,
    apply_packaged_ibkr_sample_to_guest,
    default_guest_holdings,
    estimate_annual_income_usd,
    guest_holdings_from_session,
    load_packaged_ibkr_sample_preview,
    remove_guest_holding,
    save_guest_holdings,
)
from services.guidance_analytics import track_guidance_event
from ui.beta_disclaimer import render_research_disclaimer
from ui.command_center_home import (
    DemoPage,
    PublicRoute,
    PublicView,
    navigate_public,
    navigate_to_auth,
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

# Full demo nav (Research / Import remain optional secondary routes).
_DEMO_STEPS = (
    DemoPage.OVERVIEW,
    DemoPage.INCOME,
    DemoPage.RISK,
    DemoPage.RESEARCH,
    DemoPage.IMPORT,
)
_DEMO_STEP_LABELS = ("Overview", "Income", "Risk", "Research", "Import")
# Primary guided MVP journey — Create portfolio is the auth CTA, not a demo page.
_PRIMARY_JOURNEY = (DemoPage.OVERVIEW, DemoPage.INCOME, DemoPage.RISK)
_PRIMARY_JOURNEY_LABELS = ("Overview", "Income", "Risk", "Create portfolio")


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


def resolve_next_demo_step() -> DemoStep:
    """Primary MVP journey: Overview → Income → Risk → Create portfolio."""
    adjusted, income, risk, _research, _import_seen = _tour_flags()
    if not adjusted:
        return DemoStep(
            title="Adjust sample shares",
            description="Change KO, JNJ, or O quantities and submit to see estimated income update.",
            action_label="Stay on Overview",
            target_page=DemoPage.OVERVIEW,
        )
    if not income:
        return DemoStep(
            title="Review estimated vs sample received income",
            description=(
                "Open Income to see next-12-month estimates beside an illustrative "
                "received-cash example — not real broker cash."
            ),
            action_label="Open Income",
            target_page=DemoPage.INCOME,
        )
    if not risk:
        return DemoStep(
            title="Inspect one explained risk update",
            description="Review the highest-priority sample attention item and supporting metrics.",
            action_label="Open Risk",
            target_page=DemoPage.RISK,
        )
    return DemoStep(
        title="Create your portfolio",
        description=(
            "Guest holdings stay in this session and can transfer after sign-up. "
            "Research and Sample import remain optional."
        ),
        action_label="Create portfolio",
        target_page=None,
    )


def _primary_completed_count() -> int:
    adjusted, income, risk, _r, _i = _tour_flags()
    return sum(1 for done in (adjusted, income, risk) if done)


def _severity_label(raw: str) -> str:
    text = (raw or "").strip().lower()
    if text in {"high", "risky"}:
        return "Needs attention"
    if text in {"medium", "watch"}:
        return "Review"
    if text in {"low"}:
        return "Monitor"
    return "Not enough data"


def _render_demo_chrome(active: DemoPage) -> None:
    """Progress + page nav + next-step card — same shell on every demo page."""
    if active in _PRIMARY_JOURNEY:
        primary_index = _PRIMARY_JOURNEY.index(active)
    else:
        primary_index = len(_PRIMARY_JOURNEY)  # optional secondary page
    render_demo_progress(
        list(_PRIMARY_JOURNEY_LABELS),
        active_index=min(primary_index, len(_PRIMARY_JOURNEY_LABELS) - 1),
        completed_through=_primary_completed_count() - 1,
    )

    cols = st.columns(len(_DEMO_STEPS))
    for col, page, label in zip(cols, _DEMO_STEPS, _DEMO_STEP_LABELS):
        with col:
            selected = page == active
            secondary = page not in _PRIMARY_JOURNEY
            text = (
                f"{label} · active" if selected else (f"{label} · optional" if secondary else label)
            )
            st.button(
                text,
                key=f"cc_demo_nav_{page.value}",
                use_container_width=True,
                type="primary" if selected else "secondary",
                disabled=selected,
                on_click=navigate_public,
                args=(PublicView.DEMO, page),
                kwargs={"source_section": "demo_nav"},
            )

    step = resolve_next_demo_step()
    done = _primary_completed_count()
    kicker = (
        "Guided demo complete — create your portfolio"
        if done >= len(_PRIMARY_JOURNEY)
        else f"MVP journey · {done} of {len(_PRIMARY_JOURNEY)} complete"
    )
    render_action_card(step.title, step.description, kicker=kicker)
    if step.target_page == active:
        st.caption("Complete the action on this page, then continue with the button below.")


def _submit_share_updates() -> None:
    """Form submit callback — holdings update before the Streamlit rerun."""
    before = estimate_annual_income_usd(guest_holdings_from_session(st.session_state))
    holdings = guest_holdings_from_session(st.session_state)
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
            changed = True
    after = estimate_annual_income_usd(guest_holdings_from_session(st.session_state))
    if changed:
        track_guidance_event(
            "guest_holding_quantity_changed",
            session=st.session_state,
            properties={"holding_count": len(holdings)},
        )
        _mark_tour(_CC_TOUR_ADJUSTED, step_id="adjust")
        st.session_state[GUEST_INCOME_CONFIRM_KEY] = {
            "before": before,
            "after": after,
        }


def _reset_demo_holdings() -> None:
    before = estimate_annual_income_usd(guest_holdings_from_session(st.session_state))
    save_guest_holdings(st.session_state, default_guest_holdings())
    st.session_state[GUEST_SPOTLIGHT_KEY] = "KO"
    for holding in default_guest_holdings():
        st.session_state[f"cc_demo_shares_{holding.symbol}"] = float(holding.shares)
    after = estimate_annual_income_usd(guest_holdings_from_session(st.session_state))
    _mark_tour(_CC_TOUR_ADJUSTED, step_id="adjust")
    st.session_state[GUEST_INCOME_CONFIRM_KEY] = {"before": before, "after": after}


def _render_income_confirmation() -> None:
    confirm = st.session_state.get(GUEST_INCOME_CONFIRM_KEY)
    if isinstance(confirm, dict):
        before = float(confirm.get("before") or 0.0)
        after = float(confirm.get("after") or 0.0)
        st.success(
            f"Sample holdings updated. Estimated annual income: "
            f"**${before:,.2f}** → **${after:,.2f}**."
        )
    import_confirm = st.session_state.get(GUEST_IMPORT_CONFIRM_KEY)
    if isinstance(import_confirm, dict):
        symbols = ", ".join(str(s) for s in (import_confirm.get("symbols") or []))
        st.success(
            f"Imported sample applied · {import_confirm.get('holding_count', 0)} holdings "
            f"({symbols}). Parsed {import_confirm.get('open_positions', 0)} positions, "
            f"{import_confirm.get('trades', 0)} trades, "
            f"{import_confirm.get('dividends', 0)} dividends. Session only — not saved to a database."
        )


def _top_alert(dashboard: GuestDashboard):
    if not dashboard.safety_alerts:
        return None
    return dashboard.safety_alerts[0]


def _render_overview(dashboard: GuestDashboard) -> None:
    render_page_header(
        "Start with the one thing that matters next.",
        "Sample portfolio only — adjust holdings and watch estimated income update.",
        kicker="Demo · Overview",
    )
    _render_income_confirmation()

    top = _top_alert(dashboard)
    attention = (
        f"{top.symbol}: {top.message}"
        if top is not None
        else "No high-priority attention item in this sample."
    )
    render_metric_strip(
        [
            (
                "Estimated annual income",
                f"${dashboard.annual_income_usd:,.2f}",
                "Estimated",
                True,
            ),
            (
                "Near-term expected income",
                f"${dashboard.near_term_income_usd:,.2f}",
                "Next sample payouts",
            ),
            (
                "Highest attention item",
                top.symbol if top is not None else "None",
                attention[:80] + ("…" if len(attention) > 80 else ""),
            ),
            (
                "Holdings",
                str(len(dashboard.holdings)),
                f"Mode: {dashboard.data_mode}",
            ),
        ]
    )
    render_data_provenance(dashboard.provenance_label)

    render_section_header(
        "Update sample holdings",
        f"Up to {GUEST_MAX_HOLDINGS} names. Submit to recalculate estimated income.",
    )
    holdings = list(dashboard.holdings)
    if not holdings:
        render_empty_state(
            "No sample holdings",
            "Reset to KO, JNJ, and O to continue the walkthrough.",
            icon="📂",
        )
    else:
        with st.form("cc_demo_shares_form"):
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
            st.form_submit_button(
                "Update sample holdings",
                type="primary",
                use_container_width=True,
                on_click=_submit_share_updates,
            )
        render_ticker_chips(
            [
                (
                    h.symbol,
                    f"{h.shares:.0f} sh · {h.company_name or h.symbol}",
                )
                for h in holdings
            ]
        )

    st.button(
        "Continue to Income",
        type="primary",
        use_container_width=True,
        key="cc_overview_to_income",
        on_click=navigate_public,
        args=(PublicView.DEMO, DemoPage.INCOME),
        kwargs={"source_section": "overview_cta"},
    )

    with st.expander("Add, remove, or reset sample holdings", expanded=False):
        st.caption("Optional — the walkthrough works with the default KO, JNJ, O list.")
        add_c1, add_c2, add_c3 = st.columns([2.2, 1, 1])
        with add_c1:
            symbol = st.text_input("Ticker", key="cc_demo_add_symbol", placeholder="e.g. VZ")
        with add_c2:
            shares = st.number_input(
                "Shares", min_value=1.0, value=10.0, step=1.0, key="cc_demo_add_shares"
            )
        with add_c3:
            if st.button("Add", type="primary", use_container_width=True, key="cc_demo_add_btn"):
                before = estimate_annual_income_usd(guest_holdings_from_session(st.session_state))
                _, err = add_guest_holding(
                    st.session_state, symbol=(symbol or "").strip(), shares=shares
                )
                if err:
                    st.warning(err)
                else:
                    after = estimate_annual_income_usd(
                        guest_holdings_from_session(st.session_state)
                    )
                    st.session_state[GUEST_INCOME_CONFIRM_KEY] = {
                        "before": before,
                        "after": after,
                    }
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

        st.button(
            "Reset to KO, JNJ, O",
            key="cc_demo_reset",
            use_container_width=True,
            on_click=_reset_demo_holdings,
        )

    if dashboard.next_payouts:
        render_section_header("Upcoming estimated payouts", "Sample schedule")
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
        "Calculated from the guest sample (snapshot or library enrichment).",
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
    render_data_provenance(dashboard.provenance_label)
    _render_income_chart(dashboard)

    if dashboard.next_payouts:
        render_section_header("Upcoming estimated payments", "Sample schedule")
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
        "Sample received-income example",
        "Scaled to the current sample list · not connected to a broker account.",
    )
    render_metric_strip(
        [
            (
                term_label("gross_dividend"),
                f"${dashboard.sample_received_gross_usd:,.2f}",
                "Illustrative example",
            ),
            (
                term_label("withholding_tax"),
                f"${dashboard.sample_withholding_usd:,.2f}",
                "Illustrative example",
            ),
            (
                term_label("net_dividend"),
                f"${dashboard.sample_received_net_usd:,.2f}",
                "Illustrative example",
            ),
            ("Broker link", "None", "Public demo"),
        ]
    )
    render_info_panel(
        "Illustrative received-income example — not connected to a broker account. "
        "Authenticated portfolios use imported broker cash for received totals."
    )
    st.button(
        "Continue to Risk",
        type="primary",
        use_container_width=True,
        key="cc_income_to_risk",
        on_click=navigate_public,
        args=(PublicView.DEMO, DemoPage.RISK),
        kwargs={"source_section": "income_cta"},
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
    top = _top_alert(dashboard)
    if top is None:
        render_empty_state(
            "No attention items right now",
            "Adjust the sample list on Overview, or continue to Create portfolio.",
            icon="✅",
        )
        render_info_panel(
            "Snapshot mode still works without library alerts — create a portfolio "
            "when you are ready to analyze your own holdings."
        )
        st.button(
            "Create portfolio",
            type="primary",
            use_container_width=True,
            key="cc_risk_to_auth_empty",
            on_click=navigate_to_auth,
            kwargs={"source_section": "risk_cta"},
        )
        return

    severity = _severity_label(top.severity)
    render_section_header(
        "Highest-priority attention item",
        "One explained sample signal — educational research only.",
    )
    row = next((r for r in dashboard.rows if getattr(r, "ticker", "") == top.symbol), None)
    payout = getattr(row, "payout_ratio_pct", None) if row is not None else None
    yld = getattr(row, "dividend_yield_pct", None) if row is not None else None
    income = getattr(row, "annual_income", None) if row is not None else None
    render_metric_strip(
        [
            ("Holding", top.symbol, top.company or top.symbol, True),
            ("Priority", severity, top.severity.title()),
            (
                "Payout ratio",
                f"{payout:.0f}%" if payout is not None else "—",
                "Supporting metric",
            ),
            (
                "Yield",
                f"{yld:.1f}%" if yld is not None else "—",
                (f"Est. income ${income:,.0f}" if income is not None else "Supporting metric"),
            ),
        ]
    )
    st.markdown(f"**Reason:** {top.message}")
    st.caption(
        f"Suggested research check: {top.suggested_check} "
        "Use the optional **Research** tab if you want a closer look."
    )
    render_data_provenance(dashboard.provenance_label)
    st.session_state[GUEST_SPOTLIGHT_KEY] = top.symbol

    if len(dashboard.safety_alerts) > 1:
        with st.expander("Other sample attention items", expanded=False):
            for alert in dashboard.safety_alerts[1:]:
                st.markdown(
                    f"**{_severity_label(alert.severity)} · {alert.symbol}** — {alert.message}"
                )

    st.button(
        "Create portfolio",
        type="primary",
        use_container_width=True,
        key="cc_risk_to_auth",
        on_click=navigate_to_auth,
        kwargs={"source_section": "risk_cta"},
    )


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
        snap = None
        from services.guest_playground import demo_snapshot_for

        snap = demo_snapshot_for(spotlight)
        st.warning(
            f"Research library data is unavailable for {spotlight}. "
            "Showing the illustrative snapshot fallback instead."
        )
        if snap is not None:
            render_metric_strip(
                [
                    ("Company", snap.company, spotlight),
                    ("Dividend yield", f"{snap.dividend_yield_pct:.2f}%", "Snapshot"),
                    ("Payout ratio", f"{snap.payout_ratio_pct:.1f}%", "Snapshot"),
                    (
                        "Annual DPS",
                        f"${snap.annual_dividend_per_share:.2f}",
                        "Snapshot",
                        True,
                    ),
                ]
            )
            render_data_provenance(
                "Snapshot fallback · market library unavailable · sample data only"
            )
        else:
            render_empty_state(
                "No research data",
                "Try KO, JNJ, or O — symbols with packaged snapshot support.",
            )
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


def _load_sample_import_preview() -> None:
    preview = load_packaged_ibkr_sample_preview()
    st.session_state[GUEST_IMPORT_PREVIEW_KEY] = {
        "open_positions": preview.open_positions,
        "trades": preview.trades,
        "dividends": preview.dividends,
        "withholdings": preview.withholdings,
        "deposits": preview.deposits,
        "warnings": preview.warnings,
        "symbols": [row[0] for row in preview.position_rows],
    }
    _mark_tour(_CC_TOUR_IMPORT, step_id="import")


def _use_imported_sample() -> None:
    apply_packaged_ibkr_sample_to_guest(st.session_state)
    _mark_tour(_CC_TOUR_IMPORT, step_id="import")
    _mark_tour(_CC_TOUR_ADJUSTED, step_id="adjust")
    navigate_public(
        PublicView.DEMO,
        DemoPage.OVERVIEW,
        source_section="import_apply",
    )


def _render_import() -> None:
    _mark_tour(_CC_TOUR_IMPORT, step_id="import")
    render_page_header(
        "Preview a packaged sample import — then create an account.",
        "The public demo never accepts arbitrary broker file uploads.",
        kicker="Demo · Import",
    )
    render_info_panel(
        "Only the packaged fictitious IBKR sample can be loaded here. "
        "After you create a portfolio, authenticated Import accepts your own "
        "supported IBKR activity statements."
    )

    render_section_header("What can be imported", "After authentication")
    st.markdown(
        "- Trades and open positions\n"
        "- Deposits and withdrawals\n"
        "- Dividends and withholding taxes\n"
        "- Fees and corporate actions"
    )

    st.button(
        "Load sample IBKR statement",
        type="primary",
        use_container_width=True,
        key="cc_demo_load_sample_ibkr",
        on_click=_load_sample_import_preview,
    )

    preview = st.session_state.get(GUEST_IMPORT_PREVIEW_KEY)
    if isinstance(preview, dict) and preview.get("open_positions") is not None:
        render_section_header(
            "Sample import summary",
            "Parsed from the packaged fictitious AS_Fv2 CSV · session only",
        )
        render_metric_strip(
            [
                ("Open positions", str(preview.get("open_positions", 0)), "Parsed"),
                ("Trades", str(preview.get("trades", 0)), "Parsed"),
                ("Dividends", str(preview.get("dividends", 0)), "Parsed"),
                ("Warnings", str(preview.get("warnings", 0)), "Parsed"),
            ]
        )
        render_data_provenance(
            "Packaged demo CSV · fictitious account DU0000001 · no database writes"
        )
        symbols = preview.get("symbols") or []
        if symbols:
            st.caption("Open positions: " + ", ".join(str(s) for s in symbols))
        st.button(
            "Use this imported sample",
            type="primary",
            use_container_width=True,
            key="cc_demo_use_sample_ibkr",
            on_click=_use_imported_sample,
        )
    else:
        st.caption("Load the packaged sample to see parser-derived totals.")
    st.caption(
        "Create a portfolio from the header when you are ready to import your own statement."
    )


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
        "Primary journey: Overview → Income → Risk → Create portfolio. "
        "Research and Sample import are optional."
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
