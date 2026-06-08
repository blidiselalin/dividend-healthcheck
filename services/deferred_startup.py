"""
Defer heavy startup work to background threads so the UI paints immediately.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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


def apply_background_results() -> bool:
    """Merge completed background jobs into Streamlit session state."""
    import streamlit as st

    handlers = {
        JOB_DIVIDEND_SYNC: _apply_dividend_sync,
        JOB_YIELD_PRELOAD: _apply_yield_preload,
        JOB_WARM_PORTFOLIO: _apply_warm_portfolio,
        JOB_LIVE_RELOAD: _apply_live_reload,
        JOB_COVERAGE_STATS: _apply_coverage_stats,
        JOB_HOURLY_UPDATE: _apply_hourly_update,
    }
    applied = apply_completed_jobs(handlers)
    if applied:
        st.session_state["_background_jobs_applied"] = True
    return applied


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
        import pickle

        with cache_path.open("rb") as handle:
            bundle = pickle.load(handle)
        return cache_is_stale(bundle)
    except Exception:
        clear_session_cache()
        return False


def schedule_startup_tasks(*, is_demo: bool, has_holdings: bool) -> None:
    """Queue startup jobs that should not block the first UI paint."""
    if is_demo or not has_holdings:
        schedule_coverage_badge_refresh()
        return

    schedule_dividend_sync_if_needed()
    if _library_reload_needed():
        schedule_library_reload_if_needed()
    else:
        schedule_portfolio_warm_if_needed()
    schedule_yield_preload_if_needed()
    schedule_coverage_badge_refresh()


def schedule_dividend_sync_if_needed() -> None:
    from services.portfolio_ui_cache import should_sync_dividends_on_startup

    if not should_sync_dividends_on_startup():
        return

    def _worker(progress: ProgressCallback) -> Any:
        progress(0.05, "Scanning holdings…")
        from services.portfolio_dividend_sync_service import maybe_sync_received_dividends

        stats = maybe_sync_received_dividends()
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

    def _worker(progress: ProgressCallback) -> Dict[str, Any]:
        from services.portfolio_ui_cache import compute_yield_preload_payload

        return compute_yield_preload_payload(
            symbols,
            stock_cache,
            vector_docs,
            progress_callback=progress,
        )

    start_job(JOB_YIELD_PRELOAD, "Loading yield charts", _worker)


def schedule_portfolio_warm_if_needed() -> None:
    import streamlit as st

    from services.portfolio_session import is_demo_session, user_has_holdings_in_db

    if st.session_state.get("portfolio_details_rows"):
        return
    if is_demo_session() or not user_has_holdings_in_db():
        return
    if has_active_jobs(scope=session_scope()) and _job_running(JOB_WARM_PORTFOLIO):
        return

    def _worker(progress: ProgressCallback) -> Dict[str, Any]:
        progress(0.05, "Loading holdings from library…")
        from services.portfolio_ui_cache import compute_fast_portfolio_payload

        payload = compute_fast_portfolio_payload(progress_callback=progress)
        progress(1.0, "Portfolio loaded")
        return payload

    start_job(JOB_WARM_PORTFOLIO, "Loading portfolio", _worker)


def schedule_library_reload_if_needed() -> None:
    if not _library_reload_needed():
        return

    def _worker(progress: ProgressCallback) -> Dict[str, Any]:
        progress(0.05, "Reloading after library update…")
        from services.portfolio_ui_cache import compute_live_portfolio_payload

        payload = compute_live_portfolio_payload(progress_callback=progress)
        progress(1.0, "Live reload complete")
        return payload

    start_job(JOB_LIVE_RELOAD, "Refreshing portfolio", _worker)


def schedule_coverage_badge_refresh() -> None:
    import streamlit as st

    status = st.session_state.get("market_db_status") or {}
    if status.get("sp500_coverage") is not None:
        return
    doc_count = int(status.get("document_count") or 0)
    if doc_count <= 0:
        return

    def _worker(progress: ProgressCallback) -> Dict[str, Any]:
        progress(0.1, "Counting S&P coverage…")
        from services.sp500_peers_service import coverage_stats

        return coverage_stats()

    start_job(JOB_COVERAGE_STATS, "Updating library stats", _worker)


def schedule_hourly_market_update(*, enrich_limit: int = 40) -> Optional[str]:
    """Admin-triggered hourly market refresh (prices + stale enrich)."""
    from auth.user_context import is_app_admin

    if not is_app_admin():
        return None

    def _worker(progress: ProgressCallback) -> Dict[str, Any]:
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


def visible_jobs(*, admin: bool) -> List:
    jobs = list_jobs(include_finished=True)
    visible = []
    for job in jobs:
        if job.admin_only and not admin:
            continue
        if job.status in ("queued", "running"):
            visible.append(job)
        elif job.status == "done" and not job.applied:
            visible.append(job)
        elif job.status == "error" and job.finished_at:
            visible.append(job)
    return visible[-6:]


def _job_running(kind: str) -> bool:
    return any(job.kind == kind and job.status in ("queued", "running") for job in list_jobs(include_finished=False))


def _apply_dividend_sync(result: Any) -> None:
    if result is None:
        return
    logger.info(
        "Background dividend sync: holdings=%s receipts=%s",
        getattr(result, "holdings_scanned", "?"),
        getattr(result, "receipts_added", "?"),
    )


def _apply_yield_preload(result: Dict[str, Any]) -> None:
    import streamlit as st

    from services.portfolio_ui_cache import save_session_cache

    st.session_state["portfolio_yield_cache"] = result.get("yield_channels") or {}
    st.session_state["portfolio_stock_cache"] = result.get("stock_data") or {}
    st.session_state["portfolio_vector_docs"] = result.get("vector_docs") or {}
    st.session_state["portfolio_analysis_ready"] = True
    st.session_state.pop("portfolio_fast_loaded", None)
    save_session_cache()


def _apply_warm_portfolio(result: Dict[str, Any]) -> None:
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


def _apply_live_reload(result: Dict[str, Any]) -> None:
    import streamlit as st

    from ui.portfolio_risk_panel import refresh_portfolio_risks, store_portfolio_payload

    rows = result.get("rows") or []
    preload = result.get("preload")
    if not rows or preload is None:
        return
    store_portfolio_payload(rows, preload, analysis_ready=True)
    refresh_portfolio_risks(force=True, rows=rows, preload=preload)
    st.session_state["_portfolio_library_sync_done"] = True
    st.session_state.pop("portfolio_fast_loaded", None)
    logger.info("Background live reload: %d holdings", len(rows))


def _apply_coverage_stats(result: Dict[str, Any]) -> None:
    import streamlit as st

    status = dict(st.session_state.get("market_db_status") or {})
    status["sp500_coverage"] = result
    st.session_state["market_db_status"] = status


def _apply_hourly_update(result: Dict[str, Any]) -> None:
    import streamlit as st

    st.session_state["last_hourly_update_summary"] = result
    enrich = (result or {}).get("enrich") or {}
    logger.info(
        "Background hourly update: enriched=%s processed=%s",
        enrich.get("enriched"),
        enrich.get("processed"),
    )
