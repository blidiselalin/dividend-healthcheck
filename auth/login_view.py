"""
Sign-up / sign-in screen (Google OIDC via Streamlit) and test-user entry.
"""

from __future__ import annotations

import streamlit as st

from auth.settings import (
    allowed_emails,
    auth_configured,
    auth_disabled,
    google_signup_enabled,
    invite_only_signup,
)
from auth.test_user import sign_in_as_test_user, test_user_email, test_user_enabled
from ui.command_center_home import render_command_center_page


def _login_with_google() -> None:
    """Streamlit OIDC — creates an account on first Google login, signs in after."""
    st.login()


def render_login_page(*, access_denied: bool = False) -> None:
    if access_denied:
        from ui.app_about import render_app_about_compact
        from ui.design_system import render_logo
        from ui.theme import inject_app_theme

        inject_app_theme()
        _left, center, _right = st.columns([1, 2, 1])
        with center:
            render_logo(tagline="Beta access")
            render_app_about_compact()
            from ui.access_request_panel import render_access_denied_panel

            render_access_denied_panel()
        return

    def _auth_block() -> None:
        _render_auth_controls()

    render_command_center_page(auth_block=_auth_block)


def _render_auth_controls() -> None:
    if auth_disabled():
        st.warning("Authentication is disabled. Enable Google OAuth in Streamlit secrets.")
        dev_email = st.text_input("Dev email (local bypass)", placeholder="you@gmail.com")
        if (
            st.button("Continue in dev mode", type="primary", use_container_width=True)
            and dev_email.strip()
        ):
            st.session_state["dev_login_email"] = dev_email.strip().lower()
            st.rerun()
    elif not auth_configured():
        st.warning(
            "Google sign-up is not configured. Copy `.streamlit/secrets.toml.example` to "
            "`.streamlit/secrets.toml` and add your OAuth client credentials."
        )
        dev_email = st.text_input("Dev email (local bypass)", placeholder="you@gmail.com")
        if (
            st.button("Continue in dev mode", type="primary", use_container_width=True)
            and dev_email.strip()
        ):
            st.session_state["dev_login_email"] = dev_email.strip().lower()
            st.rerun()
    else:
        _render_google_auth_block()

    if test_user_enabled():
        st.divider()
        st.caption(f"**Test mode** — full demo KO, JNJ, O · {test_user_email()}")
        if st.button("Continue as test user", use_container_width=True):
            sign_in_as_test_user()
            st.rerun()


def _render_google_auth_block() -> None:
    if google_signup_enabled():
        if invite_only_signup():
            st.caption(
                "Sign up with an **invited** Google account. Your try list can carry over "
                "into your private portfolio."
            )
            allowed = sorted(allowed_emails())
            if len(allowed) <= 8:
                st.caption("Invited: " + ", ".join(allowed))
        else:
            st.caption(
                "One-click Google sign-up — your try-list holdings copy into your "
                "account automatically."
            )
        st.button(
            "Create portfolio — Sign up with Google",
            type="primary",
            use_container_width=True,
            on_click=_login_with_google,
            key="auth_signup_google",
        )
        st.caption("Already have an account? Same button signs you in.")
    else:
        st.caption("Sign in with Google to save your portfolio.")
        st.button(
            "Create portfolio — Sign in with Google",
            type="primary",
            use_container_width=True,
            on_click=_login_with_google,
            key="auth_signin_google_only",
        )
