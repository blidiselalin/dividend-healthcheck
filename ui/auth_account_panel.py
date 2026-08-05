"""
Account controls and admin user management (app Options menu).
"""

from __future__ import annotations

import streamlit as st

from auth.settings import auth_required
from auth.test_user import is_test_user, sign_out_test_user, test_user_session_active
from auth.user_context import (
    clear_portfolio_session_state,
    current_user,
    ensure_user_session,
    is_app_admin,
)
from auth.user_store import UserStore


def _holding_count_for_user(user_id: str) -> int:
    from db.connection import holding_count_for_user

    return holding_count_for_user(user_id)


def render_account_options() -> None:
    """Account block for the top-right Options popover (main panel)."""
    user = current_user()
    if user is None:
        return

    st.markdown("**Account**")
    cols = st.columns([1, 3])
    if user.picture_url:
        cols[0].image(user.picture_url, width=48)
    with cols[1]:
        st.markdown(f"**{user.name or user.email.split('@')[0]}**")
        st.caption(user.email)

    if test_user_session_active() and is_test_user(user):
        if st.button("Exit test user", use_container_width=True, key="options_exit_test_user"):
            sign_out_test_user()
            st.rerun()
    elif auth_required() and st.button(
        "Sign out", use_container_width=True, key="options_sign_out"
    ):
        clear_portfolio_session_state()
        st.logout()

    registered = ensure_user_session()
    if registered and is_app_admin(user, registered):
        from ui.access_request_panel import render_admin_access_requests

        render_admin_access_requests(in_sidebar=False)
        _render_admin_users()


def render_account_sidebar() -> None:
    """Backward-compatible alias — account lives in Options now."""
    render_account_options()


def _render_admin_users() -> None:
    st.markdown("**Users**")
    store = UserStore()
    users = store.list_users()
    if not users:
        st.caption("No users yet.")
        return

    rows = []
    for item in users:
        rows.append(
            {
                "Email": item.email,
                "User id": item.id,
                "Name": item.name or "—",
                "Holdings": _holding_count_for_user(item.id),
                "Active": "yes" if item.is_active else "no",
                "Admin": "yes" if item.is_admin else "no",
                "Last login": item.last_login_at.strftime("%Y-%m-%d %H:%M"),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    with st.expander("Manage access", expanded=False):
        pick = st.selectbox(
            "User",
            options=[u.id for u in users],
            format_func=lambda uid: next(u.email for u in users if u.id == uid),
            key="admin_user_pick",
        )
        selected = next(u for u in users if u.id == pick)
        active = st.checkbox("Active", value=selected.is_active, key="admin_user_active")
        admin = st.checkbox("Admin", value=selected.is_admin, key="admin_user_admin")
        if st.button("Save user", key="admin_user_save"):
            store.set_active(pick, active=active)
            store.set_admin(pick, admin=admin)
            st.success("User updated.")
            st.rerun()
