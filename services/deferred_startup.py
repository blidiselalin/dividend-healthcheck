"""
Defer heavy startup work to background threads so the UI paints immediately.
"""

from __future__ import annotations

from sqlite3 import Error as SQLiteError
from typing import Any

try:
    from psycopg import Error as PostgresError
except ImportError:
    PostgresError = type("PostgresError", (Exception,), {})

from services.background_jobs import (
    ProgressCallback,
    apply_completed_jobs,
    has_active_jobs,
    list_jobs,
    session_scope,
    start_job,
)
from utils.logging_config import get_logger

logger = get_logger("dividendscope.deferred")

JOB_DIVIDEND_SYNC = "dividend_sync"
JOB_YIELD_PRELOAD = "yield_preload"
JOB_WARM_PORTFOLIO = "warm_portfolio"
JOB_LIVE_RELOAD = "live_reload"
JOB_COVERAGE_STATS = "coverage_stats"
JOB_HOURLY_UPDATE = "hourly_market_update"
JOB_HISTORY_BACKFILL = "history_backfill"
JOB_HISTORY_TABLE_SYNC = "history_table_sync"
JOB_ENSURE_SP500 = "ensure_sp500"
JOB_ENSURE_TOP_DIVIDEND = "ensure_top_dividend"
JOB_PRICE_REFRESH = "price_refresh"
JOB_PORTFOLIO_DB_REFRESH = "portfolio_db_refresh"


def apply_background_results() -> list[str]:
    """Merge completed background jobs into Streamlit session state."""
    import streamlit as st

    handlers = {
        JOB_DIVIDEND_SYNC: _apply_dividend_sync,
        JOB_YIELD_PRELOAD: _apply_yield_preload,
        JOB_WARM_PORTFOLIO: _apply_warm_portfolio,
        JOB_LIVE_RELOAD: _apply_live_reload,
        JOB_COVERAGE_STATS: _apply_coverage_stats,
        JOB_HOURLY_UPDATE: _apply_hourly_update,
        JOB_HISTORY_BACKFILL: _apply_history_backfill,
        JOB_HISTORY_TABLE_SYNC: _apply_history_table_sync,
        JOB_ENSURE_SP500: _apply_ensure_sp500,
        JOB_ENSURE_TOP_DIVIDEND: _apply_ensure_top_dividend,
        JOB_PRICE_REFRESH: _apply_price_refresh,
        JOB_PORTFOLIO_DB_REFRESH: _apply_portfolio_db_refresh,
    }
    applied_kinds = apply_completed_jobs(handlers)  # type: ignore[arg-type]
    if applied_kinds:
        st.session_state["_background_jobs_applied"] = True
    return applied_kinds


def _library_reload_needed() -> bool:
    import streamlit as st

    from services.portfolio_session import is_demo_session, user_has_holdings_in_db
    from services.portfolio_ui_cache import (
        _cache_path,
        cache_is_stale,
        clear_session_cache,
        market_library_latest_update,
    )

    if is_demo_session() or not user_has_holdings_in_db():
        return False
    if st.session_state.get("_portfolio_stale_cache_loaded"):
        return True
    if st.session_state.get("portfolio_details_rows"):
        return False
    if st.session_state.get("_portfolio_library_sync_done"):
        return False
    if market_library_latest_update() is None:
        return False

    cache_path = _cache_path()
    if not cache_path.is_file():
        return False
    try:
        import json

        with cache_path.open("r", encoding="utf-8") as handle:
            bundle = json.load(handle)
        return cache_is_stale(bundle)
    except (json.JSONDecodeError, OSError):
        clear_session_cache()
        return False


def schedule_startup_tasks(*, is_demo: bool, has_holdings: bool) -> None:
    """Queue startup jobs that should not block the first UI paint."""
    from services.background_task_prefs import auto_background_tasks_enabled

    if not auto_background_tasks_enabled():
        return

    if is_demo or not has_holdings:
        schedule_coverage_badge_refresh()
        return

    schedule_dividend_sync_if_needed()
    if _library_reload_needed():
        schedule_library_reload_if_needed()
    else:
        schedule_portfolio_warm_if_needed()
    schedule_yield_preload_if_needed()
    schedule_stale_price_refresh_if_needed()
    schedule_coverage_badge_refresh()
    schedule_auto_backfill_if_needed()


