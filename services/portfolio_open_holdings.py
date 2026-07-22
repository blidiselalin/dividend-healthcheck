"""
Active (open) portfolio positions — exclude fully sold names from analysis UI.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.portfolio_analysis_preload import PortfolioAnalysisPreload
    from services.portfolio_attention_service import AttentionItem, AttentionSummary
    from services.portfolio_details_service import PortfolioDetailRow
else:
    AttentionItem = object
    AttentionSummary = object


def open_portfolio_symbols(*, db_path: Path | None = None) -> set[str]:
    """Tickers with an open row in the holdings table."""
    from data_ingestion.portfolio_store import PortfolioStore

    store = PortfolioStore(db_path=db_path, seed=False) if db_path else PortfolioStore(seed=False)
    return {holding.symbol for holding in store.list_holdings() if holding.shares > 0}


def filter_open_portfolio_rows(
    rows: Sequence[PortfolioDetailRow],
    *,
    allowed_symbols: set[str] | None = None,
) -> list[PortfolioDetailRow]:
    """Keep only rows for symbols still held (positive share count)."""
    allowed = allowed_symbols if allowed_symbols is not None else open_portfolio_symbols()
    return [row for row in rows if row.ticker in allowed and row.shares > 0]


def filter_attention_summary(
    summary: AttentionSummary,
    *,
    allowed_symbols: set[str] | None = None,
) -> AttentionSummary:
    """Drop watchlist entries for symbols no longer held."""
    from services.portfolio_attention_service import AttentionSummary as Summary

    allowed = allowed_symbols if allowed_symbols is not None else open_portfolio_symbols()

    def _keep(item: AttentionItem) -> bool:
        return item.symbol in allowed

    return Summary(
        risk_items=[item for item in summary.risk_items if _keep(item)],
        opportunity_items=[item for item in summary.opportunity_items if _keep(item)],
        dividend_items=[item for item in summary.dividend_items if _keep(item)],
        reference_date=summary.reference_date,
    )


def trim_preload_for_symbols(
    preload: PortfolioAnalysisPreload,
    symbols: set[str],
) -> PortfolioAnalysisPreload:
    """Drop cached analysis payloads for symbols no longer in the portfolio."""
    return preload.for_symbols(symbols)
