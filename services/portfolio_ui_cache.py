"""
Persist portfolio UI session (holdings, preload, risk summary) for fast startup.

Reload live market data only when the user clicks **Reload live data** in the sidebar.
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

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
    except Exception as exc:
        logger.warning("Could not save portfolio UI cache: %s", exc)


def hydrate_session_from_disk() -> bool:
    """
    Restore portfolio session from disk if the in-memory session is empty.

    Returns True when holdings rows are available in session_state.
    """
    import streamlit as st

    from ui.portfolio_risk_panel import SESSION_CHECKED_AT_KEY, SESSION_SUMMARY_KEY

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
    if bundle.get("portfolio_details_time"):
        st.session_state["portfolio_details_time"] = bundle["portfolio_details_time"]
    st.session_state["portfolio_analysis_ready"] = bool(bundle.get("portfolio_analysis_ready"))
    st.session_state["portfolio_show_analysis"] = True
    return True


def clear_session_cache() -> None:
    """Remove on-disk cache (e.g. after portfolio structure changes)."""
    try:
        cache_path = _cache_path()
        if cache_path.exists():
            cache_path.unlink()
    except OSError as exc:
        logger.warning("Could not clear portfolio UI cache: %s", exc)
