"""
Persist portfolio UI session (holdings, preload, risk summary) for fast startup.

Reload live market data when the user clicks **Reload live data**, or automatically
when the shared market library was updated after the cached snapshot was saved.
"""

from __future__ import annotations

import pickle
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logging_config import get_logger

logger = get_logger("dividendscope.portfolio")

# Discard cached portfolio snapshots older than this (or when library is newer).
MAX_PORTFOLIO_CACHE_AGE = timedelta(hours=24)

def _cache_path() -> Path:
    try:
        from auth.user_context import resolve_user_session_cache_path

        return resolve_user_session_cache_path()
    except Exception:
        pass
    try:
        from config import DATA_DIR

        return DATA_DIR / "portfolio_ui_session.pkl"
    except ImportError:
        return Path("data/portfolio_ui_session.pkl")

_DATE_FIELDS = ("ex_dividend_date", "dividend_pay_date")


def _row_to_dict(row: Any) -> Dict[str, Any]:
    payload = asdict(row)
    for key in _DATE_FIELDS:
        value = payload.get(key)
        if isinstance(value, date):
            payload[key] = value.isoformat()
    return payload


def _row_from_dict(payload: Dict[str, Any]) -> Any:
    from services.portfolio_details_service import PortfolioDetailRow

    data = dict(payload)
    for key in _DATE_FIELDS:
        value = data.get(key)
        if value and isinstance(value, str):
            data[key] = date.fromisoformat(value)
    return PortfolioDetailRow(**data)


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def market_library_latest_update() -> Optional[datetime]:
    """Latest ``last_updated`` across PostgreSQL stock_documents (None if empty/local)."""
    try:
        from db.connection import ensure_schema, get_connection, use_cloud_sql

        if not use_cloud_sql():
            return None
        ensure_schema()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT MAX(last_updated) AS latest FROM stock_documents"
            ).fetchone()
        if not row or not row.get("latest"):
            return None
        return _coerce_datetime(row["latest"])
    except Exception as exc:
        logger.debug("Market library latest update unavailable: %s", exc)
        return None


def cache_saved_at_from_bundle(bundle: Dict[str, Any]) -> Optional[datetime]:
    saved = _coerce_datetime(bundle.get("saved_at"))
    if saved:
        return saved
    return _coerce_datetime(bundle.get("portfolio_details_time"))


def cache_is_stale(bundle: Dict[str, Any]) -> bool:
    """True when the on-disk snapshot should not be shown (library or age)."""
    saved_at = cache_saved_at_from_bundle(bundle)
    if saved_at is None:
        return True

    if datetime.now() - saved_at > MAX_PORTFOLIO_CACHE_AGE:
        return True

    library_at = market_library_latest_update()
    if library_at and library_at > saved_at + timedelta(seconds=30):
        return True

    return False


