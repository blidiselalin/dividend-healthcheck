"""
Sign-up / sign-in screen (Google OIDC via Streamlit) and test-user entry.
"""

from __future__ import annotations

import streamlit as st

from auth.settings import (
    auth_configured,
    auth_disabled,
    auth_required,
    google_signup_enabled,
    invite_only_signup,
)
from auth.test_user import sign_in_as_test_user, test_user_email, test_user_enabled
from ui.command_center_home import (
    PublicButtonVariant,
    render_command_center_page,
    render_public_button,
    set_public_feedback,
)


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


def _continue_dev_login() -> None:
    email = str(st.session_state.get("cc_auth_dev_email") or "").strip().lower()
    if not email:
        set_public_feedback("warning", "Enter an email to continue in dev mode.", "auth_dev")
        return
    st.session_state["dev_login_email"] = email


def _render_dev_login(*, notice: str) -> None:
    st.warning(notice)
    st.text_input(
        "Dev email (local bypass)",
        placeholder="you@gmail.com",
        key="cc_auth_dev_email",
    )
    render_public_button(
        "Continue in dev mode",
        key="cc_auth_dev_continue",
        variant=PublicButtonVariant.PRIMARY,
        on_click=_continue_dev_login,
    )


def _render_auth_controls() -> None:
    if auth_required() and not auth_configured():
        st.error(
            "Google sign-in is required for this deployment, but OAuth is not configured. "
            "Contact the operator; portfolio access is locked."
        )
        return

    if auth_disabled():
        _render_dev_login(
            notice="Authentication is disabled. Enable Google OAuth in Streamlit secrets."
        )
    elif not auth_configured():
        _render_dev_login(
            notice=(
                "Google sign-up is not configured. Copy `.streamlit/secrets.toml.example` to "
                "`.streamlit/secrets.toml` and add your OAuth client credentials."
            )
        )
    else:
        _render_google_auth_block()

    if test_user_enabled():
        st.divider()
        st.caption(f"**Test mode** — diversified demo · 10 holdings · {test_user_email()}")
        render_public_button(
            "Continue as test user",
            key="cc_auth_test_user",
            variant=PublicButtonVariant.SECONDARY,
            on_click=sign_in_as_test_user,
        )


def _render_google_auth_block() -> None:
    if google_signup_enabled():
        if invite_only_signup():
            st.info(
                "**Invite-only beta.** Sign in with a Google account that has been invited "
                "or approved. The public demo uses sample data only."
            )
            st.caption(
                "If you are not on the invite list, sign in once to request access. "
                "Your try-list holdings can carry over after approval."
            )
        else:
            st.caption(
                "One-click Google sign-up — your try-list holdings copy into your "
                "account automatically."
            )
        render_public_button(
            "Create portfolio — Sign up with Google",
            key="auth_signup_google",
            variant=PublicButtonVariant.PRIMARY,
            on_click=_login_with_google,
        )
        st.caption("Already have an account? Same button signs you in.")
    else:
        st.caption("Sign in with Google to save your portfolio.")
        render_public_button(
            "Create portfolio — Sign in with Google",
            key="auth_signin_google_only",
            variant=PublicButtonVariant.PRIMARY,
            on_click=_login_with_google,
        )