def schedule_dividend_sync_if_needed() -> None:
    from services.portfolio_ui_cache import should_sync_dividends_on_startup

    if not should_sync_dividends_on_startup():
        return

    def _worker(progress: ProgressCallback) -> Any:
        progress(0.05, "Scanning holdings…")
        from services.portfolio_dividend_sync_service import (
            maybe_sync_received_dividends,
        )

        stats = maybe_sync_received_dividends()
        progress(1.0, "Dividend sync complete")
        return stats

    start_job(JOB_DIVIDEND_SYNC, "Syncing received dividends", _worker)


def schedule_forced_dividend_sync() -> None:
    """Queue a non-skippable dividend sync."""

    def _worker(progress: ProgressCallback) -> Any:
        progress(0.05, "Scanning holdings…")
        from services.portfolio_dividend_sync_service import (
            maybe_sync_received_dividends,
        )

        stats = maybe_sync_received_dividends(force=True)
        progress(1.0, "Dividend sync complete")
        return stats

    start_job(JOB_DIVIDEND_SYNC, "Syncing received dividends", _worker)


def schedule_yield_preload_if_needed() -> None:
    import streamlit as st

    if st.session_state.get("portfolio_analysis_ready"):
        return
    if not st.session_state.get("portfolio_fast_loaded"):
        return
    if not st.session_state.get("portfolio_details_rows"):
        return

    rows = st.session_state.get("portfolio_details_rows") or []
    symbols = [row.ticker for row in rows]
    stock_cache = dict(st.session_state.get("portfolio_stock_cache") or {})
    vector_docs = dict(st.session_state.get("portfolio_vector_docs") or {})

    def _worker(progress: ProgressCallback) -> dict[str, Any]:
        from services.portfolio_ui_cache import compute_yield_preload_payload

        return compute_yield_preload_payload(
            symbols,
            stock_cache,
            vector_docs,
            progress_callback=progress,
        )

    start_job(JOB_YIELD_PRELOAD, "Loading yield charts", _worker)


def schedule_stale_price_refresh_if_needed() -> None:
    """Queue a live-price-only refresh when library quotes are stale."""
    import streamlit as st

    if not st.session_state.get("_stale_prices_pending"):
        rows = st.session_state.get("portfolio_details_rows") or []
        if not any(getattr(row, "price_stale", False) for row in rows):
            return

    if st.session_state.get("_deferred_price_refresh_scheduled"):
        return
    if not st.session_state.get("portfolio_details_rows"):
        return
    if (
        _job_running(JOB_LIVE_RELOAD)
        or _job_running(JOB_PORTFOLIO_DB_REFRESH)
        or _job_running(JOB_WARM_PORTFOLIO)
    ):
        return

    st.session_state["_deferred_price_refresh_scheduled"] = True
    st.session_state.pop("_stale_prices_pending", None)

    def _worker(progress: ProgressCallback) -> dict[str, Any]:
        from services.portfolio_ui_cache import compute_live_prices_payload

        progress(0.05, "Refreshing live prices…")
        payload = compute_live_prices_payload(progress_callback=progress)
        progress(1.0, "Prices updated")
        return payload

    start_job(JOB_LIVE_RELOAD, "Refreshing live prices", _worker)


def trigger_portfolio_load() -> str | None:
    """Manual: load or refresh portfolio rows from the shared library."""
    return schedule_portfolio_refresh(live_prices=False)


def trigger_yield_preload() -> None:
    """Manual: preload yield charts regardless of automatic-task preference."""
    import streamlit as st

    rows = st.session_state.get("portfolio_details_rows") or []
    if not rows:
        return
    if _job_running(JOB_YIELD_PRELOAD):
        return

    symbols = [row.ticker for row in rows]
    stock_cache = dict(st.session_state.get("portfolio_stock_cache") or {})
    vector_docs = dict(st.session_state.get("portfolio_vector_docs") or {})

    def _worker(progress: ProgressCallback) -> dict[str, Any]:
        from services.portfolio_ui_cache import compute_yield_preload_payload

        return compute_yield_preload_payload(
            symbols,
            stock_cache,
            vector_docs,
            progress_callback=progress,
        )

    start_job(JOB_YIELD_PRELOAD, "Loading yield charts", _worker)


