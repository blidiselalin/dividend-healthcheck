"""
Streamlit onboarding checklist for new portfolio users.
"""

from __future__ import annotations

import streamlit as st

from services.guidance_analytics import track_guidance_event
from services.portfolio_onboarding import (
    ONBOARDING_DISMISSED_KEY,
    StepStatus,
    checklist_states,
    completed_step_count,
    current_sidebar_hint,
    should_show_onboarding,
    step_progress,
)
from services.portfolio_session import is_demo_session, user_has_holdings_in_db
from ui.theme import PORTFOLIO_NAV, render_notice
from ui.user_guidance import (
    mark_preferences_configured,
    navigate_guidance_route,
    resolve_dashboard_next_best_action,
)


def _render_workspace_overview() -> None:
    """What each main section contains — matches Home section buttons and README."""
    st.markdown("##### What's in your workspace")
    lines = [f"- **{label}** — {hint}" for label, _key, hint in PORTFOLIO_NAV]
    st.markdown("\n".join(lines))
    st.caption(
        "Expand **What is DividendScope?** on Home for purpose, data sources, and how analysis helps."
    )


def _render_ibkr_import_howto() -> None:
    """Explicit IBKR import walkthrough inside Getting started."""
    from ui.user_guidance import IMPORT_CAPABILITIES

    st.markdown("##### How to import from Interactive Brokers")
    st.markdown(
        """
1. In IBKR Portal / Client Portal, download an **Activity Statement** CSV (**AS_Fv2**).
2. Open the sidebar → **Manage portfolio** → **Import IBKR**.
3. Upload the CSV, choose **Merge** (keep existing data) or **Full replace**.
4. Review the preview (positions, trades, dividends, deposits) and any warnings.
5. Click **Apply import** — Home refreshes from the shared library in the background.
        """.strip()
    )
    st.caption("This import can include: " + "; ".join(IMPORT_CAPABILITIES) + ".")
    if st.button(
        "Open Import IBKR",
        key="onboarding_open_ibkr_import",
        type="primary",
        use_container_width=True,
    ):
        track_guidance_event(
            "getting_started_step_clicked",
            session=st.session_state,
            properties={"step_id": "IMPORT_DATA", "which": "ibkr_howto"},
        )
        navigate_guidance_route("manage:import")


def _status_icon(status: StepStatus) -> str:
    if status == StepStatus.COMPLETED:
        return "✅"
    if status == StepStatus.NEEDS_ATTENTION:
        return "⚠️"
    if status == StepStatus.IN_PROGRESS:
        return "▶️"
    return "⬜"


def _guidance_counts() -> tuple[bool, bool, bool]:
    """Best-effort derived flags for checklist completion."""
    from ui.user_guidance import (
        portfolio_has_broker_data,
        portfolio_has_dividend_transactions,
        portfolio_has_upcoming_dividends,
    )

    return (
        portfolio_has_broker_data(),
        portfolio_has_dividend_transactions(),
        portfolio_has_upcoming_dividends(),
    )


def mark_onboarding_live_reload_requested() -> None:
    """Call when the user clicks Reload live data during onboarding."""
    st.session_state["portfolio_onboarding_live_reload"] = True


def dismiss_onboarding() -> None:
    st.session_state[ONBOARDING_DISMISSED_KEY] = True
    track_guidance_event("getting_started_dismissed", session=st.session_state)


def render_onboarding_sidebar_hint() -> None:
    """Compact next-step hint under the Portfolio sidebar heading."""
    if is_demo_session():
        return
    has_broker, has_divs, has_upcoming = _guidance_counts()
    hint = current_sidebar_hint(
        has_holdings=user_has_holdings_in_db(),
        session=st.session_state,
        is_demo=False,
        has_dividend_transactions=has_divs,
        has_upcoming_dividends=has_upcoming,
        has_successful_import=has_broker,
    )
    if not hint:
        return
    st.sidebar.markdown(
        f'<p class="ds-onboarding-sidebar-hint"><strong>Next step:</strong> {hint}</p>',
        unsafe_allow_html=True,
    )


