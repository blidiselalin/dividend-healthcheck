"""
Persist portfolio UI session (holdings, preload, risk summary) for fast startup.

Reload live market data when the user clicks **Reload live data**, or automatically
when the shared market library was updated after the cached snapshot was saved.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from sqlite3 import Error as SQLiteError
from typing import Any

from services.background_jobs import ProgressCallback
from utils.logging_config import get_logger

try:
    from psycopg import Error as PostgresError
except ImportError:
    PostgresError = type("PostgresError", (Exception,), {})

logger = get_logger("dividendscope.portfolio")

# Discard cached portfolio snapshots older than this (or when library is newer).
MAX_PORTFOLIO_CACHE_AGE = timedelta(hours=24)

# Dividend receipt sync is heavy (history per holding); run at most this often on app open.
DIVIDEND_SYNC_INTERVAL = timedelta(hours=6)

# TTL for market_library_latest_update() — avoids a SELECT MAX per startup check.
_LIBRARY_UPDATE_CACHE_TTL: float = 60.0
_library_update_cache: tuple[datetime | None, float] | None = None


def _cache_path() -> Path:
    try:
        from auth.user_context import resolve_user_session_cache_path

        return resolve_user_session_cache_path()
    except (ImportError, AttributeError):  # noqa: S110
        pass
    try:
        from config import DATA_DIR

        return DATA_DIR / "portfolio_ui_session.json"
    except ImportError:
        return Path("data/portfolio_ui_session.json")


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
    """Latest ``last_updated`` across PostgreSQL stock_documents (None if empty/local).

    Cached for ``_LIBRARY_UPDATE_CACHE_TTL`` seconds so multiple calls within
    the same render cycle (staleness check + library-reload decision) share one
    database round-trip.
    """
    global _library_update_cache

    now = time.monotonic()
    if (
        _library_update_cache is not None
        and (now - _library_update_cache[1]) < _LIBRARY_UPDATE_CACHE_TTL
    ):
        return _library_update_cache[0]

    result = _fetch_market_library_latest_update()
    _library_update_cache = (result, now)
    return result


def _fetch_market_library_latest_update() -> datetime | None:
    """Uncached query for the latest stock_documents update timestamp."""
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
    except (SQLiteError, PostgresError, OSError) as exc:
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
    return bool(library_at and library_at > saved_at + timedelta(seconds=30))


_PENDING_CACHE_SAVE_KEY = "_portfolio_cache_save_pending"


def save_session_cache(*, force: bool = False) -> None:
    """Write current Streamlit session portfolio state to disk (debounced per rerun)."""
    import streamlit as st

    rows = st.session_state.get("portfolio_details_rows")
    if not rows:
        return

    if not force:
        st.session_state[_PENDING_CACHE_SAVE_KEY] = True
        return

    _write_session_cache()


def flush_session_cache_if_pending() -> None:
    """Persist debounced portfolio UI cache once per script run."""
    import streamlit as st

    if st.session_state.pop(_PENDING_CACHE_SAVE_KEY, False):
        _write_session_cache()


def _write_session_cache() -> None:
    import streamlit as st

    from ui.portfolio_risk_panel import SESSION_CHECKED_AT_KEY, SESSION_SUMMARY_KEY

    rows = st.session_state.get("portfolio_details_rows")
    if not rows:
        return

    risk_checked_at = st.session_state.get(SESSION_CHECKED_AT_KEY)
    # Serialise only JSON-safe fields.  Complex analysis objects (stock_cache,
    # yield_cache, vector_docs) are excluded; they are rebuilt lazily on next load.
    bundle: dict[str, Any] = {
        "version": 2,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "rows": [_row_to_dict(row) for row in rows],
        "attention_summary": st.session_state.get(SESSION_SUMMARY_KEY),
        "risk_checked_at": risk_checked_at.isoformat()
        if isinstance(risk_checked_at, datetime)
        else risk_checked_at,
        "portfolio_details_time": st.session_state.get("portfolio_details_time"),
        # Analysis caches are intentionally omitted; flag is forced False so the
        # UI knows to trigger a background reload after hydration.
        "portfolio_analysis_ready": False,
    }
    try:
        from utils.portfolio_db import compute_portfolio_db_fingerprint

        bundle["db_fingerprint"] = compute_portfolio_db_fingerprint(use_cache=False)
    except (SQLiteError, PostgresError, OSError) as exc:
        logger.debug("Could not compute portfolio DB fingerprint for cache: %s", exc)
    try:
        cache_path = _cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as handle:
            json.dump(bundle, handle, default=str)
        logger.info(
            "Portfolio UI cache saved path=%s holdings=%d",
            cache_path,
            len(bundle.get("rows") or []),
        )
    except (OSError, TypeError) as exc:
        logger.warning("Could not save portfolio UI cache: %s", exc)


def _rebuild_risk_summary_if_needed() -> None:
    """Build sidebar watchlists from cached rows without network I/O."""
    import streamlit as st

    from ui.portfolio_risk_panel import SESSION_SUMMARY_KEY, _rebuild_attention_from_session

    if st.session_state.get(SESSION_SUMMARY_KEY):
        return
    if not st.session_state.get("portfolio_details_rows"):
        return
    try:
        _rebuild_attention_from_session()
    except (ImportError, AttributeError, KeyError) as exc:
        logger.debug("Risk watchlist rebuild skipped: %s", exc)


def _apply_disk_bundle(bundle: dict[str, Any], *, cache_path: Path) -> bool:
    """Restore session_state from a saved portfolio UI cache bundle."""
    import streamlit as st

    from services.portfolio_details_service import PortfolioDetailsService
    from ui.portfolio_risk_panel import SESSION_CHECKED_AT_KEY, SESSION_SUMMARY_KEY

    rows_payload = bundle.get("rows") or []
    if not rows_payload:
        return False

    restored_rows = [_row_from_dict(item) for item in rows_payload]
    st.session_state["portfolio_details_rows"] = (
        PortfolioDetailsService().enrich_rows_previous_close(restored_rows)
    )
    if bundle.get("attention_summary") is not None:
        st.session_state[SESSION_SUMMARY_KEY] = bundle["attention_summary"]
    if bundle.get("risk_checked_at"):
        st.session_state[SESSION_CHECKED_AT_KEY] = (
            _coerce_datetime(bundle["risk_checked_at"]) or bundle["risk_checked_at"]
        )
    details_time = _coerce_datetime(bundle.get("portfolio_details_time"))
    if details_time:
        st.session_state["portfolio_details_time"] = details_time
    st.session_state["portfolio_analysis_ready"] = bool(bundle.get("portfolio_analysis_ready"))
    st.session_state["portfolio_show_analysis"] = True
    try:
        from utils.portfolio_db import compute_portfolio_db_fingerprint

        st.session_state["_portfolio_db_fingerprint"] = bundle.get(
            "db_fingerprint"
        ) or compute_portfolio_db_fingerprint(use_cache=True)
    except (SQLiteError, PostgresError, OSError) as exc:
        logger.debug("Could not store portfolio DB fingerprint after hydrate: %s", exc)
    logger.info(
        "Portfolio UI cache loaded path=%s holdings=%d saved_at=%s",
        cache_path,
        len(rows_payload),
        bundle.get("saved_at", "?"),
    )
    _rebuild_risk_summary_if_needed()
    return True


def hydrate_session_from_disk() -> bool:  # noqa: C901
    """
    Restore portfolio session from disk if the in-memory session is empty.

    Returns True when holdings rows are available in session_state.
    """
    import streamlit as st

    from services.portfolio_session import is_demo_session, user_has_holdings_in_db

    if not is_demo_session() and not user_has_holdings_in_db():
        clear_session_cache()
        return False

    if st.session_state.get("portfolio_details_rows"):
        return True

    cache_path = _cache_path()
    if not cache_path.exists():
        if user_has_holdings_in_db():
            logger.info("No portfolio UI cache; loading holdings from DB/library.")
            return warm_portfolio_session_from_db()
        return False

    try:
        with cache_path.open("r", encoding="utf-8") as handle:
            bundle = json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not load portfolio UI cache: %s", exc)
        try:
            cache_path.unlink(missing_ok=True)
            logger.info("Removed corrupted portfolio UI cache file: %s", cache_path)
        except OSError:
            pass
        if user_has_holdings_in_db():
            logger.info("Portfolio UI cache corrupted; loading holdings from DB/library.")
            return warm_portfolio_session_from_db()
        return False

    rows_payload = bundle.get("rows") or []
    if not rows_payload:
        if user_has_holdings_in_db():
            logger.info("Portfolio UI cache empty; loading holdings from DB/library.")
            return warm_portfolio_session_from_db()
        return False

    fp_mismatch = False
    try:
        from utils.portfolio_db import compute_portfolio_db_fingerprint

        current_fp = compute_portfolio_db_fingerprint(use_cache=True)
        bundle_fp = bundle.get("db_fingerprint")
        if bundle_fp and bundle_fp != current_fp:
            fp_mismatch = True
            logger.info(
                "Portfolio UI cache fingerprint mismatch; showing cached rows "
                "and scheduling background refresh."
            )
            try:
                from services.deferred_startup import schedule_portfolio_refresh

                schedule_portfolio_refresh(live_prices=False)
            except (ImportError, AttributeError) as exc:
                logger.debug("Could not schedule portfolio refresh after mismatch: %s", exc)
    except (SQLiteError, PostgresError, OSError) as exc:
        logger.debug("Portfolio DB fingerprint check skipped during hydrate: %s", exc)

    if cache_is_stale(bundle) or fp_mismatch:
        if cache_is_stale(bundle):
            logger.info(
                "Portfolio UI cache stale (saved_at=%s); utilizing as "
                "fallback and scheduling background reload",
                bundle.get("saved_at", "?"),
            )
        st.session_state["_portfolio_stale_cache_loaded"] = True
        if cache_is_stale(bundle) and not fp_mismatch:
            try:
                from services.deferred_startup import schedule_library_reload_if_needed

                schedule_library_reload_if_needed()
            except (ImportError, AttributeError) as exc:
                logger.debug("Could not schedule library reload: %s", exc)

    return _apply_disk_bundle(bundle, cache_path=cache_path)


def _dividend_sync_meta_path() -> Path:
    return _cache_path().parent / "dividend_sync_at.txt"


def should_sync_dividends_on_startup() -> bool:
    """True when paid-dividend sync should run (not run on every Streamlit rerun)."""
    path = _dividend_sync_meta_path()
    if not path.is_file():
        return True
    try:
        saved = datetime.fromisoformat(path.read_text(encoding="utf-8").strip())
    except (ValueError, TypeError, OSError):
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


def warm_portfolio_session_from_db(*, preload_charts: bool = False, force: bool = False) -> bool:
    """
    Build holdings from the shared library without live prices when the session is empty.

    Returns True when rows were loaded into session_state.
    """
    import streamlit as st

    from services.portfolio_session import is_demo_session, user_has_holdings_in_db
    from ui.portfolio_risk_panel import store_portfolio_payload

    if st.session_state.get("portfolio_details_rows") and not force:
        return True
    if is_demo_session() or not user_has_holdings_in_db():
        return False

    try:
        from services.portfolio_details_service import PortfolioDetailsService

        rows, preload = PortfolioDetailsService().build_rows_with_cache(
            use_live_prices=False,
            preload_analysis=preload_charts,
        )
    except (SQLiteError, PostgresError, OSError, AttributeError) as exc:
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
    try:
        from utils.portfolio_db import compute_portfolio_db_fingerprint

        st.session_state["_portfolio_db_fingerprint"] = compute_portfolio_db_fingerprint(
            use_cache=False
        )
    except (SQLiteError, PostgresError, OSError) as exc:
        logger.debug("Could not store portfolio DB fingerprint after warm load: %s", exc)
    logger.info("Portfolio fast-loaded from library (%d holdings)", len(rows))
    _rebuild_risk_summary_if_needed()
    return True


def ensure_portfolio_session_loaded() -> bool:
    """
    Restore portfolio rows synchronously from disk or the shared library.

    Returns True when ``portfolio_details_rows`` is populated. Background jobs
    may still enrich prices and yield charts afterward.
    """
    import streamlit as st

    if hydrate_session_from_disk():
        return True
    return bool(st.session_state.get("portfolio_details_rows"))


def compute_yield_preload_payload(
    symbols: list[str],
    stock_cache: dict[str, Any],
    vector_docs: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Build yield-channel preload payload (safe to run off the UI thread)."""
    from services.portfolio_analysis_preload import preload_portfolio_analysis

    preload = preload_portfolio_analysis(
        symbols,
        stock_cache,
        dict(vector_docs),
        progress_callback=progress_callback,
    )
    return {
        "yield_channels": preload.yield_channels,
        "stock_data": preload.stock_data,
        "vector_docs": preload.vector_docs,
        "dividend_statuses": preload.dividend_statuses or {},
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
        "prices_only": False,
    }