def trigger_stale_price_refresh() -> None:
    """Manual: refresh holdings whose quotes are stale."""
    import streamlit as st

    st.session_state["_stale_prices_pending"] = True
    st.session_state.pop("_deferred_price_refresh_scheduled", None)
    schedule_stale_price_refresh_if_needed()


def trigger_portfolio_history_backfill() -> str | None:
    """Manual: backfill thin price/dividend history for current holdings."""
    import streamlit as st

    if _job_running(JOB_HISTORY_BACKFILL):
        return None
    rows = st.session_state.get("portfolio_details_rows") or []
    thin_symbols = [row.ticker for row in rows if getattr(row, "history_thin", False)]
    if not thin_symbols:
        thin_symbols = [row.ticker for row in rows]
    if not thin_symbols:
        return None

    limit = min(5, len(thin_symbols))
    symbols_to_backfill = thin_symbols[:limit]

    def _worker(progress: ProgressCallback) -> dict[str, Any]:
        from services.stock_history_backfill import backfill_thin_history

        return backfill_thin_history(
            limit=limit,
            symbols=symbols_to_backfill,
            progress_callback=progress,
            prioritize_portfolio=True,
        )

    return start_job(
        JOB_HISTORY_BACKFILL,
        "Updating history for portfolio holdings",
        _worker,
        admin_only=False,
    )


def schedule_portfolio_warm_if_needed() -> None:
    import streamlit as st

    from services.portfolio_session import is_demo_session, user_has_holdings_in_db

    if st.session_state.get("portfolio_details_rows"):
        return
    if is_demo_session() or not user_has_holdings_in_db():
        return
    if has_active_jobs(scope=session_scope()) and _job_running(JOB_WARM_PORTFOLIO):
        return

    def _worker(progress: ProgressCallback) -> dict[str, Any]:
        progress(0.05, "Loading holdings from library…")
        from services.portfolio_ui_cache import compute_fast_portfolio_payload

        payload = compute_fast_portfolio_payload(progress_callback=progress)
        progress(1.0, "Portfolio loaded")
        return payload

    start_job(JOB_WARM_PORTFOLIO, "Loading portfolio", _worker)


def schedule_portfolio_refresh(*, live_prices: bool = False) -> str | None:
    """
    Queue a portfolio reload after DB edits or fingerprint drift.

    Fast (library) reload by default; ``live_prices=True`` fetches live quotes + charts.
    """
    if live_prices:
        if _job_running(JOB_PORTFOLIO_DB_REFRESH) or _job_running(JOB_WARM_PORTFOLIO):
            return None
        return _start_live_reload_job(label="Refreshing live prices")

    if (
        _job_running(JOB_LIVE_RELOAD)
        or _job_running(JOB_WARM_PORTFOLIO)
        or _job_running(JOB_PORTFOLIO_DB_REFRESH)
    ):
        return None

    def _worker(progress: ProgressCallback) -> dict[str, Any]:
        progress(0.05, "Reading holdings from database…")
        from services.portfolio_ui_cache import compute_fast_portfolio_payload

        payload = compute_fast_portfolio_payload(progress_callback=progress)
        progress(1.0, "Portfolio updated")
        return payload

    return start_job(
        JOB_PORTFOLIO_DB_REFRESH,
        "Updating portfolio",
        _worker,
    )


def _start_live_reload_job(*, label: str = "Refreshing portfolio") -> str | None:
    def _worker(progress: ProgressCallback) -> dict[str, Any]:
        progress(0.05, "Fetching live prices…")
        from services.portfolio_ui_cache import compute_live_portfolio_payload

        payload = compute_live_portfolio_payload(progress_callback=progress)
        progress(1.0, "Live reload complete")
        return payload

    return start_job(JOB_LIVE_RELOAD, label, _worker)


def schedule_library_reload_if_needed() -> None:
    if not _library_reload_needed():
        return

    _start_live_reload_job(label="Refreshing after library update")


