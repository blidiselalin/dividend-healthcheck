"""
Demo / test user for validating home page, examples, and empty states.

Enable in `.streamlit/secrets.toml`:

    test_user_enabled = true
    test_user_email = "test@dividendscope.local"
"""

from __future__ import annotations

import os

from auth.models import CurrentUser
from auth.settings import _auth_section

TEST_USER_ID = "test_demo"
DEFAULT_TEST_EMAIL = "test@dividendscope.local"
SESSION_FLAG = "auth_test_user"


def test_user_enabled() -> bool:
    section = _auth_section()
    if section.get("test_user_enabled") is False:
        return False
    flag = os.environ.get("DIVIDENDSCOPE_TEST_USER", "").strip().lower()
    if flag in ("0", "false", "no"):
        return False
    if flag in ("1", "true", "yes"):
        return True
    return bool(section.get("test_user_enabled", True))


def test_user_email() -> str:
    section = _auth_section()
    return (
        (
            str(section.get("test_user_email") or os.environ.get("DIVIDENDSCOPE_TEST_USER_EMAIL"))
            or DEFAULT_TEST_EMAIL
        )
        .strip()
        .lower()
    )


def is_test_user_email(email: str) -> bool:
    return email.strip().lower() == test_user_email()


def is_test_user_id(user_id: str) -> bool:
    return user_id == TEST_USER_ID


def is_test_user(user: CurrentUser | None) -> bool:
    if user is None:
        return False
    return is_test_user_id(user.id) or is_test_user_email(user.email)


def test_user_session_active() -> bool:
    if not test_user_enabled():
        return False
    try:
        import streamlit as st

        return bool(st.session_state.get(SESSION_FLAG))
    except Exception:
        return False


def test_user_current() -> CurrentUser:
    return CurrentUser(
        id=TEST_USER_ID,
        email=test_user_email(),
        name="Test user (demo)",
        is_admin=False,
    )


def sign_in_as_test_user() -> None:
    import streamlit as st

    st.session_state[SESSION_FLAG] = True
    st.session_state.pop("dev_login_email", None)


def sign_out_test_user() -> None:
    import streamlit as st

    from auth.user_context import clear_portfolio_session_state

    st.session_state.pop(SESSION_FLAG, None)
    clear_portfolio_session_state()
