"""
Consolidated admin console — market library, history pipelines, and database tools.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

import streamlit as st

from auth.user_context import is_app_admin
from db.connection import use_cloud_sql
from services.deferred_startup import (
    apply_background_results,
    schedule_ensure_sp500,
    schedule_ensure_top_dividend,
    schedule_history_backfill,
    schedule_history_table_sync,
    schedule_hourly_market_update,
    schedule_price_refresh,
    visible_jobs,
)
from ui.market_library_cache import cached_thin_history_summary, clear_thin_history_summary_cache
from services.price_refresh_scheduler import scheduler_status
from services.shared_market_db import shared_market_db_status
from services.sp500_peers_service import coverage_stats, top_dividend_coverage_stats
from ui.db_admin_panel import render_database_admin_tabs
from ui.theme import render_notice, render_page_header

_ADMIN_VIEW_KEY = "admin_console_active"


def is_admin_console_active() -> bool:
    return bool(st.session_state.get(_ADMIN_VIEW_KEY))


def set_admin_console_active(active: bool) -> None:
    st.session_state[_ADMIN_VIEW_KEY] = active


def render_admin_sidebar_entry() -> None:
    """Single sidebar entry for admins (replaces scattered admin controls)."""
    if not is_app_admin():
        return

    st.sidebar.divider()
    st.sidebar.markdown(
        '<p class="ds-sidebar-heading">Administration</p>',
        unsafe_allow_html=True,
    )
    if is_admin_console_active():
        if st.sidebar.button(
            "← Back to portfolio",
            use_container_width=True,
            key="admin_console_back",
        ):
            set_admin_console_active(False)
            st.rerun()
    elif st.sidebar.button(
        "Open admin console",
        use_container_width=True,
        type="secondary",
        key="admin_console_open",
    ):
        set_admin_console_active(True)
        st.rerun()


def render_admin_page_if_active() -> bool:
    """Render the admin console in the main panel. Returns True when shown."""
    if not is_admin_console_active():
        return False
    if not is_app_admin():
        set_admin_console_active(False)
        return False

    _inject_admin_styles()
    render_page_header(
        title="Admin console",
        subtitle="Shared market library, history pipelines, and database inspection",
    )
    _render_status_metrics()
    _render_background_jobs_panel()

    tab_overview, tab_library, tab_history, tab_database = st.tabs(
        [
            "Overview",
            "Market library",
            "History & yield",
            "Database",
        ]
    )

    with tab_overview:
        _render_overview_tab()

    with tab_library:
        _render_market_library_tab()

    with tab_history:
        _render_history_tab()

    with tab_database:
        render_database_admin_tabs()

    return True


def _inject_admin_styles() -> None:
    st.markdown(
        """
        <style>
        .ds-admin-card {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 1rem 1.1rem;
            margin-bottom: 0.75rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        .ds-admin-card h4 {
            margin: 0 0 0.35rem 0;
            font-size: 1rem;
            color: #0f172a;
        }
        .ds-admin-card p {
            margin: 0;
            font-size: 0.88rem;
            color: #64748b;
            line-height: 1.45;
        }
        .ds-admin-kpi {
            background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 0.65rem 0.85rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _library_status() -> Dict[str, Any]:
    status = dict(st.session_state.get("market_db_status") or {})
    if not status.get("document_count"):
        try:
            status = shared_market_db_status(include_coverage=True)
            st.session_state["market_db_status"] = status
        except Exception:
            status = {}
    return status


def _render_status_metrics() -> None:
    status = _library_status()
    doc_count = int(status.get("document_count") or 0)
    sp_cov = status.get("sp500_coverage") or coverage_stats()
    top_cov = status.get("top_dividend_coverage") or top_dividend_coverage_stats()

    try:
        thin = cached_thin_history_summary()
        yield_ready = thin.get("yield_ready", 0)
        thin_count = thin.get("thin_history", 0)
        total_symbols = thin.get("total", 0)
    except Exception:
        yield_ready = thin_count = total_symbols = 0

    storage = "PostgreSQL" if use_cloud_sql() else "Local library"
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Library documents", f"{doc_count:,}")
    c2.metric(
        "S&P 500 coverage",
        f"{sp_cov.get('analysed_sp500', 0)}/{sp_cov.get('universe_total', 0)}",
        f"{sp_cov.get('pct_covered', 0):.0f}%",
    )
    c3.metric(
        "Top dividend coverage",
        f"{top_cov.get('analysed_top_dividend', 0)}/{top_cov.get('universe_total', 0)}",
        f"{top_cov.get('pct_covered', 0):.0f}%",
    )
    c4.metric("Yield-ready symbols", f"{yield_ready}/{total_symbols or '—'}")
    c5.metric("Need backfill", thin_count)
    st.caption(f"Storage: **{storage}** · Jobs run in the background so the portfolio UI stays responsive.")


@st.fragment(run_every=timedelta(seconds=2))
def _admin_jobs_fragment() -> None:
    applied = apply_background_results()
    jobs = visible_jobs(admin=True)
    if not jobs and not applied:
        st.caption("No admin background jobs running.")
        return

    for job in jobs:
        label = job.label
        if job.message:
            label = f"{job.label} — {job.message}"
        if job.status == "error":
            st.error(f"{job.label}: {job.error or 'failed'}")
        elif job.status in ("queued", "running"):
            st.progress(job.progress, text=label)
        elif job.status == "done":
            st.success(f"{label} ✓")

    if applied:
        clear_thin_history_summary_cache()
        st.rerun()


def _render_background_jobs_panel() -> None:
    with st.expander("Background jobs", expanded=True):
        _admin_jobs_fragment()


def _render_overview_tab() -> None:
    render_notice(
        "Use **Market library** to ingest missing S&P 500 and top dividend tickers. "
        "Use **History & yield** before troubleshooting empty yield charts. "
        "Use **Database** for read-only validation and SQL probes.",
        kind="info",
    )

    summaries = [
        ("Last price refresh", st.session_state.get("last_price_refresh_summary")),
        ("Last library update", st.session_state.get("last_hourly_update_summary")),
        ("Last S&P 500 ingest", st.session_state.get("last_ensure_sp500_summary")),
        ("Last top dividend ingest", st.session_state.get("last_ensure_top_dividend_summary")),
        ("Last history backfill", st.session_state.get("last_history_backfill_summary")),
        ("Last history table sync", st.session_state.get("last_history_table_sync_summary")),
    ]
    rows = []
    for label, payload in summaries:
        if not payload:
            continue
        rows.append({"Task": label, "Summary": _format_job_summary(payload)})

    if rows:
        st.markdown("#### Recent admin runs")
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.caption("Completed admin job summaries will appear here after the first run.")


def _format_job_summary(payload: Dict[str, Any]) -> str:
    if not payload:
        return "—"
    parts = []
    for key in ("created", "enriched", "synced", "processed", "errors", "ready_after"):
        if key in payload and payload[key] is not None:
            parts.append(f"{key}={payload[key]}")
    coverage = payload.get("coverage")
    if isinstance(coverage, dict):
        if "analysed_sp500" in coverage:
            parts.append(
                f"sp500={coverage.get('analysed_sp500')}/{coverage.get('universe_total')}"
            )
        if "analysed_top_dividend" in coverage:
            parts.append(
                f"top_div={coverage.get('analysed_top_dividend')}/{coverage.get('universe_total')}"
            )
    enrich = payload.get("enrich")
    if isinstance(enrich, dict) and enrich.get("enriched") is not None:
        parts.append(f"enriched={enrich.get('enriched')}")
    return ", ".join(parts) if parts else str(payload)[:120]


def _render_market_library_tab() -> None:
    refresh_status = scheduler_status()
    if refresh_status.get("running"):
        last_run = refresh_status.get("last_run_at") or "not yet"
        st.caption(
            f"Automatic price refresh every **{refresh_status.get('interval_seconds', 300) // 60} minutes** "
            f"(last run: {last_run})."
        )
    else:
        st.caption(
            "Automatic price refresh is disabled in this process "
            "(set `DIVIDENDSCOPE_DISABLE_PRICE_SCHEDULER=0` to enable)."
        )

    st.markdown(
        """
        <div class="ds-admin-card">
            <h4>Shared analysed-stocks library</h4>
            <p>Populate and refresh the shared S&P library used by every user for charts, peers, and portfolio analysis.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_refresh, col_prices, col_sp, col_top = st.columns(4)

    with col_refresh:
        st.markdown("**Update stock library**")
        st.caption("Refresh prices and enrich stale symbols (hourly-style pass).")
        enrich_limit = st.number_input(
            "Enrich limit",
            min_value=5,
            max_value=200,
            value=40,
            step=5,
            key="admin_enrich_limit",
        )
        if st.button("Run library update", type="primary", key="admin_run_hourly"):
            job_id = schedule_hourly_market_update(enrich_limit=int(enrich_limit))
            st.toast("Library update started" if job_id else "Update already running")
            st.rerun()

    with col_prices:
        st.markdown("**Refresh prices now**")
        st.caption("Live quotes only — same pass as the 5-minute scheduler.")
        if st.button("Refresh prices", key="admin_run_prices"):
            job_id = schedule_price_refresh()
            st.toast("Price refresh started" if job_id else "Refresh already running")
            st.rerun()
        last_prices = refresh_status.get("last_stats") or {}
        if last_prices.get("updated") is not None:
            st.caption(
                f"Last auto: **{last_prices.get('updated')}** updated · "
                f"{last_prices.get('errors', 0)} errors"
            )

    with col_sp:
        st.markdown("**Ensure S&P 500**")
        st.caption("Fetch and enrich any missing S&P 500 constituents.")
        sp_limit = st.number_input(
            "Max new tickers (0 = all missing)",
            min_value=0,
            max_value=503,
            value=0,
            step=10,
            key="admin_sp500_limit",
        )
        if st.button("Ensure S&P 500", key="admin_run_sp500"):
            limit = int(sp_limit) or None
            job_id = schedule_ensure_sp500(limit=limit)
            st.toast("S&P 500 ingest started" if job_id else "Job already running")
            st.rerun()

    with col_top:
        st.markdown("**Ensure top 100 dividend**")
        st.caption("Aristocrats + quality supplemental payers from the curated list.")
        top_limit = st.number_input(
            "Max new tickers (0 = all missing)",
            min_value=0,
            max_value=100,
            value=0,
            step=5,
            key="admin_top_div_limit",
        )
        if st.button("Ensure top dividend", key="admin_run_top_div"):
            limit = int(top_limit) or None
            job_id = schedule_ensure_top_dividend(limit=limit)
            st.toast("Top dividend ingest started" if job_id else "Job already running")
            st.rerun()

    st.divider()
    st.markdown("**CLI equivalents**")
    st.code(
        "python ingest_data.py --refresh-prices\n"
        "python ingest_data.py --ensure-sp500\n"
        "python ingest_data.py --ensure-top-dividend\n"
        "python ingest_data.py --enrich-existing",
        language="bash",
    )


def _render_history_tab() -> None:
    st.markdown(
        """
        <div class="ds-admin-card">
            <h4>Price &amp; dividend history</h4>
            <p>Backfill thin JSONB history, then sync into normalized tables for database-first yield charts.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        thin = cached_thin_history_summary()
        if thin.get("thin_history"):
            render_notice(
                f"**{thin['thin_history']}** symbols need backfill · "
                f"**{thin['yield_ready']}/{thin['total']}** yield-ready in the library.",
                kind="warning",
            )
    except Exception:
        pass

    col_backfill, col_sync = st.columns(2)

    with col_backfill:
        st.markdown("**Backfill thin history**")
        st.caption("Fetch missing price/dividend series into stock_documents.")
        backfill_limit = st.number_input(
            "Symbol limit",
            min_value=5,
            max_value=200,
            value=40,
            step=5,
            key="admin_backfill_limit",
        )
        if st.button("Start backfill", type="primary", key="admin_run_backfill"):
            job_id = schedule_history_backfill(limit=int(backfill_limit))
            st.toast("Backfill started" if job_id else "Backfill already running")
            st.rerun()

    with col_sync:
        st.markdown("**Sync history tables**")
        st.caption("Copy JSONB arrays into stock_price_history / stock_dividend_history.")
        sync_limit = st.number_input(
            "Symbol limit",
            min_value=10,
            max_value=500,
            value=200,
            step=10,
            key="admin_sync_limit",
        )
        if st.button("Start table sync", key="admin_run_sync"):
            job_id = schedule_history_table_sync(limit=int(sync_limit))
            st.toast("Table sync started" if job_id else "Sync already running")
            st.rerun()

    last_backfill = st.session_state.get("last_history_backfill_summary")
    last_sync = st.session_state.get("last_history_table_sync_summary")
    if last_backfill or last_sync:
        st.markdown("#### Last results")
        if last_backfill:
            st.json({"backfill": last_backfill})
        if last_sync:
            st.json({"table_sync": last_sync})