def schedule_coverage_badge_refresh() -> None:
    import streamlit as st

    status = st.session_state.get("market_db_status") or {}
    if status.get("sp500_coverage") is not None:
        return
    doc_count = int(status.get("document_count") or 0)
    if doc_count <= 0:
        return

    def _worker(progress: ProgressCallback) -> dict[str, Any]:
        progress(0.1, "Counting S&P coverage…")
        from services.sp500_peers_service import coverage_stats

        return coverage_stats()

    start_job(JOB_COVERAGE_STATS, "Updating library stats", _worker)


def schedule_auto_backfill_if_needed() -> str | None:
    """
    Auto-trigger a small backfill job when portfolio holdings have thin history.

    Unlike the admin-triggered ``schedule_history_backfill()``, this runs for any
    authenticated user and uses a small batch limit (5 symbols) so it does not
    compete with other startup tasks.  Controlled by ``AUTO_BACKFILL_ON_LOAD``
    (``DIVIDENDSCOPE_AUTO_BACKFILL_ON_LOAD=0`` to disable).
    """
    import streamlit as st

    from config import AUTO_BACKFILL_ON_LOAD

    if not AUTO_BACKFILL_ON_LOAD:
        return None
    if _job_running(JOB_HISTORY_BACKFILL):
        return None
    # Only run after the portfolio rows are available so we can inspect them.
    rows = st.session_state.get("portfolio_details_rows") or []
    thin_symbols = [row.ticker for row in rows if getattr(row, "history_thin", False)]
    if not thin_symbols:
        return None

    limit = min(5, len(thin_symbols))
    symbols_to_backfill = thin_symbols[:limit]

    def _worker(progress: ProgressCallback) -> dict[str, Any]:
        from services.stock_history_backfill import backfill_thin_history

        return backfill_thin_history(
            limit=limit,
            symbols=symbols_to_backfill,
            progress_callback=progress,
            prioritize_portfolio=True,
        )

    logger.info(
        "Auto-backfill scheduled for %d thin-history holding(s): %s",
        len(symbols_to_backfill),
        ", ".join(symbols_to_backfill),
    )
    return start_job(
        JOB_HISTORY_BACKFILL,
        "Updating history for portfolio holdings",
        _worker,
        admin_only=False,
    )


def schedule_history_backfill(*, limit: int = 40) -> str | None:
    """Admin-triggered backfill for thin price/dividend history."""
    from auth.user_context import is_app_admin

    if not is_app_admin():
        return None

    def _worker(progress: ProgressCallback) -> dict[str, Any]:
        from services.stock_history_backfill import backfill_thin_history

        return backfill_thin_history(limit=limit, progress_callback=progress)

    return start_job(
        JOB_HISTORY_BACKFILL,
        "Backfilling price/dividend history",
        _worker,
        admin_only=True,
    )


def schedule_history_table_sync(*, limit: int = 200) -> str | None:
    """Admin-triggered JSONB → normalized history table sync."""
    from auth.user_context import is_app_admin

    if not is_app_admin():
        return None

    def _worker(progress: ProgressCallback) -> dict[str, Any]:
        from db.postgres_market_history_store import PostgresMarketHistoryStore

        progress(0.05, "Finding symbols pending history sync…")
        stats = PostgresMarketHistoryStore().sync_pending_from_jsonb(limit=limit)
        progress(1.0, f"Synced {stats.get('synced', 0)} symbols")
        return stats

    return start_job(
        JOB_HISTORY_TABLE_SYNC,
        "Syncing history tables",
        _worker,
        admin_only=True,
    )


def schedule_hourly_market_update(*, enrich_limit: int = 40) -> str | None:
    """Admin-triggered hourly market refresh (prices + stale enrich)."""
    from auth.user_context import is_app_admin

    if not is_app_admin():
        return None

    def _worker(progress: ProgressCallback) -> dict[str, Any]:
        from services.hourly_market_update import run_hourly_market_update

        progress(0.05, "Refreshing prices…")
        summary = run_hourly_market_update(enrich_limit=enrich_limit)
        progress(1.0, "Market update complete")
        return summary

    return start_job(
        JOB_HOURLY_UPDATE,
        "Updating shared stock library",
        _worker,
        admin_only=True,
    )