def compute_live_prices_payload(
    *,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Refresh live quotes only — keeps existing yield-chart preload (background-safe)."""
    from services.portfolio_details_service import PortfolioDetailsService

    if progress_callback:
        progress_callback(0.1, "Fetching live prices…")
    rows, preload = PortfolioDetailsService().build_rows_with_cache(
        use_live_prices=True,
        preload_analysis=False,
    )
    if progress_callback:
        progress_callback(0.95, f"{len(rows)} holdings refreshed")
    return {
        "rows": rows,
        "preload": preload,
        "analysis_ready": False,
        "fast_loaded": False,
        "prices_only": True,
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
    st.session_state["portfolio_dividend_statuses"] = payload.get("dividend_statuses") or {}
    st.session_state["portfolio_analysis_ready"] = True
    st.session_state.pop("portfolio_fast_loaded", None)
    save_session_cache(force=True)
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
            with cache_path.open("r", encoding="utf-8") as handle:
                bundle = json.load(handle)
            if not cache_is_stale(bundle):
                return False
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Could not read portfolio UI cache for staleness check: %s", exc)
            clear_session_cache()

    try:
        from ui.portfolio_sidebar import _reload_live_data

        logger.info("Auto-reloading portfolio after market library update")
        _reload_live_data()
        st.session_state["_portfolio_library_sync_done"] = True
        return True
    except (ImportError, AttributeError) as exc:
        logger.warning("Auto portfolio reload failed: %s", exc)
        return False
