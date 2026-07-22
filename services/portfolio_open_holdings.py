"""
Active (open) portfolio positions — exclude fully sold names from analysis UI.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data_ingestion.purchase_journal_store import PurchaseRecord
    from services.portfolio_analysis_preload import PortfolioAnalysisPreload
    from services.portfolio_attention_service import AttentionItem, AttentionSummary
    from services.portfolio_details_service import PortfolioDetailRow
else:
    AttentionItem = object
    AttentionSummary = object
    PurchaseRecord = object


def net_shares_for_symbol(records: Sequence[PurchaseRecord], symbol: str) -> float | None:
    """
    Net share balance from explicit buy/sell journal rows.

    Returns None when the symbol has no share-aware journal entries.
    """
    symbol_records = [record for record in records if record.symbol == symbol.upper()]
    if not symbol_records:
        return None
    if not any(record.shares is not None and record.shares > 0 for record in symbol_records):
        return None
    from services.portfolio_monthly_valuation import shares_from_records

    return shares_from_records(list(symbol_records), date.max)


def reconcile_closed_holdings(*, db_path: Path | None = None) -> list[str]:
    """
    Drop holdings with zero shares or a fully sold share-aware journal balance.

    Journal rows are kept for historical views.
    """
    from services.portfolio_context import create_portfolio_context

    ctx = create_portfolio_context(db_path=db_path)
    records = ctx.journal.list_purchases(portfolio_only=False)
    dropped: list[str] = []
    for holding in list(ctx.portfolio.list_holdings()):
        symbol = holding.symbol
        if holding.shares <= 0:
            ctx.portfolio.drop_holding(symbol)
            dropped.append(symbol)
            continue
        net = net_shares_for_symbol(records, symbol)
        if net is not None and net <= 0:
            ctx.portfolio.drop_holding(symbol)
            dropped.append(symbol)
    return dropped


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
