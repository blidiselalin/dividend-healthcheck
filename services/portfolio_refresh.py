"""
Invalidate Streamlit caches and reload portfolio session state after data changes.
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional, Set

import streamlit as st

from services.portfolio_analysis_preload import PortfolioAnalysisPreload
from services.portfolio_details_service import PortfolioDetailsService
from services.portfolio_management_service import SECTION_KEYS
from ui.portfolio_risk_panel import refresh_portfolio_risks, store_portfolio_payload

SectionKey = str


def invalidate_section_caches(sections: Iterable[SectionKey]) -> None:
    """Clear cached data for the given portfolio tabs (or 'all')."""
    wanted: Set[str] = set(sections)
    if "all" in wanted:
        wanted = set(SECTION_KEYS)

    if wanted & {"dividend_growth", "all"}:
        from ui.portfolio_details_view import _load_dividend_growth

        _load_dividend_growth.clear()

    if wanted & {"deposits", "all"}:
        from ui.portfolio_details_view import _load_benchmark_comparison

        _load_benchmark_comparison.clear()


def reload_portfolio_session(
    *,
    refresh_risks: bool = True,
    sections: Optional[Iterable[SectionKey]] = None,
) -> PortfolioAnalysisPreload:
    """Rebuild holdings rows and analysis preload after portfolio DB changes."""
    if sections:
        invalidate_section_caches(sections)
    else:
        invalidate_section_caches(["all"])

    rows, preload = PortfolioDetailsService().build_rows_with_cache()
    store_portfolio_payload(rows, preload)
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
            with st.spinner("Refreshing portfolio market data…"):
                reload_portfolio_session(sections=["all"])
        else:
            invalidate_section_caches([section, "all"])
        st.rerun()

    return _refresh
