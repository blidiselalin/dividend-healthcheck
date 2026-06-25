"""
Streamlit onboarding checklist for new portfolio users.
"""

from __future__ import annotations

import streamlit as st

from services.portfolio_onboarding import (
    ONBOARDING_DISMISSED_KEY,
    completed_step_count,
    current_sidebar_hint,
    should_show_onboarding,
    step_progress,
)
from services.portfolio_session import is_demo_session, user_has_holdings_in_db
from ui.theme import PORTFOLIO_NAV, render_notice


def _render_workspace_overview() -> None:
    """What each main section contains — matches Home section buttons and README."""
    st.markdown("##### What's in your workspace")
    lines = [f"- **{label}** — {hint}" for label, _key, hint in PORTFOLIO_NAV]
    st.markdown("\n".join(lines))
    st.caption(
        "Expand **What is DividendScope?** on Home for purpose, data sources, and how analysis helps."
    )


def mark_onboarding_live_reload_requested() -> None:
    """Call when the user clicks Reload live data during onboarding."""
    st.session_state["portfolio_onboarding_live_reload"] = True


def dismiss_onboarding() -> None:
    st.session_state[ONBOARDING_DISMISSED_KEY] = True


def render_onboarding_sidebar_hint() -> None:
    """Compact next-step hint under the Portfolio sidebar heading."""
    if is_demo_session():
        return
    hint = current_sidebar_hint(
        has_holdings=user_has_holdings_in_db(),
        session=st.session_state,
        is_demo=False,
    )
    if not hint:
        return
    st.sidebar.markdown(
        f'<p class="ds-onboarding-sidebar-hint"><strong>Next step:</strong> {hint}</p>',
        unsafe_allow_html=True,
    )


def render_onboarding_checklist(*, expanded: bool = True) -> None:
    """Step-by-step guide for real users (empty or partially set-up portfolio)."""
    if is_demo_session():
        return
    if not should_show_onboarding(
        has_holdings=user_has_holdings_in_db(),
        session=st.session_state,
        is_demo=False,
    ):
        return

    has_holdings = user_has_holdings_in_db()
    progress = step_progress(
        has_holdings=has_holdings,
        session=st.session_state,
        is_demo=False,
    )
    done_count, total = completed_step_count(
        has_holdings=has_holdings,
        session=st.session_state,
        is_demo=False,
    )

    with st.expander("Getting started — step-by-step guide", expanded=expanded):
        st.caption(
            "Your portfolio is private in PostgreSQL. Market history comes from the "
            "shared S&P library. Heavy work runs in **Background tasks** so the UI stays responsive."
        )
        _render_workspace_overview()
        st.progress(done_count / total if total else 0.0, text=f"{done_count} of {total} steps done")

        for step, complete in progress:
            icon = "✅" if complete else "⬜"
            st.markdown(f"{icon} **{step.title}**")
            if not complete:
                st.markdown(step.detail)

        st.markdown("##### Optional next")
        st.markdown(
            """
            - **Purchase** tab — log buy dates for cost-basis history
            - **Monthly evolution** tab — record deposits and end-of-month portfolio value (€)
            - **Assistant** in the sidebar — FAQ and app help
            - **S&P research** picker on Home — analyze a symbol before you buy
            """
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Got it — hide guide", key="portfolio_onboarding_dismiss"):
                dismiss_onboarding()
                st.rerun()
        with c2:
            if st.button("Open Manage portfolio tips", key="portfolio_onboarding_manage_tip"):
                st.session_state["portfolio_onboarding_show_manage_tip"] = True
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
        st.progress(done_count / total if total else 0.0, text=f"{done_count} of {total} steps done")
        for step, complete in progress:
            icon = "✅" if complete else "⬜"
            st.markdown(f"{icon} **{step.title}**")
            if not complete:
                st.markdown(step.detail)
        if st.button("Hide tour", key="portfolio_onboarding_dismiss_demo"):
            dismiss_onboarding()
            st.rerun()


def render_real_user_getting_started() -> None:
    """Welcome panel when the portfolio snapshot is not ready yet."""
    st.markdown("### Welcome to DividendScope")
    st.write(
        "Track dividend holdings, income, and risk in one workspace. "
        "Follow the guide below — each step matches how the app loads data in the background."
    )
    with st.expander("What is DividendScope?", expanded=False):
        from ui.app_about import render_about_body

        render_about_body()
    render_onboarding_checklist(expanded=True)

    if not user_has_holdings_in_db():
        render_notice(
            "<strong>Tip:</strong> **Manage portfolio** in the sidebar is expanded automatically "
            "until you add your first ticker.",
            kind="info",
        )
    elif not st.session_state.get("portfolio_details_rows"):
        render_notice(
            "<strong>Loading:</strong> Your holding was saved. Watch **Background tasks** in the "
            "sidebar — Home will populate when the portfolio job finishes.",
            kind="info",
        )


def render_onboarding_banner_if_needed() -> None:
    """Compact reminder on Home when the user has rows but has not finished onboarding."""
    if is_demo_session():
        return
    if not should_show_onboarding(
        has_holdings=user_has_holdings_in_db(),
        session=st.session_state,
        is_demo=False,
    ):
        return
    if not st.session_state.get("portfolio_details_rows"):
        return

    done_count, total = completed_step_count(
        has_holdings=user_has_holdings_in_db(),
        session=st.session_state,
        is_demo=False,
    )
    remaining = [step.title for step, done in step_progress(
        has_holdings=user_has_holdings_in_db(),
        session=st.session_state,
        is_demo=False,
    ) if not done]
    if not remaining:
        return

    render_notice(
        f"<strong>Setup {done_count}/{total}:</strong> Next — {remaining[0]}. "
        "Open the **Getting started** guide below for details.",
        kind="info",
    )
