"""
Top-right app options — account, help, theme, and admin.

Pinned to the main-panel corner so it stays out of the portfolio workflow.
"""

from __future__ import annotations

import streamlit as st

from auth.user_context import current_user, is_app_admin
from ui.design_system import render_html

_OPTIONS_BAR_CSS = """
<style>
/* Pin Options / user menu to the top-right of the main panel */
[class*="st-key-ds_options_bar"] {
  position: fixed !important;
  top: 0.4rem !important;
  right: 0.85rem !important;
  left: auto !important;
  width: min(250px, 48vw) !important;
  margin: 0 !important;
  padding: 0 !important;
  z-index: 100050 !important;
  background: transparent !important;
}
[class*="st-key-ds_options_bar"] > div {
  background: transparent !important;
}
[class*="st-key-ds_options_bar"] [data-testid="stPopover"] {
  display: flex !important;
  justify-content: flex-end !important;
  width: 100% !important;
}
[class*="st-key-ds_options_bar"] [data-testid="stPopover"] > button,
[class*="st-key-ds_options_bar"] button[kind="secondary"],
[class*="st-key-ds_options_bar"] button {
  margin-left: auto !important;
  border-radius: 999px !important;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.18) !important;
  font-weight: 600 !important;
  white-space: nowrap !important;
}
/* Leave a slim band so page content clears the floating control */
[data-testid="stMain"] [data-testid="block-container"] {
  padding-top: 3.1rem !important;
}
</style>
"""


def render_app_options_bar() -> None:
    """Compact Options control fixed in the top-right corner."""
    render_html(_OPTIONS_BAR_CSS)

    user = current_user()
    if user is not None:
        short = (user.name or user.email.split("@")[0] or "Account").strip()
        if len(short) > 16:
            short = short[:15] + "…"
        label = f"Account · {short}"
    else:
        label = "Account"

    with st.container(key="ds_options_bar"), st.popover(label, use_container_width=True):
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
