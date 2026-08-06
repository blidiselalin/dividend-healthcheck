"""
Account / admin control pinned to the Streamlit app header (under the ⋮ menu).
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

# Pin beside Streamlit's header toolbar (⋮). Collapse the in-page footprint so the
# control does not appear under Home / portfolio snapshot content.
_OPTIONS_BAR_CSS = """
<style>
header[data-testid="stHeader"] {
  z-index: 999990 !important;
  background: transparent !important;
}
/* Remove the empty vertical slot left in the main column */
div[data-testid="stElementContainer"]:has([class*="st-key-ds_options_bar"]),
div[data-testid="stVerticalBlockBorderWrapper"]:has([class*="st-key-ds_options_bar"]),
div[data-testid="stVerticalBlock"]:has(> div > [class*="st-key-ds_options_bar"]) {
  height: 0 !important;
  min-height: 0 !important;
  max-height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  border: none !important;
  overflow: visible !important;
}
[class*="st-key-ds_options_bar"] {
  position: fixed !important;
  top: 0.35rem !important;
  right: 3.6rem !important; /* sit just left of Streamlit's ⋮ menu */
  left: auto !important;
  width: auto !important;
  max-width: min(260px, 55vw) !important;
  margin: 0 !important;
  padding: 0 !important;
  z-index: 1000005 !important;
  background: transparent !important;
}
[class*="st-key-ds_options_bar"] [data-testid="stPopover"] {
  width: auto !important;
}
[class*="st-key-ds_options_bar"] [data-testid="stPopover"] > button {
  border-radius: 999px !important;
  font-weight: 650 !important;
  white-space: nowrap !important;
  min-height: 2.15rem !important;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.22) !important;
  background: var(--ds-surface-elevated, #1e293b) !important;
  border: 1px solid var(--ds-border, rgba(148, 163, 184, 0.35)) !important;
  color: var(--ds-text, #e2e8f0) !important;
}
@media (max-width: 640px) {
  [class*="st-key-ds_options_bar"] {
    right: 3.1rem !important;
    max-width: 46vw !important;
  }
  [class*="st-key-ds_options_bar"] [data-testid="stPopover"] > button {
    font-size: 0.82rem !important;
    padding-left: 0.65rem !important;
    padding-right: 0.65rem !important;
  }
}
</style>
"""


def _pending_access_count() -> int:
    if not is_app_admin():
        return 0
    from auth.access_requests import pending_access_request_count

    return pending_access_request_count()


def _account_label() -> str:
    user = current_user()
    if user is None:
        return "Account"
    if test_user_session_active() and is_test_user(user):
        return "Account · Demo"
    short = (user.name or user.email.split("@")[0] or "Account").strip()
    if len(short) > 14:
        short = short[:13] + "…"
    pending = _pending_access_count()
    if pending:
        return f"Account · {short} · {pending} request{'s' if pending != 1 else ''}"
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

    from ui.admin_page import (
        is_admin_console_active,
        render_admin_options_entry,
        set_admin_console_active,
    )

    if is_app_admin():
        st.divider()
        render_admin_options_entry(key_prefix=key_prefix)
    elif is_admin_console_active():
        set_admin_console_active(False)


def render_app_options_bar() -> None:
    """Pin Account control under the Streamlit header, left of the ⋮ menu."""
    # Global CSS must go through markdown — st.html can scope/strip page styles.
    st.markdown(_OPTIONS_BAR_CSS, unsafe_allow_html=True)

    with st.container(key="ds_options_bar"), st.popover(_account_label()):
        _render_options_body(key_prefix="options_main")


def render_sidebar_account_entry() -> None:
    """Sidebar shortcuts for account / admin / help."""
    from ui.theme import sidebar_heading

    st.sidebar.divider()
    admin = is_app_admin()
    sidebar_heading("Account & admin" if admin else "Account")
    st.sidebar.caption("Full menu: **Account** beside the Streamlit ⋮ menu (top right).")

    user = current_user()
    demo = bool(user and test_user_session_active() and is_test_user(user))
    if user is not None:
        if demo:
            st.sidebar.markdown("**Demo portfolio**")
            st.sidebar.caption("Sample holdings — no personal email shown.")
        else:
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

    from ui.admin_page import is_admin_console_active, set_admin_console_active

    if not admin:
        if is_admin_console_active():
            set_admin_console_active(False)
    else:
        from ui.access_request_panel import render_admin_access_requests

        # Pending invites must be visible without opening the Account popover.
        render_admin_access_requests(in_sidebar=True, key_prefix="sidebar")

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
        if demo:
            if st.sidebar.button(
                "Exit demo",
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