def schedule_ensure_sp500(*, limit: int | None = None) -> str | None:
    """Admin-triggered ingest of missing S&P 500 symbols into analysed stocks."""
    from auth.user_context import is_app_admin

    if not is_app_admin():
        return None

    def _worker(progress: ProgressCallback) -> dict[str, Any]:
        from services.sp500_peers_service import (
            coverage_stats,
            ensure_sp500_in_vectordb,
        )

        def _cb(msg: str, current: int, total: int) -> None:
            progress(current / total if total else 0.05, msg)

        stats = ensure_sp500_in_vectordb(limit=limit, progress_callback=_cb)
        stats["coverage"] = coverage_stats(force=True)
        progress(1.0, "S&P 500 ingest complete")
        return stats

    return start_job(
        JOB_ENSURE_SP500,
        "Ensuring S&P 500 in library",
        _worker,
        admin_only=True,
    )


def schedule_ensure_top_dividend(*, limit: int | None = None) -> str | None:
    """Admin-triggered ingest of missing top-100 dividend symbols."""
    from auth.user_context import is_app_admin

    if not is_app_admin():
        return None

    def _worker(progress: ProgressCallback) -> dict[str, Any]:
        from services.sp500_peers_service import (
            ensure_top_dividend_in_vectordb,
            top_dividend_coverage_stats,
        )

        def _cb(msg: str, current: int, total: int) -> None:
            progress(current / total if total else 0.05, msg)

        stats = ensure_top_dividend_in_vectordb(limit=limit, progress_callback=_cb)
        stats["coverage"] = top_dividend_coverage_stats(force=True)
        progress(1.0, "Top dividend ingest complete")
        return stats

    return start_job(
        JOB_ENSURE_TOP_DIVIDEND,
        "Ensuring top dividend tickers",
        _worker,
        admin_only=True,
    )


def schedule_price_refresh() -> str | None:
    """On-demand price refresh for all library symbols (background thread)."""
    from auth.user_context import is_app_admin

    if not is_app_admin():
        return None

    def _worker(progress: ProgressCallback) -> dict[str, Any]:
        from services.price_refresh_scheduler import run_price_refresh_once

        progress(0.1, "Fetching live prices…")
        stats = run_price_refresh_once()
        progress(1.0, "Price refresh complete")
        return stats

    return start_job(
        JOB_PRICE_REFRESH,
        "Refreshing live prices",
        _worker,
        admin_only=True,
    )


def visible_jobs(*, admin: bool) -> list[Any]:
    jobs = list_jobs(include_finished=True)
    visible = []
    for job in jobs:
        if job.admin_only and not admin:
            continue
        if (
            job.status in ("queued", "running")
            or job.status == "done"
            and not job.applied
            or job.status == "error"
            and job.finished_at
            and not job.applied
        ):
            visible.append(job)
    return visible[-6:]


def _job_running(kind: str) -> bool:
    return any(
        job.kind == kind and job.status in ("queued", "running")
        for job in list_jobs(include_finished=False)
    )


def _apply_dividend_sync(result: Any) -> None:
    if result is None:
        return
    import streamlit as st

    receipts_updated = getattr(result, "receipts_updated", 0)
    pay_fixes = getattr(result, "pay_dates_corrected", 0)
    logger.info(
        (
            "Background dividend sync: holdings=%s, receipts_added=%s, "
            "receipts_updated=%s, pay_date_fixes=%s"
        ),
        getattr(result, "holdings_scanned", "?"),
        getattr(result, "receipts_added", "?"),
        receipts_updated,
        pay_fixes,
    )
    for key in ("_month_paid_cache", "_month_paid_cache_day", "_month_paid_cache_fp"):
        st.session_state.pop(key, None)
    try:
        from utils.portfolio_db import (
            compute_portfolio_db_fingerprint,
            invalidate_portfolio_db_fingerprint_cache,
        )

        invalidate_portfolio_db_fingerprint_cache()
        st.session_state["_portfolio_db_fingerprint"] = compute_portfolio_db_fingerprint(
            use_cache=False
        )
    except (SQLiteError, PostgresError, OSError) as exc:
        logger.debug("Could not refresh portfolio fingerprint after dividend sync: %s", exc)


