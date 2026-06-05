"""
Independent single-stock analysis backed by the shared library (stock_documents).

Loads full JSON history (price_history, dividend_history), merges indexed Postgres
columns, derives dividend yield from payments when metadata is missing, and prepares
yield-channel data for the analysis UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from utils.converters import document_to_stock_data
from utils.logging_config import get_logger
from utils.stock_history_enrichment import enrich_stock_data_from_history

logger = get_logger("dividendscope.stock_analysis")

try:
    from data_ingestion.models import StockDocument
    from models.stock import StockData
    from services.yield_channel_chart import YieldChannelData

    LIBRARY_AVAILABLE = True
except ImportError:
    LIBRARY_AVAILABLE = False
    StockDocument = Any  # type: ignore
    StockData = Any  # type: ignore
    YieldChannelData = Any  # type: ignore


@dataclass(frozen=True)
class IndependentStockAnalysis:
    """Payload for single-stock / S&P research views."""

    symbol: str
    stock_data: "StockData"
    document: Optional["StockDocument"]
    yield_channel: Optional["YieldChannelData"]
    price_history_points: int
    dividend_history_points: int
    dividend_yield_source: str
    history_summary: Dict[str, Any]


def _history_counts(doc: Optional["StockDocument"]) -> tuple[int, int]:
    if doc is None:
        return 0, 0
    return len(doc.price_history or []), len(doc.dividend_history or [])


def load_library_document(symbol: str) -> Optional["StockDocument"]:
    """Load one symbol from the shared market library."""
    if not LIBRARY_AVAILABLE:
        return None
    try:
        from services.shared_market_db import get_document

        return get_document((symbol or "").strip().upper())
    except Exception as exc:
        logger.debug("Library lookup failed for %s: %s", symbol, exc)
        return None


def stock_data_from_document(
    document: "StockDocument",
    *,
    apply_live_price: bool = True,
) -> "StockData":
    """Convert a library document to UI stock data with history-based dividend fields."""
    stock = document_to_stock_data(document)
    stock, yield_source = enrich_stock_data_from_history(stock, document)

    if apply_live_price:
        from services.live_price import apply_live_price

        stock = apply_live_price(stock)
        stock, yield_source = enrich_stock_data_from_history(stock, document)

    stock._yield_source = yield_source  # type: ignore[attr-defined]
    return stock


def load_yield_channel_data(
    symbol: str,
    *,
    years: int = 10,
    document: Optional["StockDocument"] = None,
) -> Optional["YieldChannelData"]:
    try:
        from services.yield_channel_chart import _default_yield_channel_service

        return _default_yield_channel_service().fetch_yield_channel_data(
            symbol,
            years=years,
            use_db=True,
        )
    except Exception as exc:
        logger.debug("Yield channel unavailable for %s: %s", symbol, exc)
        return None


def load_independent_stock_analysis(
    symbol: str,
    *,
    years: int = 10,
    apply_live_price: bool = True,
    include_yield_channel: bool = True,
    document: Optional["StockDocument"] = None,
) -> Optional[IndependentStockAnalysis]:
    """
    Build a complete analysis bundle for one ticker (portfolio holding or S&P research).

    Uses analysed-library historical data first; falls back to live API only when
    no library document exists.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return None

    doc = document or load_library_document(sym)
    if doc is not None:
        stock = stock_data_from_document(doc, apply_live_price=apply_live_price)
        yield_source = getattr(stock, "_yield_source", "history")
    else:
        stock = _fallback_stock_data(sym, apply_live_price=apply_live_price)
        if stock is None:
            return None
        yield_source = "api"

    channel = (
        load_yield_channel_data(sym, years=years, document=doc)
        if include_yield_channel
        else None
    )
    if channel is not None and (stock.dividend_yield_pct is None or yield_source == "history"):
        stock.dividend_yield_pct = channel.current_yield
        yield_source = "yield_channel"

    stock._yield_source = yield_source  # type: ignore[attr-defined]

    price_pts, div_pts = _history_counts(doc)
    summary = {
        "library_hit": doc is not None,
        "price_history_points": price_pts,
        "dividend_history_points": div_pts,
        "yield_channel_ready": channel is not None,
        "dividend_yield_source": yield_source,
    }

    return IndependentStockAnalysis(
        symbol=sym,
        stock_data=stock,
        document=doc,
        yield_channel=channel,
        price_history_points=price_pts,
        dividend_history_points=div_pts,
        dividend_yield_source=yield_source,
        history_summary=summary,
    )


def _fallback_stock_data(symbol: str, *, apply_live_price: bool) -> Optional["StockData"]:
    """API fallback when the symbol is not in stock_documents."""
    stock = None
    try:
        from services.enhanced_stock_service import EnhancedStockService

        stock = EnhancedStockService(staleness_days=7, fetch_realtime_prices=False).fetch(symbol)
    except Exception:
        stock = None
    if stock is None:
        try:
            from services.stock_service import StockService

            stock = StockService.fetch(symbol)
        except Exception:
            stock = None
    if stock is None:
        return None
    if apply_live_price:
        from services.live_price import apply_live_price

        stock = apply_live_price(stock)
    return stock
