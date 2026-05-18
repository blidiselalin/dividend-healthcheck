"""Google sign-in and per-user portfolio storage."""

from auth.settings import auth_required
from auth.user_context import (
    current_user,
    current_user_id,
    ensure_user_session,
    resolve_portfolio_db_path,
    resolve_user_data_dir,
    resolve_user_session_cache_path,
)

__all__ = [
    "auth_required",
    "current_user",
    "current_user_id",
    "ensure_user_session",
    "resolve_portfolio_db_path",
    "resolve_user_data_dir",
    "resolve_user_session_cache_path",
]
