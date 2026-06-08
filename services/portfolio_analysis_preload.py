"""
Preload dividend charts and vector DB history for portfolio holdings.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, TYPE_CHECKING

ProgressCallback = Callable[[float, str], None]

if TYPE_CHECKING:
    from data_ingestion.models import StockDocument
    from models.stock import StockData
    from services.yield_channel_chart import YieldChannelData


def _fetch_preload_channel(
    _service: object,
    symbol: str,
    years: int,
    document: Optional["StockDocument"],
) -> Optional["YieldChannelData"]:
    from services.stock_analysis_service import load_yield_channel_data

    return load_yield_channel_data(symbol, years=years, document=document)


@dataclass(frozen=True)
class PortfolioAnalysisPreload:
    """In-memory analysis payloads keyed by ticker."""

    stock_data: Dict[str, "StockData"]
    yield_channels: Dict[str, "YieldChannelData"]
    vector_docs: Dict[str, "StockDocument"]


def preload_portfolio_analysis(
    symbols: List[str],
    stock_data: Dict[str, "StockData"],
    vector_docs: Dict[str, "StockDocument"],
    *,
    years: int = 10,
    max_workers: int = 6,
    progress_callback: Optional[ProgressCallback] = None,
) -> PortfolioAnalysisPreload:
    """
    Fetch yield-channel series and retain vector documents for every holding.

    Runs in parallel so the portfolio table and drill-down charts are ready
    before the user selects a ticker.
    """
    from services.yield_channel_chart import YieldChannelService

    yield_channels: Dict[str, YieldChannelData] = {}
    if not symbols:
        return PortfolioAnalysisPreload(
            stock_data=dict(stock_data),
            yield_channels=yield_channels,
            vector_docs=dict(vector_docs),
        )

    vector_store = None
    try:
        from services.shared_market_db import get_shared_vector_store

        vector_store = get_shared_vector_store()
    except Exception:
        pass

    service = YieldChannelService(vector_store=vector_store)

    total = len(symbols)
    completed = 0
    if progress_callback and total:
        progress_callback(0.0, f"0/{total} yield charts")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _fetch_preload_channel,
                service,
                symbol,
                years,
                vector_docs.get(symbol),
            ): symbol
            for symbol in symbols
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                channel = future.result()
            except Exception:
                channel = None
            if channel is not None:
                yield_channels[symbol] = channel
            completed += 1
            if progress_callback and total:
                progress_callback(
                    completed / total,
                    f"{completed}/{total} yield charts ({symbol})",
                )

    return PortfolioAnalysisPreload(
        stock_data=dict(stock_data),
        yield_channels=yield_channels,
        vector_docs=dict(vector_docs),
    )
