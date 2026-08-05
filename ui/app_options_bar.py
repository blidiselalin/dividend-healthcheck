"""
Top-right app options — account, help, theme, and admin.

Keeps user/admin controls out of the portfolio workflow sidebar.
"""

from __future__ import annotations

import streamlit as st

from auth.user_context import current_user, is_app_admin


def render_app_options_bar() -> None:
    """Compact options control aligned to the right of the main panel."""
    user = current_user()
    label = "Options"
    if user is not None:
        short = (user.name or user.email.split("@")[0] or "Account").strip()
        if len(short) > 18:
            short = short[:17] + "…"
        label = f"Options · {short}"

    _spacer, opts = st.columns([3.4, 1.6], gap="small")
    with opts, st.popover(label, use_container_width=True):
        st.caption("Account, appearance, help, and admin")
        from ui.theme_mode import render_theme_toggle

        st.markdown("**Appearance**")
        render_theme_toggle(sidebar=False)

        st.divider()
        st.markdown("**Help**")
        if st.button("Help & guidance", key="options_help_open", use_container_width=True):
            from ui.user_guidance import open_help_drawer

            open_help_drawer("getting_started")
            st.rerun()
        if st.button(
            "Reopen getting started",
            key="options_reopen_getting_started",
            use_container_width=True,
        ):
            from ui.user_guidance import reopen_getting_started

            reopen_getting_started()
            st.rerun()

        st.divider()
        from ui.auth_account_panel import render_account_options

        render_account_options()

        if is_app_admin():
            st.divider()
            from ui.admin_page import render_admin_options_entry

            render_admin_options_entry()
