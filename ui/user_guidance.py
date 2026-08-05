"""
Contextual help UI — next-best action, empty states, help drawer, term tooltips.

Business rules live in services/; this module only renders and navigates.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from services.dividend_terminology import DIVIDEND_TERM_LABELS, DIVIDEND_TERMS, term_help
from services.guidance_analytics import track_guidance_event
from services.next_best_action import NextBestAction, resolve_next_best_action
from services.portfolio_onboarding import (
    LAST_IMPORT_SUMMARY_KEY,
    PREFERENCES_CONFIGURED_KEY,
    VIEWED_DIVIDEND_DASHBOARD_KEY,
    VIEWED_UPCOMING_DIVIDENDS_KEY,
    build_guidance_context,
    record_import_guidance_summary,
)
from services.portfolio_session import is_demo_session, user_has_holdings_in_db
from ui.design_system import render_empty_state
from ui.session_keys import HELP_DRAWER_OPEN_KEY, HELP_DRAWER_SECTION_KEY

IMPORT_CAPABILITIES = (
    "Trades",
    "Deposits and withdrawals",
    "Dividends",
    "Withholding taxes",
    "Fees",
    "Corporate actions",
    "Positions, when available",
)

HELP_SECTIONS: tuple[tuple[str, str, str], ...] = (
    (
        "getting_started",
        "Getting started",
        "Open **Getting started — step-by-step guide** at the top of Home. "
        "Preferred path: sidebar **Manage portfolio** → **Import IBKR** → upload an "
        "Activity Statement CSV (AS_Fv2) → preview → **Apply import**. "
        "You can also add a ticker manually under **Add ticker**.",
    ),
    (
        "importing",
        "Importing broker data",
        "In IBKR, download an Activity Statement CSV (AS_Fv2). In DividendScope open "
        "**Manage portfolio** → **Import IBKR**. Upload the file, choose **Merge** "
        "(keep existing data) or **Full replace**, review positions/trades/dividends, "
        "then **Apply import**. Import oldest statements before newest when covering "
        "multiple periods.",
    ),
    (
        "dividends",
        "How dividends are calculated",
        "Received cash comes from broker dividend receipts. "
        "Estimated amounts use current holdings and market-library schedules. "
        "Net = gross − withholding when the broker reports both.",
    ),
    (
        "received_vs_estimated",
        "Received versus estimated dividends",
        "**Received** is completed broker cash. **Accrued** is recorded but not yet paid. "
        "**Estimated** is a projection. These stay separate — they are never summed into "
        "one unlabeled total.",
    ),
    (
        "taxes",
        "Understanding taxes",
        "Withholding tax is deducted by the broker or payment source. "
        "DividendScope shows gross and net when both are available. "
        "This is educational only — not tax advice.",
    ),
    (
        "reconciliation",
        "Data reconciliation",
        "After import, review warnings for unmatched rows or validation issues. "
        "Holdings come from open positions; dividends come from cash transactions. "
        "Fix source files or re-import when totals look incomplete.",
    ),
    (
        "faq",
        "Frequently asked questions",
        "Use the **Assistant** in the sidebar for common how-to questions. "
        "Open **About DividendScope** for data sources and disclaimers. "
        "Nothing here is investment advice or a guarantee of income.",
    ),
)


def mark_dividend_dashboard_viewed() -> None:
    st.session_state[VIEWED_DIVIDEND_DASHBOARD_KEY] = True
    track_guidance_event(
        "dividend_dashboard_opened",
        session=st.session_state,
    )


def mark_upcoming_dividends_viewed() -> None:
    st.session_state[VIEWED_UPCOMING_DIVIDENDS_KEY] = True
    track_guidance_event(
        "upcoming_dividends_opened",
        session=st.session_state,
    )


def mark_preferences_configured() -> None:
    st.session_state[PREFERENCES_CONFIGURED_KEY] = True


def open_help_drawer(section: str = "getting_started") -> None:
    st.session_state[HELP_DRAWER_OPEN_KEY] = True
    st.session_state[HELP_DRAWER_SECTION_KEY] = section
    track_guidance_event(
        "help_article_opened",
        session=st.session_state,
        properties={"section": section},
    )


def reopen_getting_started() -> None:
    from services.portfolio_onboarding import ONBOARDING_DISMISSED_KEY

    st.session_state[ONBOARDING_DISMISSED_KEY] = False
    st.session_state["portfolio_onboarding_force_expand"] = True


def navigate_guidance_route(route: str) -> None:
    """Map guidance routes onto Streamlit section / panel actions."""
    route = (route or "").strip()
    if route.startswith("help:"):
        open_help_drawer(route.split(":", 1)[1] or "getting_started")
        st.rerun()
        return

    if route in {"manage", "manage:import", "manage:import_issues"}:
        st.session_state["portfolio_onboarding_show_manage_tip"] = True
        st.session_state["portfolio_manage_expand"] = True
        if route.endswith("import") or route.endswith("import_issues"):
            st.session_state["portfolio_manage_focus_import"] = True
        if route.endswith("import_issues"):
            track_guidance_event("reconciliation_opened", session=st.session_state)
        from ui.portfolio_home import navigate_to_portfolio_home

        navigate_to_portfolio_home()
        return

    if route == "preferences":
        st.session_state["background_tasks_expand"] = True
        mark_preferences_configured()
        from ui.portfolio_home import navigate_to_portfolio_home

        navigate_to_portfolio_home()
        return

    section = {
        "dashboard": "dashboard",
        "dividends": "dividends",
        "holdings": "holdings",
        "journal": "journal",
        "deposits": "deposits",
    }.get(route, "dashboard")
    from ui.portfolio_home import navigate_to_portfolio_section

    navigate_to_portfolio_section(section)


def render_actionable_empty_state(
    *,
    title: str,
    description: str,
    icon: str = "📊",
    primary_action_label: str | None = None,
    primary_action_route: str | None = None,
    secondary_action_label: str | None = None,
    secondary_action_route: str | None = None,
    key_prefix: str = "empty",
) -> None:
    render_empty_state(title, description, icon=icon)
    cols = st.columns(2 if secondary_action_label and secondary_action_route else 1)
    if primary_action_label and primary_action_route:
        with cols[0]:
            if st.button(
                primary_action_label,
                key=f"{key_prefix}_primary",
                type="primary",
                use_container_width=True,
            ):
                navigate_guidance_route(primary_action_route)
    if secondary_action_label and secondary_action_route and len(cols) > 1:
        with cols[1]:
            if st.button(
                secondary_action_label,
                key=f"{key_prefix}_secondary",
                use_container_width=True,
            ):
                navigate_guidance_route(secondary_action_route)


def render_dividend_term_tooltip(term_id: str, *, label: str | None = None) -> None:
    """Accessible term definition via Streamlit help / expander."""
    text = term_help(term_id)
    if not text:
        return
    shown = label or DIVIDEND_TERM_LABELS.get(term_id, term_id)
    st.caption(f"**{shown}** — {text}")


def render_dividend_terms_help(*, expanded: bool = False) -> None:
    with st.expander("Dividend terms", expanded=expanded):
        for term_id, definition in DIVIDEND_TERMS.items():
            st.markdown(f"**{DIVIDEND_TERM_LABELS[term_id]}** — {definition}")


def portfolio_has_broker_data() -> bool:
    summary = st.session_state.get(LAST_IMPORT_SUMMARY_KEY) or {}
    if isinstance(summary, dict) and (
        summary.get("successful") or int(summary.get("imported_records") or 0) > 0
    ):
        return True
    try:
        from services.portfolio_context import create_portfolio_context

        ctx = create_portfolio_context()
        purchases = ctx.journal.list_purchases()
        if any(getattr(row, "source", "") in ("ibkr", "ibkr-open") for row in purchases):
            return True
        totals = ctx.receipts.yearly_net_totals()
        return any(abs(float(value or 0.0)) > 0 for value in totals.values())
    except Exception:  # noqa: BLE001
        return False


def portfolio_has_dividend_transactions() -> bool:
    try:
        from services.portfolio_context import create_portfolio_context

        ctx = create_portfolio_context()
        totals = ctx.receipts.yearly_net_totals()
        return any(abs(float(value or 0.0)) > 0 for value in totals.values())
    except Exception:  # noqa: BLE001
        return False


def portfolio_has_upcoming_dividends() -> bool:
    summary = st.session_state.get("portfolio_attention_summary")
    if isinstance(summary, dict):
        return int(summary.get("dividend_total") or 0) > 0
    if summary is not None:
        return int(getattr(summary, "dividend_total", 0) or 0) > 0
    return False


def resolve_dashboard_next_best_action() -> NextBestAction | None:
    if is_demo_session():
        return None
    has_broker = portfolio_has_broker_data()
    context = build_guidance_context(
        has_portfolio=user_has_holdings_in_db(),
        has_dividend_transactions=portfolio_has_dividend_transactions(),
        has_upcoming_dividends=portfolio_has_upcoming_dividends(),
        session=st.session_state,
        has_successful_import=has_broker,
    )
    return resolve_next_best_action(context)


def render_next_best_action_card(*, key_prefix: str = "nba") -> None:
    action = resolve_dashboard_next_best_action()
    if action is None:
        return

    if st.session_state.get("_nba_tracked_id") != action.id:
        st.session_state["_nba_tracked_id"] = action.id
        track_guidance_event(
            "next_best_action_viewed",
            session=st.session_state,
            properties={"action_id": action.id, "severity": action.severity},
        )

    from ui.design_system import render_action_card

    kicker = {
        "error": "Needs attention",
        "warning": "Review recommended",
        "info": "Next step",
    }.get(action.severity, "Next step")
    render_action_card(action.title, action.description, kicker=kicker)
    cols = st.columns(2 if action.secondary_action_label else 1)
    with cols[0]:
        if st.button(
            action.primary_action_label,
            key=f"{key_prefix}_primary",
            type="primary",
            use_container_width=True,
        ):
            track_guidance_event(
                "next_best_action_clicked",
                session=st.session_state,
                properties={"action_id": action.id, "which": "primary"},
            )
            navigate_guidance_route(action.primary_action_route)
    if action.secondary_action_label and action.secondary_action_route and len(cols) > 1:
        with cols[1]:
            if st.button(
                action.secondary_action_label,
                key=f"{key_prefix}_secondary",
                use_container_width=True,
            ):
                track_guidance_event(
                    "next_best_action_clicked",
                    session=st.session_state,
                    properties={"action_id": action.id, "which": "secondary"},
                )
                navigate_guidance_route(action.secondary_action_route)


def render_help_drawer(*, force_open: bool | None = None) -> None:
    """Lightweight help panel — expander on main page or when opened from nav."""
    open_flag = (
        bool(st.session_state.get(HELP_DRAWER_OPEN_KEY)) if force_open is None else force_open
    )
    preferred = st.session_state.get(HELP_DRAWER_SECTION_KEY) or "getting_started"
    with st.expander("Help & guidance", expanded=open_flag):
        section_ids = [item[0] for item in HELP_SECTIONS]
        labels = [item[1] for item in HELP_SECTIONS]
        try:
            index = section_ids.index(str(preferred))
        except ValueError:
            index = 0
        choice = st.selectbox(
            "Topic",
            options=labels,
            index=index,
            key="help_drawer_topic",
            label_visibility="collapsed",
        )
        selected = HELP_SECTIONS[labels.index(choice)]
        st.markdown(f"### {selected[1]}")
        st.write(selected[2])
        if st.session_state.get("_help_tracked_section") != selected[0]:
            st.session_state["_help_tracked_section"] = selected[0]
            track_guidance_event(
                "help_article_opened",
                session=st.session_state,
                properties={"section": selected[0]},
            )
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Getting started checklist", key="help_reopen_checklist"):
                reopen_getting_started()
                st.rerun()
        with c2:
            if st.button("Dividend income", key="help_goto_dividends"):
                navigate_guidance_route("dividends")
        with c3:
            if st.button("Manage portfolio", key="help_goto_manage"):
                navigate_guidance_route("manage")
        render_dividend_terms_help(expanded=False)
        if st.button("Close help", key="help_drawer_close"):
            st.session_state[HELP_DRAWER_OPEN_KEY] = False
            st.rerun()


def render_import_capabilities_caption() -> None:
    st.caption("This import can include: " + "; ".join(IMPORT_CAPABILITIES) + ".")


def render_import_result_guidance(summary: dict[str, Any]) -> None:
    """Post-import result panel with optional Review issues action."""
    st.markdown("##### Import result")
    st.markdown(
        f"- **Imported records:** {summary.get('imported_records', 0)}\n"
        f"- **Skipped duplicates:** {summary.get('skipped_duplicates', 0)}\n"
        f"- **Updated records:** {summary.get('updated_records', 0)}\n"
        f"- **Records with warnings:** {summary.get('warning_count', 0)}\n"
        f"- **Date range:** {summary.get('date_range') or '—'}\n"
        f"- **Broker account:** {summary.get('broker_account_masked') or '—'}\n"
        f"- **Currencies found:** {', '.join(summary.get('currencies') or []) or '—'}"
    )
    needs_review = (
        int(summary.get("warning_count") or 0) > 0
        or int(summary.get("blocking_error_count") or 0) > 0
        or str(summary.get("reconciliation_status") or "") not in ("SUCCESS", "UNKNOWN", "")
    )
    if needs_review:
        render_actionable_empty_state(
            title="Some records need attention",
            description=(
                "Your import was saved, but some transactions could not be matched " "or validated."
            ),
            icon="⚠️",
            primary_action_label="Review import issues",
            primary_action_route="manage:import_issues",
            secondary_action_label="How reconciliation works",
            secondary_action_route="help:reconciliation",
            key_prefix="import_warnings",
        )


def persist_import_apply_guidance(
    *,
    successful: bool,
    failed: bool,
    imported_records: int,
    skipped_duplicates: int,
    updated_records: int,
    warning_count: int,
    blocking_error_count: int,
    reconciliation_status: str,
    date_range: str | None = None,
    currencies: list[str] | None = None,
    broker_account_masked: str | None = None,
) -> dict[str, Any]:
    record_import_guidance_summary(
        st.session_state,
        successful=successful,
        failed=failed,
        imported_records=imported_records,
        skipped_duplicates=skipped_duplicates,
        updated_records=updated_records,
        warning_count=warning_count,
        blocking_error_count=blocking_error_count,
        reconciliation_status=reconciliation_status,
        date_range=date_range,
        currencies=currencies,
        broker_account_masked=broker_account_masked,
    )
    summary = dict(st.session_state.get(LAST_IMPORT_SUMMARY_KEY) or {})
    if successful:
        track_guidance_event(
            "broker_import_completed",
            session=st.session_state,
            properties={
                "imported_records": imported_records,
                "warning_count": warning_count,
                "blocking_error_count": blocking_error_count,
            },
        )
    if failed:
        track_guidance_event(
            "broker_import_failed",
            session=st.session_state,
            properties={"blocking_error_count": blocking_error_count},
        )
    return summary
