"""
Invalidate Streamlit caches and reload portfolio session state after data changes.
"""

from __future__ import annotations

from collections.abc import Iterable
from sqlite3 import Error as SQLiteError
from typing import Callable

try:
    from psycopg import Error as PostgresError
except ImportError:
    PostgresError = type("PostgresError", (Exception,), {})

import streamlit as st

from services.deferred_startup import (
    schedule_forced_dividend_sync,
    schedule_portfolio_refresh,
)
from services.portfolio_analysis_preload import PortfolioAnalysisPreload
from services.portfolio_details_service import PortfolioDetailsService
from services.portfolio_management_service import SECTION_KEYS
from services.portfolio_ui_cache import clear_session_cache
from ui.portfolio_risk_panel import refresh_portfolio_risks, store_portfolio_payload
from utils.logging_config import get_logger

logger = get_logger("dividendscope.portfolio")

SectionKey = str


def invalidate_section_caches(sections: Iterable[SectionKey]) -> None:
    """Clear cached data for the given portfolio tabs (or 'all')."""
    wanted: set[str] = set(sections)
    if "all" in wanted:
        wanted = set(SECTION_KEYS)

    if wanted & {"dividend_growth", "all"}:
        from ui.portfolio_details_view import _load_dividend_growth

        _load_dividend_growth.clear()

    if wanted & {"deposits", "all"}:
        from ui.portfolio_details_view import _load_benchmark_comparison

        _load_benchmark_comparison.clear()


def schedule_portfolio_reload(
    *,
    live_prices: bool = False,
    sections: Iterable[SectionKey] | None = None,
) -> None:
    """Queue a non-blocking portfolio reload (library or live prices)."""
    if sections:
        invalidate_section_caches(sections)
    else:
        invalidate_section_caches(["all"])

    schedule_portfolio_refresh(live_prices=live_prices)


def reload_portfolio_session(
    *,
    refresh_risks: bool = True,
    sections: Iterable[SectionKey] | None = None,
) -> PortfolioAnalysisPreload:
    """
    Synchronous rebuild of holdings rows and analysis preload.

    Prefer ``schedule_portfolio_reload`` in UI code so the app stays responsive.
    """
    if sections:
        invalidate_section_caches(sections)
    else:
        invalidate_section_caches(["all"])

    logger.info("Portfolio reload started (refresh_risks=%s)", refresh_risks)
    clear_session_cache()
    schedule_forced_dividend_sync()
    rows, preload = PortfolioDetailsService().build_rows_with_cache(
        use_live_prices=True,
        preload_analysis=True,
    )
    store_portfolio_payload(rows, preload)
    try:
        from utils.portfolio_db import compute_portfolio_db_fingerprint

        st.session_state["_portfolio_db_fingerprint"] = compute_portfolio_db_fingerprint(
            use_cache=False
        )
    except (SQLiteError, PostgresError, OSError) as exc:
        logger.debug("Could not store portfolio DB fingerprint after reload: %s", exc)
    logger.info("Portfolio reload finished (%d holdings)", len(rows))
    if refresh_risks:
        refresh_portfolio_risks(force=True, rows=rows, preload=preload)
    return preload


def make_section_refresher(section: SectionKey) -> Callable[[], None]:
    """Return a callback for per-tab Update buttons."""

    def _refresh() -> None:
        needs_full_reload = section in {
            "dashboard",
            "dividends",
            "holdings",
            "all",
        }
        if needs_full_reload:
            schedule_portfolio_reload(live_prices=True, sections=["all"])
        else:
            invalidate_section_caches([section, "all"])
        st.rerun()

    return _refresh
