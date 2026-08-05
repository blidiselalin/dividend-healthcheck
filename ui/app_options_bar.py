"""
Top-right app options — account, help, theme, and admin.

Also mirrored as a short Account & admin block in the sidebar so controls
stay discoverable if the top-right popover is easy to miss.
"""

from __future__ import annotations

import streamlit as st

from auth.settings import auth_required
from auth.test_user import is_test_user, sign_out_test_user, test_user_session_active
from auth.user_context import (
    clear_portfolio_session_state,
    current_user,
    is_app_admin,
)
from ui.design_system import render_html

_OPTIONS_BAR_CSS = """
<style>
[class*="st-key-ds_options_bar"] {
  margin: 0 0 0.5rem 0 !important;
  padding: 0 !important;
}
[class*="st-key-ds_options_bar"] [data-testid="stPopover"] {
  display: flex !important;
  justify-content: flex-end !important;
  width: 100% !important;
}
[class*="st-key-ds_options_bar"] [data-testid="stPopover"] > button {
  border-radius: 999px !important;
  font-weight: 650 !important;
  white-space: nowrap !important;
  min-height: 2.45rem !important;
}
</style>
"""


def _account_label() -> str:
    user = current_user()
    if user is None:
        return "Account"
    short = (user.name or user.email.split("@")[0] or "Account").strip()
    if len(short) > 18:
        short = short[:17] + "…"
    return f"Account · {short}"


def _render_options_body(*, key_prefix: str) -> None:
    st.caption("Account, appearance, help, and admin")
    from ui.theme_mode import (
        THEME_LABELS,
        get_theme_mode,
        normalize_theme,
        set_theme_mode,
        theme_label,
    )

    st.markdown("**Appearance**")
    current = get_theme_mode()
    choice = st.segmented_control(
        "Theme",
        options=list(THEME_LABELS),
        default=theme_label(current),
        key=f"{key_prefix}_theme_toggle",
        label_visibility="collapsed",
        help="Switch between dark and light appearance",
    )
    selected = normalize_theme(str(choice).lower() if choice else current)
    if selected != current:
        set_theme_mode(selected)
        st.rerun()

    st.divider()
    st.markdown("**Help**")
    if st.button(
        "Help & guidance",
        key=f"{key_prefix}_help_open",
        use_container_width=True,
    ):
        from ui.user_guidance import open_help_drawer

        open_help_drawer("getting_started")
        st.rerun()
    if st.button(
        "Reopen getting started",
        key=f"{key_prefix}_reopen_getting_started",
        use_container_width=True,
    ):
        from ui.user_guidance import reopen_getting_started

        reopen_getting_started()
        st.rerun()

    st.divider()
    from ui.auth_account_panel import render_account_options

    render_account_options(key_prefix=key_prefix)

    if is_app_admin():
        st.divider()
        from ui.admin_page import render_admin_options_entry

        render_admin_options_entry(key_prefix=key_prefix)


def render_app_options_bar() -> None:
    """Visible Account control at the top-right of the main panel."""
    render_html(_OPTIONS_BAR_CSS)

    with st.container(key="ds_options_bar"):
        _left, right = st.columns([3.0, 1.5], gap="small")
        with right, st.popover(_account_label(), use_container_width=True):
            _render_options_body(key_prefix="options_main")


def render_sidebar_account_entry() -> None:
    """Always-visible sidebar shortcuts for account / admin / help."""
    from ui.theme import sidebar_heading

    st.sidebar.divider()
    sidebar_heading("Account & admin")
    st.sidebar.caption("Full menu: **Account** button at the top right.")

    user = current_user()
    if user is not None:
        st.sidebar.markdown(f"**{user.name or user.email.split('@')[0]}**")
        st.sidebar.caption(user.email)

    if st.sidebar.button(
        "Help & guidance",
        key="sidebar_account_help",
        use_container_width=True,
    ):
        from ui.user_guidance import open_help_drawer

        open_help_drawer("getting_started")
        st.rerun()

    if is_app_admin():
        from ui.admin_page import is_admin_console_active, set_admin_console_active

        if is_admin_console_active():
            if st.sidebar.button(
                "Back to Home",
                key="sidebar_admin_console_back",
                use_container_width=True,
            ):
                from ui.portfolio_home import navigate_to_portfolio_home

                navigate_to_portfolio_home()
        elif st.sidebar.button(
            "Open admin console",
            key="sidebar_admin_console_open",
            type="primary",
            use_container_width=True,
        ):
            set_admin_console_active(True)
            st.rerun()

    if user is not None:
        if test_user_session_active() and is_test_user(user):
            if st.sidebar.button(
                "Exit test user",
                key="sidebar_exit_test_user",
                use_container_width=True,
            ):
                sign_out_test_user()
                st.rerun()
        elif auth_required() and st.sidebar.button(
            "Sign out",
            key="sidebar_sign_out",
            use_container_width=True,
        ):
            clear_portfolio_session_state()
            st.logout()
