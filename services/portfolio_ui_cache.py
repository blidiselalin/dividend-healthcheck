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
from typing import Any

from services.background_jobs import ProgressCallback
from utils.logging_config import get_logger

logger = get_logger("dividendscope.portfolio")

# Discard cached portfolio snapshots older than this (or when library is newer).
MAX_PORTFOLIO_CACHE_AGE = timedelta(hours=24)

# Dividend receipt sync is heavy (history per holding); run at most this often on app open.
DIVIDEND_SYNC_INTERVAL = timedelta(hours=6)


def _cache_path() -> Path:
    try:
        from auth.user_context import resolve_user_session_cache_path

        return resolve_user_session_cache_path()
    except Exception:  # noqa: S110
        pass
    try:
        from config import DATA_DIR

        return DATA_DIR / "portfolio_ui_session.pkl"
    except ImportError:
        return Path("data/portfolio_ui_session.pkl")


_DATE_FIELDS = ("ex_dividend_date", "dividend_pay_date")


def _row_to_dict(row: Any) -> dict[str, Any]:
    payload = asdict(row)
    for key in _DATE_FIELDS:
        value = payload.get(key)
        if isinstance(value, date):
            payload[key] = value.isoformat()
    return payload


def _row_from_dict(payload: dict[str, Any]) -> Any:
    from services.portfolio_details_service import PortfolioDetailRow

    data = dict(payload)
    for key in _DATE_FIELDS:
        value = data.get(key)
        if value and isinstance(value, str):
            data[key] = date.fromisoformat(value)
    return PortfolioDetailRow(**data)


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def market_library_latest_update() -> datetime | None:
    """Latest ``last_updated`` across PostgreSQL stock_documents (None if empty/local)."""
    try:
        from db.connection import ensure_schema, get_connection, use_cloud_sql

        if not use_cloud_sql():
            return None
        ensure_schema()
        with get_connection() as conn:
            row = conn.execute("SELECT MAX(last_updated) AS latest FROM stock_documents").fetchone()
        if not row or not row.get("latest"):
            return None
        return _coerce_datetime(row["latest"])
    except Exception as exc:
        logger.debug("Market library latest update unavailable: %s", exc)
        return None


def cache_saved_at_from_bundle(bundle: dict[str, Any]) -> datetime | None:
    saved = _coerce_datetime(bundle.get("saved_at"))
    if saved:
        return saved
    return _coerce_datetime(bundle.get("portfolio_details_time"))