def render_onboarding_checklist(*, expanded: bool | None = None) -> None:
    """Step-by-step guide for real users (empty or partially set-up portfolio)."""
    if is_demo_session():
        return

    force = bool(st.session_state.pop("portfolio_onboarding_force_expand", False))
    has_broker, has_divs, has_upcoming = _guidance_counts()
    show = should_show_onboarding(
        has_holdings=user_has_holdings_in_db(),
        session=st.session_state,
        is_demo=False,
        has_dividend_transactions=has_divs,
        has_upcoming_dividends=has_upcoming,
        has_successful_import=has_broker,
    )
    if not show and not force:
        return

    has_holdings = user_has_holdings_in_db()
    states = checklist_states(
        has_holdings=has_holdings,
        session=st.session_state,
        is_demo=False,
        has_dividend_transactions=has_divs,
        has_upcoming_dividends=has_upcoming,
        has_successful_import=has_broker,
    )
    done_count, total = completed_step_count(
        has_holdings=has_holdings,
        session=st.session_state,
        is_demo=False,
        has_dividend_transactions=has_divs,
        has_upcoming_dividends=has_upcoming,
        has_successful_import=has_broker,
    )

    expand = force if expanded is None else expanded
    if expanded is None and not force:
        expand = done_count < total

    track_guidance_event("getting_started_viewed", session=st.session_state)

    with st.expander("Getting started — step-by-step guide", expanded=expand):
        st.caption(
            "Your portfolio is private in PostgreSQL. Market history comes from the "
            "shared S&P library. Heavy work runs in **Background tasks** so the UI stays responsive. "
            "The fastest path is **Import IBKR** below."
        )
        _render_ibkr_import_howto()
        st.divider()
        _render_workspace_overview()
        st.progress(
            done_count / total if total else 0.0, text=f"{done_count} of {total} steps done"
        )

        for state in states:
            icon = _status_icon(state.status)
            required = "" if state.is_required else " _(optional)_"
            st.markdown(f"{icon} **{state.title}**{required}")
            if state.status != StepStatus.COMPLETED:
                st.markdown(state.description)
                can_act = bool(state.action_label and state.action_route)
                if can_act and st.button(
                    state.action_label,
                    key=f"onboarding_step_{state.id}",
                ):
                    track_guidance_event(
                        "getting_started_step_clicked",
                        session=st.session_state,
                        properties={"step_id": state.id},
                    )
                    if state.action_route == "preferences":
                        mark_preferences_configured()
                    navigate_guidance_route(state.action_route)

        st.markdown("##### Optional next")
        st.markdown(
            """
            - **Purchase** tab — log buy dates for cost-basis history
            - **Monthly evolution** tab — record deposits and end-of-month portfolio value (€)
            - **Assistant** in the sidebar — FAQ and app help
            - **S&P research** picker on Home — analyze a symbol before you buy
            """
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Got it — hide guide", key="portfolio_onboarding_dismiss"):
                dismiss_onboarding()
                st.rerun()
        with c2:
            if st.button("Open Manage portfolio tips", key="portfolio_onboarding_manage_tip"):
                st.session_state["portfolio_onboarding_show_manage_tip"] = True
                st.rerun()
        with c3:
            if st.button("Open help", key="portfolio_onboarding_open_help"):
                from ui.user_guidance import open_help_drawer

                open_help_drawer("getting_started")
                st.rerun()


def render_demo_onboarding_checklist(*, expanded: bool = True) -> None:
    """Shorter checklist for test/demo mode."""
    if not is_demo_session():
        return
    if st.session_state.get(ONBOARDING_DISMISSED_KEY):
        return

    progress = step_progress(
        has_holdings=user_has_holdings_in_db(),
        session=st.session_state,
        is_demo=True,
    )
    done_count, total = completed_step_count(
        has_holdings=user_has_holdings_in_db(),
        session=st.session_state,
        is_demo=True,
    )
    if done_count >= total:
        return

    with st.expander("Test mode — quick tour", expanded=expanded):
        st.progress(
            done_count / total if total else 0.0, text=f"{done_count} of {total} steps done"
        )
        for step, complete in progress:
            icon = "✅" if complete else "⬜"
            st.markdown(f"{icon} **{step.title}**")
            if not complete:
                st.markdown(step.detail)
        if st.button("Hide tour", key="portfolio_onboarding_dismiss_demo"):
            dismiss_onboarding()
            st.rerun()


def render_real_user_getting_started() -> None:
    """Welcome panel when the portfolio snapshot is not ready yet.

    Checklist / next-best action already render at the top of Home — keep this
    panel focused on empty-state actions and load prompts.
    """
    st.markdown("### Welcome to DividendScope")
    st.write(
        "Track dividend holdings, income, and risk in one workspace. "
        "Start with **Import IBKR** in the Getting started guide above, "
        "or add a ticker manually from **Manage portfolio**."
    )
    with st.expander("What is DividendScope?", expanded=False):
        from ui.app_about import render_about_body

        render_about_body()

    from ui.user_guidance import render_actionable_empty_state

    if not user_has_holdings_in_db():
        render_actionable_empty_state(
            title="Add your first portfolio",
            description=(
                "Import an Interactive Brokers activity statement (recommended) "
                "or add a ticker manually to calculate holdings and dividend income."
            ),
            icon="📁",
            primary_action_label="Import from IBKR",
            primary_action_route="manage:import",
            secondary_action_label="Add ticker manually",
            secondary_action_route="manage",
            key_prefix="empty_home_portfolio",
        )
        render_notice(
            "<strong>Tip:</strong> In the sidebar open **Manage portfolio** → "
            "**Import IBKR**, upload an Activity Statement CSV (AS_Fv2), preview, "
            "then **Apply import**.",
            kind="info",
        )
    elif not st.session_state.get("portfolio_details_rows"):
        from ui.portfolio_load_prompt import render_portfolio_load_prompt

        render_portfolio_load_prompt(key_prefix="onboarding_home")


def render_onboarding_banner_if_needed() -> None:
    """Compact reminder on Home when the user has rows but has not finished onboarding."""
    if is_demo_session():
        return
    has_broker, has_divs, has_upcoming = _guidance_counts()
    if not should_show_onboarding(
        has_holdings=user_has_holdings_in_db(),
        session=st.session_state,
        is_demo=False,
        has_dividend_transactions=has_divs,
        has_upcoming_dividends=has_upcoming,
        has_successful_import=has_broker,
    ):
        return
    if not st.session_state.get("portfolio_details_rows"):
        return

    action = resolve_dashboard_next_best_action()
    if action is not None:
        render_notice(
            f"<strong>Next:</strong> {action.title}",
            kind="info",
        )
        return

    done_count, total = completed_step_count(
        has_holdings=user_has_holdings_in_db(),
        session=st.session_state,
        is_demo=False,
        has_dividend_transactions=has_divs,
        has_upcoming_dividends=has_upcoming,
        has_successful_import=has_broker,
    )
    remaining = [
        step.title
        for step, done in step_progress(
            has_holdings=user_has_holdings_in_db(),
            session=st.session_state,
            is_demo=False,
            has_dividend_transactions=has_divs,
            has_upcoming_dividends=has_upcoming,
            has_successful_import=has_broker,
        )
        if not done
    ]
    if not remaining:
        return

    render_notice(
        f"<strong>Setup {done_count}/{total}:</strong> Next — {remaining[0]}. "
        "Open the **Getting started** guide below for details.",
        kind="info",
    )
