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
from ui.app_about import render_app_about_compact
from ui.theme import inject_app_theme


def render_login_page(*, access_denied: bool = False) -> None:
    inject_app_theme()

    _left, center, _right = st.columns([1, 2, 1])
    with center:
        _render_login_content(access_denied=access_denied)


def _render_login_content(*, access_denied: bool) -> None:
    st.markdown("## DividendScope")
    render_app_about_compact()

    if access_denied:
        from ui.access_request_panel import render_access_denied_panel

        render_access_denied_panel()
        return

    if auth_disabled():
        st.warning("Authentication is disabled. Enable Google OAuth in Streamlit secrets.")
    elif not auth_configured():
        st.warning(
            "Google sign-up is not configured. Copy `.streamlit/secrets.toml.example` to "
            "`.streamlit/secrets.toml` and add your OAuth client credentials."
        )
        dev_email = st.text_input("Dev email (local bypass)", placeholder="you@gmail.com")
        if st.button("Continue in dev mode", type="primary") and dev_email.strip():
            st.session_state["dev_login_email"] = dev_email.strip().lower()
            st.rerun()
    else:
        _render_google_auth_block()

    if test_user_enabled():
        st.divider()
        st.markdown("#### Test user (UI check)")
        st.caption(f"Demo data KO, JNJ, O · no Google needed · {test_user_email()}")
        if st.button("Continue as test user", use_container_width=True):
            sign_in_as_test_user()
            st.rerun()

    st.caption("Educational use only — not financial advice.")


def _render_google_auth_block() -> None:
    if google_signup_enabled():
        st.markdown("### Create your account")
        if invite_only_signup():
            st.caption(
                "Sign up or sign in with an **invited** Google account, "
                "or request access after signing in with Google. "
                "Your portfolio is private to you."
            )
            allowed = sorted(allowed_emails())
            if len(allowed) <= 8:
                st.caption("Invited: " + ", ".join(allowed))
        else:
            st.caption(
                "Sign up with your Google account — one click, no separate password. "
                "Returning users: use the same button to sign in."
            )
        if st.button(
            "Sign up with Google",
            type="primary",
            use_container_width=True,
            key="auth_signup_google",
        ):
            st.login()
        st.caption("Already have an account? Use the same button — we'll sign you in.")
    else:
        st.markdown("### Sign in")
        st.caption("Use your Google account to open your portfolio workspace.")
        if st.button(
            "Sign in with Google",
            type="primary",
            use_container_width=True,
            key="auth_signin_google_only",
        ):
            st.login()