def cache_is_stale(bundle: dict[str, Any]) -> bool:
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

    bundle: dict[str, Any] = {
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


def hydrate_session_from_disk() -> bool:  # noqa: C901
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
        if user_has_holdings_in_db():
            logger.info(
                "No portfolio UI cache found; warming synchronously from DB to prevent empty UI."
            )
            return warm_portfolio_session_from_db(preload_charts=False)
        return False

    try:
        with cache_path.open("rb") as handle:
            bundle = pickle.load(handle)  # noqa: S301
    except Exception as exc:
        logger.warning("Could not load portfolio UI cache: %s", exc)
        if user_has_holdings_in_db():
            logger.info(
                "Portfolio UI cache corrupted; warming synchronously from DB to prevent empty UI."
            )
            return warm_portfolio_session_from_db(preload_charts=False)
        return False

    rows_payload = bundle.get("rows") or []
    if not rows_payload:
        if user_has_holdings_in_db():
            logger.info(
                "Portfolio UI cache empty; warming synchronously from DB to prevent empty UI."
            )
            return warm_portfolio_session_from_db(preload_charts=False)
        return False

    if cache_is_stale(bundle):
        logger.info(
            "Portfolio UI cache stale (saved_at=%s); utilizing as "
            "fallback and scheduling background reload",
            bundle.get("saved_at", "?"),
        )
        st.session_state["_portfolio_stale_cache_loaded"] = True

    from services.portfolio_details_service import PortfolioDetailsService

    restored_rows = [_row_from_dict(item) for item in rows_payload]
    st.session_state["portfolio_details_rows"] = (
        PortfolioDetailsService().enrich_rows_previous_close(restored_rows)
    )
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


def _dividend_sync_meta_path() -> Path:
    return _cache_path().parent / "dividend_sync_at.txt"


def should_sync_dividends_on_startup() -> bool:
    """True when paid-dividend sync should run (not run on every Streamlit rerun)."""
    path = _dividend_sync_meta_path()
    if not path.is_file():
        return True
    try:
        saved = datetime.fromisoformat(path.read_text(encoding="utf-8").strip())
    except (TypeError, ValueError, OSError):
        return True
    return datetime.now() - saved > DIVIDEND_SYNC_INTERVAL


def mark_dividend_sync_completed() -> None:
    path = _dividend_sync_meta_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            datetime.now().isoformat(timespec="seconds"),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.debug("Could not write dividend sync timestamp: %s", exc)


def warm_portfolio_session_from_db(*, preload_charts: bool = False) -> bool:
    """
    Build holdings from the shared library without live prices when the session is empty.

    Returns True when rows were loaded into session_state.
    """
    import streamlit as st

    from services.portfolio_session import is_demo_session, user_has_holdings_in_db
    from ui.portfolio_risk_panel import store_portfolio_payload

    if st.session_state.get("portfolio_details_rows"):
        return True
    if is_demo_session() or not user_has_holdings_in_db():
        return False

    try:
        from services.portfolio_details_service import PortfolioDetailsService

        rows, preload = PortfolioDetailsService().build_rows_with_cache(
            use_live_prices=False,
            preload_analysis=preload_charts,
        )
    except Exception as exc:
        logger.warning("Fast portfolio load failed: %s", exc)
        return False

    if not rows:
        return False

    store_portfolio_payload(
        rows,
        preload,
        analysis_ready=preload_charts,
    )
    st.session_state["portfolio_fast_loaded"] = not preload_charts
    logger.info("Portfolio fast-loaded from library (%d holdings)", len(rows))
    return True


def compute_yield_preload_payload(
    symbols: list[str],
    stock_cache: dict[str, Any],
    vector_docs: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Build yield-channel preload payload (safe to run off the UI thread)."""
    from services.portfolio_analysis_preload import preload_portfolio_analysis
    from services.portfolio_details_service import PortfolioDetailsService

    docs = dict(vector_docs)
    if not docs and symbols:
        docs = PortfolioDetailsService()._load_documents(symbols)

    preload = preload_portfolio_analysis(
        symbols,
        stock_cache,
        docs,
        progress_callback=progress_callback,
    )
    return {
        "yield_channels": preload.yield_channels,
        "stock_data": preload.stock_data,
        "vector_docs": preload.vector_docs,
    }


def compute_fast_portfolio_payload(
    *,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Library-only portfolio rows without live prices (background-safe)."""
    from services.portfolio_details_service import PortfolioDetailsService

    if progress_callback:
        progress_callback(0.2, "Reading holdings…")
    rows, preload = PortfolioDetailsService().build_rows_with_cache(
        use_live_prices=False,
        preload_analysis=False,
    )
    if progress_callback:
        progress_callback(0.9, f"{len(rows)} holdings ready")
    return {
        "rows": rows,
        "preload": preload,
        "analysis_ready": False,
        "fast_loaded": True,
    }


def compute_live_portfolio_payload(
    *,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Full live portfolio reload (background-safe)."""
    from services.portfolio_details_service import PortfolioDetailsService

    if progress_callback:
        progress_callback(0.1, "Fetching live prices…")
    rows, preload = PortfolioDetailsService().build_rows_with_cache(
        use_live_prices=True,
        preload_analysis=True,
    )
    if progress_callback:
        progress_callback(0.95, f"{len(rows)} holdings refreshed")
    return {
        "rows": rows,
        "preload": preload,
        "analysis_ready": True,
        "fast_loaded": False,
    }


def ensure_portfolio_yield_preload() -> bool:
    """Load yield-channel charts when the table was fast-loaded without them."""
    import streamlit as st

    if st.session_state.get("portfolio_analysis_ready"):
        return False
    rows = st.session_state.get("portfolio_details_rows")
    if not rows:
        return False

    symbols = [row.ticker for row in rows]
    stock_cache = st.session_state.get("portfolio_stock_cache") or {}
    vector_docs = st.session_state.get("portfolio_vector_docs") or {}
    payload = compute_yield_preload_payload(symbols, stock_cache, vector_docs)
    st.session_state["portfolio_yield_cache"] = payload["yield_channels"]
    st.session_state["portfolio_stock_cache"] = payload["stock_data"]
    st.session_state["portfolio_vector_docs"] = payload["vector_docs"]
    st.session_state["portfolio_analysis_ready"] = True
    st.session_state.pop("portfolio_fast_loaded", None)
    save_session_cache()
    logger.info(
        "Portfolio yield charts preloaded (%d channels)",
        len(payload["yield_channels"]),
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
                bundle = pickle.load(handle)  # noqa: S301
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
