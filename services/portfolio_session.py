"""
Keep Streamlit portfolio UI state aligned with the current user's holdings.
"""

from __future__ import annotations

import time
from pathlib import Path

from utils.logging_config import get_logger
from utils.portfolio_db import (
    compute_portfolio_db_fingerprint,
    invalidate_portfolio_db_fingerprint_cache,
)

logger = get_logger("dividendscope.portfolio")

# Per-user TTL cache for user_has_holdings_in_db() so repeated calls within the
# same Streamlit render cycle (6-8 are typical) only hit the DB once.
_HOLDINGS_CACHE: dict[str, tuple[bool, float]] = {}
_HOLDINGS_CACHE_TTL: float = 5.0  # seconds

_PORTFOLIO_DB_FINGERPRINT_KEY = "_portfolio_db_fingerprint"
_PORTFOLIO_DB_REFRESHING_KEY = "_portfolio_db_refreshing"


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
    invalidate_portfolio_db_fingerprint_cache()


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


def _clear_stale_session_when_empty() -> None:
    """Drop cached UI rows when the portfolio DB has no holdings."""
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
    st.session_state.pop(_PORTFOLIO_DB_FINGERPRINT_KEY, None)


def refresh_session_if_portfolio_db_changed(*, force: bool = False) -> bool:
    """
    Reload portfolio session rows when portfolio-local DB tables changed.

    Returns True when a reload was performed.
    """
    if is_demo_session():
        return False

    try:
        import streamlit as st
    except Exception:
        return False

    if not user_has_holdings_in_db():
        st.session_state[_PORTFOLIO_DB_FINGERPRINT_KEY] = compute_portfolio_db_fingerprint(
            use_cache=False
        )
        return False

    if not st.session_state.get("portfolio_details_rows") and not force:
        return False

    current = compute_portfolio_db_fingerprint(use_cache=False)
    previous = st.session_state.get(_PORTFOLIO_DB_FINGERPRINT_KEY)

    if not force and previous is not None and current == previous:
        st.session_state[_PORTFOLIO_DB_FINGERPRINT_KEY] = current
        return False

    if not force and previous is None and st.session_state.get("portfolio_details_rows"):
        from data_ingestion.portfolio_store import PortfolioStore

        store = PortfolioStore(db_path=resolve_current_portfolio_db(), seed=False)
        db_symbols = {holding.symbol for holding in store.list_holdings()}
        session_symbols = {
            getattr(row, "ticker", None)
            for row in st.session_state["portfolio_details_rows"]
        }
        session_symbols.discard(None)
        if db_symbols == session_symbols:
            st.session_state[_PORTFOLIO_DB_FINGERPRINT_KEY] = current
            return False

    if st.session_state.get(_PORTFOLIO_DB_REFRESHING_KEY):
        st.session_state[_PORTFOLIO_DB_FINGERPRINT_KEY] = current
        return False

    st.session_state[_PORTFOLIO_DB_REFRESHING_KEY] = True
    try:
        logger.info(
            "Portfolio DB changed (fingerprint %s -> %s); reloading session",
            (previous or "")[:12],
            current[:12],
        )
        from services.portfolio_refresh import reload_portfolio_session

        reload_portfolio_session(refresh_risks=True, sections=["all"])
        current = compute_portfolio_db_fingerprint(use_cache=False)
    finally:
        st.session_state.pop(_PORTFOLIO_DB_REFRESHING_KEY, None)

    st.session_state[_PORTFOLIO_DB_FINGERPRINT_KEY] = current
    return True


def sync_portfolio_session_with_db() -> None:
    """
    Align Streamlit portfolio state with the current user's DB.

    Clears stale UI when holdings were removed, and reloads rows when portfolio
    details changed in the database since the last session load.
    """
    if is_demo_session():
        return

    _clear_stale_session_when_empty()
    refresh_session_if_portfolio_db_changed()
