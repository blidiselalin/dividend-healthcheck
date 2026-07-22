"""
Preload dividend charts and vector DB history for portfolio holdings.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

ProgressCallback = Callable[[float, str], None]

if TYPE_CHECKING:
    from data_ingestion.models import StockDocument
    from models.stock import StockData
    from services.yield_channel_chart import YieldChannelData


@dataclass(frozen=True)
class PortfolioAnalysisPreload:
    """In-memory analysis payloads keyed by ticker."""

    stock_data: dict[str, StockData]
    yield_channels: dict[str, YieldChannelData]
    vector_docs: dict[str, StockDocument]
    dividend_statuses: dict[str, Any] | None = None

    @classmethod
    def from_caches(
        cls,
        stock_data: dict[str, StockData] | None = None,
        yield_channels: dict[str, YieldChannelData] | None = None,
        vector_docs: dict[str, StockDocument] | None = None,
        dividend_statuses: dict[str, Any] | None = None,
    ) -> PortfolioAnalysisPreload:
        return cls(
            stock_data=dict(stock_data or {}),
            yield_channels=dict(yield_channels or {}),
            vector_docs=dict(vector_docs or {}),
            dividend_statuses=dict(dividend_statuses or {}),
        )

    def for_symbols(self, symbols: set[str]) -> PortfolioAnalysisPreload:
        """Return a copy limited to the given tickers."""
        allowed = {symbol.upper() for symbol in symbols}
        return PortfolioAnalysisPreload(
            stock_data={
                symbol: data for symbol, data in self.stock_data.items() if symbol in allowed
            },
            yield_channels={
                symbol: channel
                for symbol, channel in self.yield_channels.items()
                if symbol in allowed
            },
            vector_docs={
                symbol: document
                for symbol, document in self.vector_docs.items()
                if symbol in allowed
            },
            dividend_statuses={
                symbol: status
                for symbol, status in (self.dividend_statuses or {}).items()
                if symbol in allowed
            },
        )


def preload_portfolio_analysis(
    symbols: list[str],
    stock_data: dict[str, StockData],
    vector_docs: dict[str, StockDocument],
    *,
    years: int = 10,
    max_workers: int = 6,
    progress_callback: ProgressCallback | None = None,
    dividend_statuses: dict[str, Any] | None = None,
    allow_library_backfill: bool = False,
) -> PortfolioAnalysisPreload:
    """
    Fetch yield-channel series and retain vector documents for every holding.

    Reads the shared market library only unless ``allow_library_backfill`` is True
    (explicit admin / backfill jobs — never portfolio import or holding edits).
    """
    from services.portfolio_details_service import PortfolioDetailsService
    from services.stock_analysis_service import load_yield_channel_data
    from services.stock_history_backfill import backfill_portfolio_holdings
    from utils.stock_document_history import history_is_thin

    docs = dict(vector_docs)
    statuses = dict(dividend_statuses or {})
    if symbols:
        missing_docs = not docs
        missing_statuses = any(symbol not in statuses for symbol in symbols)
        if missing_docs or missing_statuses:
            loaded_docs, loaded_statuses = PortfolioDetailsService()._load_documents(symbols)
            if missing_docs:
                docs = loaded_docs
            statuses.update(loaded_statuses)

    needs_backfill = [
        symbol
        for symbol in symbols
        if docs.get(symbol) is None or history_is_thin(docs.get(symbol))
    ]
    if allow_library_backfill and needs_backfill:
        if progress_callback:
            progress_callback(0.0, f"Backfilling history for {len(needs_backfill)} holdings…")
        backfill_portfolio_holdings(
            needs_backfill,
            progress_callback=(
                (lambda value, message: progress_callback(value * 0.4, message))
                if progress_callback
                else None
            ),
        )
        docs, statuses = PortfolioDetailsService()._load_documents(symbols)

    yield_channels: dict[str, YieldChannelData] = {}
    if not symbols:
        return PortfolioAnalysisPreload(
            stock_data=dict(stock_data),
            yield_channels=yield_channels,
            vector_docs=dict(docs),
            dividend_statuses=statuses,
        )

    total = len(symbols)
    completed = 0
    chart_base = 0.4 if (allow_library_backfill and needs_backfill) else 0.0
    if progress_callback and total:
        progress_callback(chart_base, f"0/{total} yield charts")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                load_yield_channel_data,
                symbol,
                years=years,
                document=docs.get(symbol),
            ): symbol
            for symbol in symbols
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                channel = future.result()
            except Exception:  # noqa: BLE001
                channel = None
            if channel is not None:
                yield_channels[symbol] = channel
            completed += 1
            if progress_callback and total:
                progress_callback(
                    chart_base + (1.0 - chart_base) * (completed / total),
                    f"{completed}/{total} yield charts ({symbol})",
                )

    return PortfolioAnalysisPreload(
        stock_data=dict(stock_data),
        yield_channels=yield_channels,
        vector_docs=dict(docs),
        dividend_statuses=statuses,
    )
