"""
Keep Streamlit portfolio UI state aligned with the current user's SQLite holdings.
"""

from __future__ import annotations

from pathlib import Path


def is_demo_session() -> bool:
    """True only for the configured test/demo user."""
    try:
        from auth.test_user import is_test_user, test_user_session_active
        from auth.user_context import current_user

        user = current_user()
        return bool(user and test_user_session_active() and is_test_user(user))
    except Exception:
        return False


def resolve_current_portfolio_db() -> Path:
    from auth.user_context import resolve_portfolio_db_path

    return resolve_portfolio_db_path()


def user_has_holdings_in_db() -> bool:
    from utils.portfolio_db import holding_count

    return holding_count(resolve_current_portfolio_db()) > 0


def sync_portfolio_session_with_db() -> None:
    """
    For real users with no holdings, drop cached rows so demo/legacy data never shows.
    """
    if is_demo_session():
        return
    if user_has_holdings_in_db():
        return

    try:
        import streamlit as st
    except Exception:
        return

    from auth.user_context import clear_portfolio_session_state
    from services.portfolio_ui_cache import clear_session_cache

    if st.session_state.get("portfolio_details_rows"):
        clear_portfolio_session_state()
    clear_session_cache()