def _apply_yield_preload(result: dict[str, Any]) -> None:
    import streamlit as st

    from services.portfolio_ui_cache import save_session_cache

    st.session_state["portfolio_yield_cache"] = result.get("yield_channels") or {}
    st.session_state["portfolio_stock_cache"] = result.get("stock_data") or {}
    st.session_state["portfolio_vector_docs"] = result.get("vector_docs") or {}
    st.session_state["portfolio_dividend_statuses"] = result.get("dividend_statuses") or {}
    st.session_state["portfolio_analysis_ready"] = True
    st.session_state.pop("portfolio_fast_loaded", None)
    save_session_cache(force=True)
    try:
        from ui.portfolio_risk_panel import _rebuild_attention_from_session

        _rebuild_attention_from_session()
    except (ImportError, AttributeError, KeyError) as exc:
        logger.debug("Risk watchlist rebuild after yield preload skipped: %s", exc)


def _apply_portfolio_db_refresh(result: dict[str, Any]) -> None:
    import streamlit as st

    from services.portfolio_ui_cache import save_session_cache
    from ui.portfolio_risk_panel import store_portfolio_payload

    rows = result.get("rows") or []
    preload = result.get("preload")
    if not rows or preload is None:
        return
    store_portfolio_payload(
        rows,
        preload,
        analysis_ready=bool(result.get("analysis_ready")),
    )
    if result.get("fast_loaded"):
        st.session_state["portfolio_fast_loaded"] = True
    try:
        from utils.portfolio_db import (
            compute_portfolio_db_fingerprint,
            invalidate_portfolio_db_fingerprint_cache,
        )

        invalidate_portfolio_db_fingerprint_cache()
        st.session_state["_portfolio_db_fingerprint"] = compute_portfolio_db_fingerprint(
            use_cache=False
        )
    except (SQLiteError, PostgresError, OSError) as exc:
        logger.debug("Could not store fingerprint after DB refresh: %s", exc)
    save_session_cache(force=True)
    from services.background_task_prefs import auto_background_tasks_enabled

    if auto_background_tasks_enabled():
        schedule_yield_preload_if_needed()
    logger.info("Background portfolio DB refresh: %d holdings", len(rows))


def _apply_warm_portfolio(result: dict[str, Any]) -> None:
    import streamlit as st

    from ui.portfolio_risk_panel import store_portfolio_payload

    rows = result.get("rows") or []
    preload = result.get("preload")
    if not rows or preload is None:
        return
    store_portfolio_payload(
        rows,
        preload,
        analysis_ready=bool(result.get("analysis_ready")),
    )
    if result.get("fast_loaded"):
        st.session_state["portfolio_fast_loaded"] = True
    logger.info("Background warm portfolio: %d holdings", len(rows))


def _apply_live_reload(result: dict[str, Any]) -> None:
    import streamlit as st

    from services.portfolio_analysis_preload import PortfolioAnalysisPreload
    from services.portfolio_ui_cache import save_session_cache
    from ui.portfolio_risk_panel import refresh_portfolio_risks, store_portfolio_payload

    rows = result.get("rows") or []
    preload = result.get("preload")
    if not rows or preload is None:
        return

    if result.get("prices_only"):
        from datetime import datetime

        existing_yield = st.session_state.get("portfolio_yield_cache") or {}
        existing_docs = st.session_state.get("portfolio_vector_docs") or {}
        merged_preload = PortfolioAnalysisPreload(
            stock_data={
                **dict(st.session_state.get("portfolio_stock_cache") or {}),
                **preload.stock_data,
            },
            yield_channels=existing_yield,
            vector_docs={**existing_docs, **preload.vector_docs},
            dividend_statuses={
                **dict(st.session_state.get("portfolio_dividend_statuses") or {}),
                **dict(preload.dividend_statuses or {}),
            },
        )
        st.session_state["portfolio_details_rows"] = rows
        st.session_state["portfolio_stock_cache"] = merged_preload.stock_data
        st.session_state["portfolio_vector_docs"] = merged_preload.vector_docs
        st.session_state["portfolio_dividend_statuses"] = merged_preload.dividend_statuses or {}
        st.session_state["portfolio_details_time"] = datetime.now()
        refresh_portfolio_risks(force=False, rows=rows, preload=merged_preload)
        save_session_cache(force=True)
        logger.info("Background price refresh: %d holdings", len(rows))
        return

    analysis_ready = bool(result.get("analysis_ready", True))
    store_portfolio_payload(rows, preload, analysis_ready=analysis_ready)
    refresh_portfolio_risks(force=True, rows=rows, preload=preload)
    st.session_state["_portfolio_library_sync_done"] = True
    st.session_state.pop("portfolio_fast_loaded", None)
    st.session_state.pop("_portfolio_stale_cache_loaded", None)
    try:
        from utils.portfolio_db import (
            compute_portfolio_db_fingerprint,
            invalidate_portfolio_db_fingerprint_cache,
        )

        invalidate_portfolio_db_fingerprint_cache()
        st.session_state["_portfolio_db_fingerprint"] = compute_portfolio_db_fingerprint(
            use_cache=False
        )
    except (SQLiteError, PostgresError, OSError) as exc:
        logger.debug("Could not store fingerprint after live reload: %s", exc)
    save_session_cache(force=True)
    logger.info("Background live reload: %d holdings", len(rows))


