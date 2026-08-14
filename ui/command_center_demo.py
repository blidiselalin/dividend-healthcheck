"""
Interactive public demo pages for the pre-login Command Center.

Guided walkthrough: Overview → Income → Risk → Create portfolio
Research and Sample import remain optional secondary routes.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import streamlit as st

from services.dividend_terminology import term_help, term_label
from services.guest_playground import (
    GUEST_IMPORT_PREVIEW_KEY,
    GUEST_INCOME_CONFIRM_KEY,
    GUEST_MAX_HOLDINGS,
    GUEST_SPOTLIGHT_KEY,
    GuestDashboard,
    GuestHolding,
    add_guest_holding,
    apply_packaged_ibkr_sample_to_guest,
    default_guest_holdings,
    default_guest_symbols,
    demo_price_caption,
    demo_risk_kind_label,
    demo_snapshot_for,
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
    PublicButtonVariant,
    PublicRoute,
    PublicView,
    guest_attention_items,
    navigate_public,
    navigate_to_auth,
    render_public_button,
    set_public_feedback,
)
from ui.design_system import (
    render_action_card,
    render_attention_list,
    render_data_provenance,
    render_demo_progress,
    render_empty_state,
    render_info_panel,
    render_metric_strip,
    render_page_header,
    render_payout_list,
    render_section_header,
    render_story_cards,
    render_ticker_chips,
)

# Session-only guided demo tour (not authenticated NBA).
_CC_TOUR_ADJUSTED = "cc_tour_adjusted"
_CC_TOUR_INCOME = "cc_tour_income_opened"
_CC_TOUR_RISK = "cc_tour_risk_opened"
_CC_TOUR_RESEARCH = "cc_tour_research_opened"
_CC_TOUR_IMPORT = "cc_tour_import_opened"
_ANALYTICS_LAST_KEY = "command_center_last_analytics"

_PRIMARY_NAV = (DemoPage.OVERVIEW, DemoPage.INCOME, DemoPage.RISK)
_PRIMARY_NAV_LABELS = ("Overview", "Income", "Risk")
_OPTIONAL_NAV = (DemoPage.RESEARCH, DemoPage.IMPORT)
_OPTIONAL_NAV_LABELS = ("Research", "Sample import")
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
            description="Change sample quantities and submit to see estimated income update.",
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
            description="Review the sample risk mix — five distinct signal types across sectors.",
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


def _render_demo_nav(active: DemoPage) -> None:
    """Progress + primary/optional page nav."""
    if active in _PRIMARY_JOURNEY:
        primary_index = _PRIMARY_JOURNEY.index(active)
    else:
        primary_index = len(_PRIMARY_JOURNEY)
    render_demo_progress(
        list(_PRIMARY_JOURNEY_LABELS),
        active_index=min(primary_index, len(_PRIMARY_JOURNEY_LABELS) - 1),
        completed_through=_primary_completed_count() - 1,
    )

    with st.container(key="cc_demo_nav_primary"):
        cols = st.columns(len(_PRIMARY_NAV))
        for col, page, label in zip(cols, _PRIMARY_NAV, _PRIMARY_NAV_LABELS):
            with col:
                render_public_button(
                    label,
                    key=f"cc_demo_nav_{page.value}",
                    variant=PublicButtonVariant.TAB,
                    selected=page == active,
                    on_click=navigate_public,
                    args=(PublicView.DEMO, page),
                    kwargs={"source_section": "demo_nav"},
                )

    with st.container(key="cc_demo_nav_optional"):
        st.caption("Optional")
        cols = st.columns(len(_OPTIONAL_NAV))
        for col, page, label in zip(cols, _OPTIONAL_NAV, _OPTIONAL_NAV_LABELS):
            with col:
                render_public_button(
                    label,
                    key=f"cc_demo_nav_{page.value}",
                    variant=PublicButtonVariant.TAB,
                    selected=page == active,
                    on_click=navigate_public,
                    args=(PublicView.DEMO, page),
                    kwargs={"source_section": "demo_nav"},
                )


def _render_demo_footer(active: DemoPage) -> None:
    """Guided next-step card + the single journey CTA for this page."""
    step = resolve_next_demo_step()
    done = _primary_completed_count()
    kicker = (
        "Guided demo complete — create your portfolio"
        if done >= len(_PRIMARY_JOURNEY)
        else f"MVP journey · {done} of {len(_PRIMARY_JOURNEY)} complete"
    )
    with st.container(key="cc_demo_next_step"):
        render_action_card(step.title, step.description, kicker=kicker)
        if active == DemoPage.OVERVIEW:
            render_public_button(
                "Continue to Income",
                key="cc_overview_to_income",
                variant=PublicButtonVariant.PRIMARY,
                on_click=navigate_public,
                args=(PublicView.DEMO, DemoPage.INCOME),
                kwargs={"source_section": "overview_cta"},
            )
        elif active == DemoPage.INCOME:
            render_public_button(
                "Continue to Risk",
                key="cc_income_to_risk",
                variant=PublicButtonVariant.PRIMARY,
                on_click=navigate_public,
                args=(PublicView.DEMO, DemoPage.RISK),
                kwargs={"source_section": "income_cta"},
            )
        elif active == DemoPage.RISK:
            render_public_button(
                "Create portfolio",
                key="cc_risk_to_auth",
                variant=PublicButtonVariant.PRIMARY,
                on_click=navigate_to_auth,
                kwargs={"source_section": "risk_cta"},
            )
        elif step.target_page is not None:
            render_public_button(
                f"Go to {step.target_page.value.title()}",
                key="cc_demo_next_optional",
                variant=PublicButtonVariant.SECONDARY,
                on_click=navigate_public,
                args=(PublicView.DEMO, step.target_page),
                kwargs={"source_section": "demo_next"},
            )
        else:
            render_public_button(
                "Create portfolio",
                key="cc_demo_next_auth",
                variant=PublicButtonVariant.PRIMARY,
                on_click=navigate_to_auth,
                kwargs={"source_section": "demo_next"},
            )


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
    if not changed:
        set_public_feedback("info", "No holding changes to apply.", "update")
        return
    track_guidance_event(
        "guest_holding_quantity_changed",
        session=st.session_state,
        properties={"holding_count": len(holdings)},
    )
    _mark_tour(_CC_TOUR_ADJUSTED, step_id="adjust")
    st.session_state[GUEST_INCOME_CONFIRM_KEY] = {"before": before, "after": after}
    set_public_feedback(
        "success",
        f"Sample holdings updated. Estimated annual income: **${before:,.2f}** → **${after:,.2f}**.",
        "update",
    )


def _reset_demo_holdings() -> None:
    before = estimate_annual_income_usd(guest_holdings_from_session(st.session_state))
    save_guest_holdings(st.session_state, default_guest_holdings())
    st.session_state[GUEST_SPOTLIGHT_KEY] = "KO"
    for holding in default_guest_holdings():
        st.session_state[f"cc_demo_shares_{holding.symbol}"] = float(holding.shares)
    after = estimate_annual_income_usd(guest_holdings_from_session(st.session_state))
    _mark_tour(_CC_TOUR_ADJUSTED, step_id="adjust")
    st.session_state[GUEST_INCOME_CONFIRM_KEY] = {"before": before, "after": after}
    set_public_feedback(
        "success",
        (
            "Restored the diversified sample list "
            f"({len(default_guest_symbols())} holdings across sectors)."
        ),
        "reset",
    )


def _add_holding_clicked() -> None:
    symbol = str(st.session_state.get("cc_demo_add_symbol") or "").strip()
    shares = float(st.session_state.get("cc_demo_add_shares") or 0.0)
    before = estimate_annual_income_usd(guest_holdings_from_session(st.session_state))
    _, err = add_guest_holding(st.session_state, symbol=symbol, shares=shares)
    if err:
        set_public_feedback("warning", err, "add")
        return
    after = estimate_annual_income_usd(guest_holdings_from_session(st.session_state))
    ticker = symbol.upper()
    _mark_tour(_CC_TOUR_ADJUSTED, step_id="adjust")
    st.session_state[GUEST_INCOME_CONFIRM_KEY] = {"before": before, "after": after}
    set_public_feedback(
        "success",
        f"Added {ticker} · {shares:.0f} shares. Estimated annual income: "
        f"**${before:,.2f}** → **${after:,.2f}**.",
        "add",
    )


def _remove_holding_clicked(symbol: str) -> None:
    _, err = remove_guest_holding(st.session_state, symbol)
    if err:
        set_public_feedback("warning", err, "remove")
        return
    _mark_tour(_CC_TOUR_ADJUSTED, step_id="adjust")
    set_public_feedback("success", f"Removed {symbol} from the sample list.", "remove")


def _iter_item_columns(
    items: Sequence[GuestHolding], per_row: int = 4
) -> Iterator[tuple[object, GuestHolding]]:
    """Yield (column, item) in wrapped rows so 10+ controls stay usable."""
    for start in range(0, len(items), per_row):
        chunk = items[start : start + per_row]
        cols = st.columns(len(chunk))
        yield from zip(cols, chunk)


def _top_alert(dashboard: GuestDashboard):
    if not dashboard.safety_alerts:
        return None
    return dashboard.safety_alerts[0]


def _render_overview(dashboard: GuestDashboard) -> None:
    render_page_header(
        "Start with the one thing that matters next.",
        f"The sample list spans {len(default_guest_symbols())} sectors. "
        "Change shares, then review income and the risk mix.",
        kicker="Demo · Overview",
    )

    yield_label = (
        f"{dashboard.portfolio_yield_pct:.2f}% yield"
        if dashboard.portfolio_yield_pct is not None
        else "Estimated"
    )
    render_metric_strip(
        [
            (
                "Portfolio value",
                f"${dashboard.portfolio_value_usd:,.2f}",
                demo_price_caption(dashboard),
            ),
            (
                "Estimated next 12 months",
                f"${dashboard.annual_income_usd:,.2f}",
                yield_label,
                True,
            ),
            (
                "Sample received",
                f"${dashboard.sample_received_gross_usd:,.2f}",
                "Sample received · not broker cash",
            ),
            (
                "Near-term expected",
                f"${dashboard.near_term_income_usd:,.2f}",
                "Next sample payouts",
            ),
        ]
    )
    render_data_provenance(dashboard.provenance_label)

    attention = guest_attention_items(dashboard)
    chart_col, attention_col = st.columns([1.15, 0.85], gap="large")
    with chart_col:
        render_section_header(
            "Next 12 months · estimated income",
            "Forward income from library dividends × sample shares.",
        )
        _render_income_chart(dashboard)
    with attention_col:
        render_section_header("Portfolio attention", "Ordered by review priority.")
        if attention:
            render_attention_list(attention)
        else:
            render_info_panel("No sample attention items for the current holdings.")

    render_section_header(
        "Portfolio positions",
        "Income contribution and signal stay visible together.",
    )
    rows_by_symbol = {getattr(row, "ticker", ""): row for row in dashboard.rows}
    table_rows: list[dict[str, str]] = []
    for holding in dashboard.holdings:
        row = rows_by_symbol.get(holding.symbol)
        value = getattr(row, "current_value", None) if row is not None else None
        income = getattr(row, "annual_income", None) if row is not None else None
        yld = getattr(row, "dividend_yield_pct", None) if row is not None else None
        signal = next(
            (status for symbol, _c, _m, status in attention if symbol == holding.symbol),
            "Healthy",
        )
        snap = demo_snapshot_for(holding.symbol)
        table_rows.append(
            {
                "Holding": f"{holding.symbol} · {holding.company_name or holding.symbol}",
                "Shares": f"{holding.shares:.0f}",
                "Value": f"${value:,.0f}" if value is not None else "—",
                "Annual income": f"${income:,.2f}" if income is not None else "—",
                "Yield": f"{yld:.1f}%" if yld is not None else "—",
                "Sector": snap.sector if snap is not None else "—",
                "Signal": signal,
            }
        )
    if table_rows:
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

    render_section_header(
        "Update sample holdings",
        f"Up to {GUEST_MAX_HOLDINGS} names across sectors. Submit to recalculate estimated income.",
    )
    holdings = list(dashboard.holdings)
    if not holdings:
        render_empty_state(
            "No sample holdings",
            "Reset the diversified sample list to continue the walkthrough.",
            icon="📂",
        )
    else:
        with st.form("cc_demo_shares_form"):
            for col, holding in _iter_item_columns(holdings, per_row=5):
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
            render_public_button(
                "Update sample holdings",
                key="cc_demo_update_holdings",
                variant=PublicButtonVariant.PRIMARY,
                submit=True,
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

    with st.expander("Add, remove, or reset sample holdings", expanded=False):
        st.caption("Optional — the walkthrough works with the default 10-name sector mix.")
        with st.container(key="cc_holdings_add"):
            add_c1, add_c2, add_c3 = st.columns([2.2, 1, 1])
            with add_c1:
                st.text_input("Ticker", key="cc_demo_add_symbol", placeholder="e.g. PG")
            with add_c2:
                st.number_input(
                    "Shares", min_value=1.0, value=10.0, step=1.0, key="cc_demo_add_shares"
                )
            with add_c3:
                render_public_button(
                    "Add holding",
                    key="cc_demo_add_btn",
                    variant=PublicButtonVariant.SECONDARY,
                    on_click=_add_holding_clicked,
                )

        if dashboard.holdings:
            for col, holding in _iter_item_columns(list(dashboard.holdings), per_row=5):
                with col:
                    render_public_button(
                        f"Remove {holding.symbol}",
                        key=f"cc_demo_remove_{holding.symbol}",
                        variant=PublicButtonVariant.DANGER,
                        on_click=_remove_holding_clicked,
                        args=(holding.symbol,),
                    )
            if len(dashboard.holdings) <= 1:
                st.caption("Keep at least one sample holding so income and risk stay visible.")

        render_public_button(
            "Reset sample list",
            key="cc_demo_reset",
            variant=PublicButtonVariant.GHOST,
            on_click=_reset_demo_holdings,
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
        "Do not mix cash received with cash expected.",
        "Gross, tax, and net stay separate from the 12-month estimate. This sample has no broker cash history.",
        kicker="Demo · Income",
    )

    render_metric_strip(
        [
            (
                term_label("gross_dividend"),
                f"${dashboard.sample_received_gross_usd:,.2f}",
                "Scaled sample · not broker cash",
            ),
            (
                term_label("withholding_tax"),
                f"${dashboard.sample_withholding_usd:,.2f}",
                "Shown separately",
            ),
            (
                term_label("net_dividend"),
                f"${dashboard.sample_received_net_usd:,.2f}",
                "Scaled sample · not broker cash",
            ),
            (
                term_label("annual_dividend_income"),
                f"${dashboard.annual_income_usd:,.2f}",
                demo_price_caption(dashboard),
                True,
            ),
        ]
    )
    render_data_provenance(dashboard.provenance_label)
    render_info_panel(
        "The received figures above are a scaled sample — not connected to a broker account. "
        "After you create a portfolio, imported IBKR cash is used for received totals."
    )

    render_section_header(
        "Forward income profile",
        "Expected gross cash by month · sample schedule.",
    )
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


def _risk_mix_rows(dashboard: GuestDashboard) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for holding in dashboard.holdings:
        snap = demo_snapshot_for(holding.symbol)
        if snap is None:
            rows.append(
                {
                    "Holding": holding.symbol,
                    "Sector": "—",
                    "Risk type": "Not in sample snapshots",
                    "Priority": "—",
                }
            )
            continue
        if snap.alert_severity in {"high", "risky"}:
            priority = "Needs attention"
        elif snap.alert_severity in {"medium", "watch"}:
            priority = "Review"
        else:
            priority = "Healthy"
        rows.append(
            {
                "Holding": holding.symbol,
                "Sector": snap.sector,
                "Risk type": demo_risk_kind_label(snap.risk_kind),
                "Priority": priority,
            }
        )
    return rows


def _render_risk_mix(dashboard: GuestDashboard) -> None:
    mix = _risk_mix_rows(dashboard)
    if not mix:
        return
    render_section_header(
        "Sample risk mix",
        "Risk types come from Clear Dividend Risk when the market library has the holding.",
    )
    st.dataframe(mix, use_container_width=True, hide_index=True)


def _render_risk(dashboard: GuestDashboard) -> None:
    _mark_tour(_CC_TOUR_RISK, step_id="risk")
    render_page_header(
        "Explain the signal before asking for attention.",
        "Scores are a review aid. Each one can be challenged — not a buy or sell recommendation.",
        kicker="Demo · Risk",
    )
    top = _top_alert(dashboard)
    attention = guest_attention_items(dashboard)
    if top is None:
        render_empty_state(
            "No high-priority attention items right now",
            "Healthy sample holdings still appear below. Create a portfolio to analyze your own list.",
            icon="✅",
        )
        if attention:
            render_attention_list(attention)
        _render_risk_mix(dashboard)
        return

    severity = _severity_label(top.severity)
    kind_label = demo_risk_kind_label(top.risk_kind)
    render_section_header(
        f"Why {top.symbol} is marked “{severity}”",
        "One explained sample signal — educational research only, not a buy or sell recommendation.",
    )
    if attention:
        render_attention_list(attention)
    row = next((r for r in dashboard.rows if getattr(r, "ticker", "") == top.symbol), None)
    payout = getattr(row, "payout_ratio_pct", None) if row is not None else None
    yld = getattr(row, "dividend_yield_pct", None) if row is not None else None
    income = getattr(row, "annual_income", None) if row is not None else None
    render_metric_strip(
        [
            ("Holding", top.symbol, top.company or top.symbol, True),
            ("Risk type", kind_label, top.sector or "Sample"),
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
    _render_risk_mix(dashboard)
    render_data_provenance(dashboard.provenance_label)
    st.session_state[GUEST_SPOTLIGHT_KEY] = top.symbol


def _render_research(dashboard: GuestDashboard) -> None:
    _mark_tour(_CC_TOUR_RESEARCH, step_id="research")
    symbols = [h.symbol for h in dashboard.holdings] or ["KO"]
    default = st.session_state.get(GUEST_SPOTLIGHT_KEY) or symbols[0]
    if default not in symbols:
        default = symbols[0]

    render_page_header(
        "Inspect evidence for one holding.",
        "The score summarizes evidence; the factors explain it. Not a personalized recommendation.",
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
                "Try a sample-list ticker with packaged snapshot support.",
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
    try:
        preview = load_packaged_ibkr_sample_preview()
    except (OSError, UnicodeError, ValueError, KeyError, AttributeError) as exc:
        set_public_feedback(
            "error",
            "Could not load the packaged sample statement. Try again or continue with the default list.",
            "import_load",
        )
        track_guidance_event(
            "public_demo_import_failed",
            session=st.session_state,
            properties={"source_section": "import_load", "error": type(exc).__name__},
        )
        return
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
    set_public_feedback(
        "success",
        f"Sample statement loaded · {preview.open_positions} positions, "
        f"{preview.trades} trades, {preview.dividends} dividends.",
        "import_load",
    )


def _use_imported_sample() -> None:
    try:
        holdings, preview = apply_packaged_ibkr_sample_to_guest(st.session_state)
    except (OSError, UnicodeError, ValueError, KeyError, AttributeError) as exc:
        set_public_feedback(
            "error",
            "Could not apply the packaged sample. The current guest list was left unchanged.",
            "import_apply",
        )
        track_guidance_event(
            "public_demo_import_failed",
            session=st.session_state,
            properties={"source_section": "import_apply", "error": type(exc).__name__},
        )
        return
    _mark_tour(_CC_TOUR_IMPORT, step_id="import")
    _mark_tour(_CC_TOUR_ADJUSTED, step_id="adjust")
    symbols = ", ".join(h.symbol for h in holdings)
    set_public_feedback(
        "success",
        f"Imported sample applied · {len(holdings)} holdings ({symbols}). "
        f"Parsed {preview.open_positions} positions, {preview.trades} trades, "
        f"{preview.dividends} dividends. Session only — not saved to a database.",
        "import_apply",
    )
    navigate_public(
        PublicView.DEMO,
        DemoPage.OVERVIEW,
        source_section="import_apply",
    )


def _render_import() -> None:
    _mark_tour(_CC_TOUR_IMPORT, step_id="import")
    render_page_header(
        "A successful import is one you can verify.",
        "The public demo loads a packaged fictitious IBKR sample only — it never accepts arbitrary uploads.",
        kicker="Demo · Import",
    )
    render_story_cards(
        [
            (
                "1",
                "Select and preview",
                "See positions, trades, and dividends before anything is applied.",
                "Outcome: you know what will change.",
            ),
            (
                "2",
                "Normalize",
                "Map cash, dividends, and taxes into one internal model.",
                "Outcome: record types are understandable.",
            ),
            (
                "3",
                "Apply in session",
                "Replace the guest list from parsed open positions — no database write.",
                "Outcome: the sample portfolio updates.",
            ),
            (
                "4",
                "Reconcile later",
                "After sign-up, your own statement is checked before the portfolio is trusted.",
                "Outcome: received cash can be verified.",
            ),
        ]
    )

    render_public_button(
        "Load sample IBKR statement",
        key="cc_demo_load_sample_ibkr",
        variant=PublicButtonVariant.PRIMARY,
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
        render_public_button(
            "Use this imported sample",
            key="cc_demo_use_sample_ibkr",
            variant=PublicButtonVariant.PRIMARY,
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
        "Demo mode: session-only sample portfolio. Received and estimated amounts stay separate."
    )
    _render_demo_nav(page)

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

    _render_demo_footer(page)
