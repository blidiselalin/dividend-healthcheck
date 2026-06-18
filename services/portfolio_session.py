"""
Keep Streamlit portfolio UI state aligned with the current user's holdings.
"""

from __future__ import annotations

import time
from pathlib import Path

# Per-user TTL cache for user_has_holdings_in_db() so repeated calls within the
# same Streamlit render cycle (6-8 are typical) only hit the DB once.
_HOLDINGS_CACHE: dict[str, tuple[bool, float]] = {}
_HOLDINGS_CACHE_TTL: float = 5.0  # seconds


def _holdings_cache_key() -> str:
    try:
        from auth.user_context import current_user_id

        uid = current_user_id()
        # "local" is the unauthenticated sentinel — fall through to DB-path key
        # so test fixtures with different tmp paths don't share the same cache entry.
        if uid and uid != "local":
            return str(uid)
    except Exception:
        pass
    # Unauthenticated / local mode: key on the actual DB path.
    try:
        return str(resolve_current_portfolio_db())
    except Exception:
        return "local"


def invalidate_holdings_cache() -> None:
    """Drop the cached holdings-count so the next call re-queries the DB."""
    key = _holdings_cache_key()
    _HOLDINGS_CACHE.pop(key, None)


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
    key = _holdings_cache_key()
    now = time.monotonic()
    cached = _HOLDINGS_CACHE.get(key)
    if cached is not None and (now - cached[1]) < _HOLDINGS_CACHE_TTL:
        return cached[0]

    from utils.portfolio_db import holding_count

    result = holding_count(resolve_current_portfolio_db()) > 0
    _HOLDINGS_CACHE[key] = (result, now)
    return result


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