def _apply_coverage_stats(result: dict[str, Any]) -> None:
    import streamlit as st

    status = dict(st.session_state.get("market_db_status") or {})
    status["sp500_coverage"] = result
    st.session_state["market_db_status"] = status


def _apply_history_table_sync(result: dict[str, Any]) -> None:
    import streamlit as st

    st.session_state["last_history_table_sync_summary"] = result
    try:
        from ui.market_library_cache import clear_thin_history_summary_cache

        clear_thin_history_summary_cache()
    except (ImportError, AttributeError):  # noqa: S110
        pass
    logger.info(
        "Background history table sync: synced=%s pending=%s",
        result.get("synced"),
        result.get("pending"),
    )


def _apply_history_backfill(result: dict[str, Any]) -> None:
    import streamlit as st

    st.session_state["last_history_backfill_summary"] = result
    try:
        from ui.portfolio_details_view import _load_dividend_growth

        _load_dividend_growth.clear()
    except (ImportError, AttributeError):  # noqa: S110
        pass
    try:
        from ui.market_library_cache import clear_thin_history_summary_cache

        clear_thin_history_summary_cache()
    except (ImportError, AttributeError):  # noqa: S110
        pass
    logger.info(
        "Background history backfill: enriched=%s ready=%s",
        result.get("enriched"),
        result.get("ready_after"),
    )


def _apply_hourly_update(result: dict[str, Any]) -> None:
    import streamlit as st

    st.session_state["last_hourly_update_summary"] = result
    enrich = (result or {}).get("enrich") or {}
    logger.info(
        "Background hourly update: enriched=%s processed=%s",
        enrich.get("enriched"),
        enrich.get("processed"),
    )


def _apply_ensure_sp500(result: dict[str, Any]) -> None:
    import streamlit as st

    from services.shared_market_db import reset_shared_vector_store_cache

    st.session_state["last_ensure_sp500_summary"] = result
    reset_shared_vector_store_cache()
    coverage = (result or {}).get("coverage")
    if coverage:
        status = dict(st.session_state.get("market_db_status") or {})
        status["sp500_coverage"] = coverage
        st.session_state["market_db_status"] = status
    logger.info(
        "Background ensure S&P 500: created=%s errors=%s",
        (result or {}).get("created"),
        (result or {}).get("errors"),
    )


def _apply_ensure_top_dividend(result: dict[str, Any]) -> None:
    import streamlit as st

    from services.shared_market_db import reset_shared_vector_store_cache

    st.session_state["last_ensure_top_dividend_summary"] = result
    reset_shared_vector_store_cache()
    coverage = (result or {}).get("coverage")
    if coverage:
        status = dict(st.session_state.get("market_db_status") or {})
        status["top_dividend_coverage"] = coverage
        st.session_state["market_db_status"] = status
    logger.info(
        "Background ensure top dividend: created=%s errors=%s",
        (result or {}).get("created"),
        (result or {}).get("errors"),
    )


def _apply_price_refresh(result: dict[str, Any]) -> None:
    import streamlit as st

    st.session_state["last_price_refresh_summary"] = result
    logger.info(
        "Background price refresh: updated=%s skipped=%s errors=%s",
        (result or {}).get("updated"),
        (result or {}).get("skipped"),
        (result or {}).get("errors"),
    )
