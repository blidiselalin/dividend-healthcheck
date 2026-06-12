"""
Resolve the signed-in user and per-user data paths for portfolio storage.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from auth.demo_portfolio import ensure_demo_database, load_demo_ui_snapshot
from auth.migration import restore_owner_portfolio
from auth.models import CurrentUser, sanitize_user_id
from auth.settings import (
    auth_required,
    dev_bypass_email,
    is_admin_email,
    is_email_allowed,
)
from auth.test_user import (
    is_test_user,
    test_user_current,
    test_user_session_active,
)
from auth.user_store import AppUser, UserStore
from config import DATA_DIR
from utils.logging_config import get_logger
from utils.portfolio_db import holding_count

logger = get_logger("dividendscope.auth")
_LOCAL_USER_ID = "local"
_SESSION_USER_KEY = "app_user_id"
_SESSION_EMAIL_KEY = "app_user_email"
_BACKGROUND_USER = threading.local()


@contextmanager
def bind_background_user_id(user_id: str | None) -> Iterator[None]:
    """
    Bind a user id for portfolio DB access inside background worker threads.

    Streamlit session identity is unavailable off the main thread; jobs must
    capture ``current_user_id()`` when scheduled and re-bind it in the worker.
    """
    previous = getattr(_BACKGROUND_USER, "user_id", None)
    if user_id:
        _BACKGROUND_USER.user_id = user_id
    try:
        yield
    finally:
        if user_id:
            if previous is None:
                if hasattr(_BACKGROUND_USER, "user_id"):
                    delattr(_BACKGROUND_USER, "user_id")
            else:
                _BACKGROUND_USER.user_id = previous


def background_user_id() -> str | None:
    return getattr(_BACKGROUND_USER, "user_id", None)


def _streamlit_logged_in() -> bool:
    try:
        import streamlit as st

        return bool(getattr(st.user, "is_logged_in", False))
    except Exception:
        return False


def _identity_from_streamlit() -> CurrentUser | None:
    try:
        import streamlit as st
    except Exception:
        return None

    if not _streamlit_logged_in():
        return None

    subject = str(getattr(st.user, "sub", "") or getattr(st.user, "id", "") or "").strip()
    email = str(getattr(st.user, "email", "") or "").strip()
    if not subject and email:
        subject = email
    if not subject:
        return None

    name = getattr(st.user, "name", None) or getattr(st.user, "given_name", None)
    picture = getattr(st.user, "picture", None)
    user_id = sanitize_user_id(subject)
    admin = is_admin_email(email) if email else False
    return CurrentUser(
        id=user_id,
        email=email or f"{user_id}@users.local",
        name=str(name) if name else None,
        picture_url=str(picture) if picture else None,
        is_admin=admin,
    )


def _dev_user() -> CurrentUser | None:
    email = dev_bypass_email()
    if not email:
        try:
            import streamlit as st

            email = (st.session_state.get("dev_login_email") or "").strip()
        except Exception:
            email = ""
    if not email:
        return None
    user_id = sanitize_user_id(email)
    return CurrentUser(
        id=user_id,
        email=email,
        name="Local dev",
        is_admin=is_admin_email(email),
    )


def uses_per_user_storage() -> bool:
    return auth_required() or test_user_session_active()


def google_identity() -> CurrentUser | None:
    """Signed-in Google user from Streamlit OIDC (even if not yet allowed in the app)."""
    if test_user_session_active():
        return None
    if not auth_required():
        return _dev_user()
    return _identity_from_streamlit()


def current_user() -> CurrentUser | None:
    if test_user_session_active():
        return test_user_current()

    if auth_required():
        user = _identity_from_streamlit()
        if user:
            return user
        return None

    dev = _dev_user()
    if dev:
        return dev

    return CurrentUser(
        id=_LOCAL_USER_ID,
        email="local@dividendscope",
        name="Local",
        is_admin=True,
    )


def current_user_id() -> str | None:
    bound = background_user_id()
    if bound:
        return bound
    user = current_user()
    return user.id if user else None


def is_app_admin(
    user: CurrentUser | None = None,
    registered: AppUser | None = None,
) -> bool:
    """True when the user may use admin tools (DB admin flag or configured admin email)."""
    user = user or current_user()
    if user is None:
        return False
    if is_admin_email(user.email):
        return True
    reg = registered if registered is not None else ensure_user_session()
    return bool(reg and reg.is_admin)


def resolve_user_data_dir() -> Path:
    bound = background_user_id()
    if bound and uses_per_user_storage():
        path = DATA_DIR / "users" / bound
        path.mkdir(parents=True, exist_ok=True)
        return path
    user = current_user()
    if user and uses_per_user_storage():
        path = DATA_DIR / "users" / user.id
        path.mkdir(parents=True, exist_ok=True)
        return path
    return DATA_DIR


def resolve_portfolio_db_path() -> Path:
    return resolve_user_data_dir() / "portfolio.db"


def resolve_user_session_cache_path() -> Path:
    return resolve_user_data_dir() / "portfolio_ui_session.pkl"


def clear_portfolio_session_state() -> None:
    try:
        import streamlit as st
    except Exception:
        return

    keys = [
        "portfolio_details_rows",
        "portfolio_details_time",
        "portfolio_analysis_ready",
        "portfolio_show_analysis",
        "portfolio_stock_cache",
        "portfolio_yield_cache",
        "portfolio_vector_docs",
        "portfolio_attention_summary",
        "portfolio_risk_checked_at",
        "portfolio_risk_refresh_in_progress",
        "portfolio_view_mode",
        "portfolio_selected_symbol",
        "portfolio_research_mode",
        "portfolio_section_label",
        "portfolio_nav_tickers",
        "portfolio_zone_filter",
        "portfolio_holdings_drill_ticker",
        "portfolio_show_examples",
        "admin_console_active",
        "dev_login_email",
        "access_request_just_sent",
        _SESSION_USER_KEY,
        _SESSION_EMAIL_KEY,
    ]
    for key in keys:
        st.session_state.pop(key, None)


def _register_user(user: CurrentUser) -> AppUser:
    store = UserStore()
    return store.upsert_from_login(
        user_id=user.id,
        email=user.email,
        name=user.name,
        picture_url=user.picture_url,
        is_admin=user.is_admin,
    )


def ensure_user_session() -> AppUser | None:  # noqa: C901
    """
    After login, register the user, enforce allowlist, and attach per-user storage.

    Returns None when not signed in or not allowed.
    """
    user = current_user()
    if user is None:
        return None

    if not is_test_user(user) and auth_required() and not is_email_allowed(user.email):
        return None

    try:
        import streamlit as st
    except Exception:
        return _register_user(user)

    previous_id = st.session_state.get(_SESSION_USER_KEY)
    if previous_id and previous_id != user.id:
        logger.info("User switched %s -> %s; clearing portfolio session", previous_id, user.id)
        clear_portfolio_session_state()

    registered = _register_user(user)
    if not registered.is_active:
        logger.warning("User inactive: %s", user.email)
        return None

    user_dir = resolve_user_data_dir()
    db_path = user_dir / "portfolio.db"
    session_changed = st.session_state.get(_SESSION_USER_KEY) != user.id

    if is_test_user(user):
        if session_changed:
            logger.info("Test user session: %s", user.email)
        ensure_demo_database(db_path)
        load_demo_ui_snapshot()
    else:
        if holding_count(db_path) == 0:
            clear_portfolio_session_state()
            from services.portfolio_ui_cache import clear_session_cache

            clear_session_cache()
        if (user.is_admin or is_admin_email(user.email)) and restore_owner_portfolio(
            user.id, user_dir
        ):
            logger.info(
                "Admin portfolio restored from legacy for %s (holdings=%d)",
                user.email,
                holding_count(db_path),
            )
            clear_portfolio_session_state()
        # Legacy portfolio is not auto-copied on first login — use
        # Per-user portfolio data is stored in PostgreSQL when DATABASE_URL is set.

    if session_changed:
        logger.info(
            "User session ready id=%s email=%s db=%s holdings=%d admin=%s",
            user.id,
            user.email,
            db_path,
            holding_count(db_path),
            user.is_admin,
        )

    st.session_state[_SESSION_USER_KEY] = user.id
    st.session_state[_SESSION_EMAIL_KEY] = user.email
    return registered
