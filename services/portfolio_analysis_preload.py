"""
Preload dividend charts and vector DB history for portfolio holdings.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from data_ingestion.models import StockDocument
    from models.stock import StockData
    from services.yield_channel_chart import YieldChannelData


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
        from data_ingestion.vector_store import VectorStore
        from config import VECTORDB_DIR

        vector_store = VectorStore(persist_directory=str(VECTORDB_DIR))
    except Exception:
        pass

    service = YieldChannelService(vector_store=vector_store)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(service.fetch_yield_channel_data, symbol, years): symbol
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

    return PortfolioAnalysisPreload(
        stock_data=dict(stock_data),
        yield_channels=yield_channels,
        vector_docs=dict(vector_docs),
    )