def save_session_cache() -> None:
    """Write current Streamlit session portfolio state to disk."""
    import streamlit as st

    from ui.portfolio_risk_panel import SESSION_CHECKED_AT_KEY, SESSION_SUMMARY_KEY

    rows = st.session_state.get("portfolio_details_rows")
    if not rows:
        return

    bundle: Dict[str, Any] = {
        "version": 1,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "rows": [_row_to_dict(row) for row in rows],
        "attention_summary": st.session_state.get(SESSION_SUMMARY_KEY),
        "risk_checked_at": st.session_state.get(SESSION_CHECKED_AT_KEY),
        "portfolio_stock_cache": st.session_state.get("portfolio_stock_cache"),
        "portfolio_yield_cache": st.session_state.get("portfolio_yield_cache"),
        "portfolio_vector_docs": st.session_state.get("portfolio_vector_docs"),
        "portfolio_details_time": st.session_state.get("portfolio_details_time"),
        "portfolio_analysis_ready": st.session_state.get("portfolio_analysis_ready", False),
    }
    try:
        cache_path = _cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("wb") as handle:
            pickle.dump(bundle, handle, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info(
            "Portfolio UI cache saved path=%s holdings=%d",
            cache_path,
            len(bundle.get("rows") or []),
        )
    except Exception as exc:
        logger.warning("Could not save portfolio UI cache: %s", exc)


def hydrate_session_from_disk() -> bool:
    """
    Restore portfolio session from disk if the in-memory session is empty.

    Returns True when holdings rows are available in session_state.
    """
    import streamlit as st

    from services.portfolio_session import is_demo_session, user_has_holdings_in_db
    from ui.portfolio_risk_panel import SESSION_CHECKED_AT_KEY, SESSION_SUMMARY_KEY

    if not is_demo_session() and not user_has_holdings_in_db():
        clear_session_cache()
        return False

    if st.session_state.get("portfolio_details_rows"):
        return True

    cache_path = _cache_path()
    if not cache_path.exists():
        return False

    try:
        with cache_path.open("rb") as handle:
            bundle = pickle.load(handle)
    except Exception as exc:
        logger.warning("Could not load portfolio UI cache: %s", exc)
        return False

    rows_payload = bundle.get("rows") or []
    if not rows_payload:
        return False

    if cache_is_stale(bundle):
        logger.info(
            "Portfolio UI cache stale (saved_at=%s); clearing",
            bundle.get("saved_at", "?"),
        )
        clear_session_cache()
        return False

    st.session_state["portfolio_details_rows"] = [_row_from_dict(item) for item in rows_payload]
    if bundle.get("attention_summary") is not None:
        st.session_state[SESSION_SUMMARY_KEY] = bundle["attention_summary"]
    if bundle.get("risk_checked_at"):
        st.session_state[SESSION_CHECKED_AT_KEY] = bundle["risk_checked_at"]
    if bundle.get("portfolio_stock_cache") is not None:
        st.session_state["portfolio_stock_cache"] = bundle["portfolio_stock_cache"]
    if bundle.get("portfolio_yield_cache") is not None:
        st.session_state["portfolio_yield_cache"] = bundle["portfolio_yield_cache"]
    if bundle.get("portfolio_vector_docs") is not None:
        st.session_state["portfolio_vector_docs"] = bundle["portfolio_vector_docs"]
    details_time = _coerce_datetime(bundle.get("portfolio_details_time"))
    if details_time:
        st.session_state["portfolio_details_time"] = details_time
    st.session_state["portfolio_analysis_ready"] = bool(bundle.get("portfolio_analysis_ready"))
    st.session_state["portfolio_show_analysis"] = True
    logger.info(
        "Portfolio UI cache loaded path=%s holdings=%d saved_at=%s",
        cache_path,
        len(rows_payload),
        bundle.get("saved_at", "?"),
    )
    return True


def clear_session_cache() -> None:
    """Remove on-disk cache (e.g. after portfolio structure changes)."""
    try:
        cache_path = _cache_path()
        if cache_path.exists():
            cache_path.unlink()
    except OSError as exc:
        logger.warning("Could not clear portfolio UI cache: %s", exc)


def refresh_portfolio_after_library_update() -> bool:
    """
    Reload portfolio live data once when the market library is newer than the UI cache.

    Returns True when a reload was performed.
    """
    import streamlit as st

    from services.portfolio_session import is_demo_session, user_has_holdings_in_db

    if is_demo_session() or not user_has_holdings_in_db():
        return False
    if st.session_state.get("portfolio_details_rows"):
        return False
    if st.session_state.get("_portfolio_library_sync_done"):
        return False

    library_at = market_library_latest_update()
    if library_at is None:
        return False

    cache_path = _cache_path()
    if cache_path.is_file():
        try:
            with cache_path.open("rb") as handle:
                bundle = pickle.load(handle)
            if not cache_is_stale(bundle):
                return False
        except Exception:
            clear_session_cache()

    try:
        from ui.portfolio_sidebar import _reload_live_data

        logger.info("Auto-reloading portfolio after market library update")
        _reload_live_data()
        st.session_state["_portfolio_library_sync_done"] = True
        return True
    except Exception as exc:
        logger.warning("Auto portfolio reload failed: %s", exc)
        return False
