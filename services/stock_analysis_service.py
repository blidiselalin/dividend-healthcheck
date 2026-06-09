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

from data_ingestion.models import StockDocument
from models.stock import StockData
from services.yield_channel_chart import YieldChannelData


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
    try:
        from services.shared_market_db import get_document

        return get_document((symbol or "").strip().upper())
    except Exception as exc:
        logger.debug("Library lookup failed for %s: %s", symbol, exc)
        return None


def load_stock_data(
    symbol: str,
    *,
    include_yield_channel: bool = True,
    apply_live_price: bool = True,
    fetch_realtime_prices: bool = False,
) -> Optional["StockData"]:
    """Return stock data for one ticker (library-first, optional API fallback)."""
    try:
        analysis = load_independent_stock_analysis(
            symbol,
            include_yield_channel=include_yield_channel,
            apply_live_price=apply_live_price,
            fetch_realtime_prices=fetch_realtime_prices,
        )
        return analysis.stock_data if analysis else None
    except Exception as exc:
        logger.debug("Stock data unavailable for %s: %s", symbol, exc)
        return None


def load_portfolio_statistics_stock(
    symbol: str,
    document: Optional["StockDocument"] = None,
) -> Optional["StockData"]:
    """Load valuation stats for portfolio rows (no live price overlay)."""
    if document is not None:
        return stock_data_from_document(document, apply_live_price=False)

    try:
        from services.enhanced_stock_service import get_enhanced_stock_service

        return get_enhanced_stock_service(fetch_realtime_prices=False).fetch(symbol)
    except Exception:
        pass

    try:
        from services.stock_service import StockService

        return StockService.fetch(symbol)
    except Exception:
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
    library_only: bool = True,
) -> Optional["YieldChannelData"]:
    """Build a yield channel from the shared market library (database-first)."""
    from utils.library_document import resolve_library_document

    sym = (symbol or "").strip().upper()
    doc = resolve_library_document(sym, document)
    if doc is None:
        return None
    try:
        from services.yield_channel_chart import _default_yield_channel_service
        from utils.yield_channel_history import plan_yield_channel_attempts

        service = _default_yield_channel_service()
        for attempt_years, min_prices, min_yields in plan_yield_channel_attempts(
            doc,
            requested_years=years,
        ):
            channel = service.fetch_yield_channel_data(
                sym,
                years=attempt_years,
                use_db=True,
                document=doc,
                min_price_rows=min_prices,
                min_yield_rows=min_yields,
                library_only=library_only,
            )
            if channel is not None:
                return channel
        return None
    except Exception as exc:
        logger.debug("Yield channel unavailable for %s: %s", sym, exc)
        return None


def ensure_yield_channel_data(
    symbol: str,
    *,
    years: int = 10,
    document: Optional["StockDocument"] = None,
    allow_backfill: bool = False,
    library_only: bool = True,
) -> Optional["YieldChannelData"]:
    """
    Load yield-channel data from library tables / stock_documents.

    When ``allow_backfill`` is True (admin jobs only), thin symbols are enriched
    once from external sources into the library, then reloaded from the database.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return None

    from utils.library_document import resolve_library_document

    doc = resolve_library_document(sym, document)
    channel = load_yield_channel_data(
        sym,
        years=years,
        document=doc,
        library_only=library_only,
    )
    if channel is not None or not allow_backfill:
        return channel

    if doc is None or len(doc.dividend_history or []) < 4:
        return None

    try:
        from services.stock_history_backfill import backfill_thin_history

        backfill_thin_history(symbols=[sym], limit=1)
        doc = load_library_document(sym) or doc
    except Exception as exc:
        logger.debug("On-demand history backfill failed for %s: %s", sym, exc)

    return load_yield_channel_data(
        sym,
        years=years,
        document=doc,
        library_only=library_only,
    )


def load_independent_stock_analysis(
    symbol: str,
    *,
    years: int = 10,
    apply_live_price: bool = True,
    include_yield_channel: bool = True,
    fetch_realtime_prices: bool = False,
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
        stock = _fallback_stock_data(
            sym,
            apply_live_price=apply_live_price,
            fetch_realtime_prices=fetch_realtime_prices,
        )
        if stock is None:
            return None
        yield_source = "api"

    channel = (
        ensure_yield_channel_data(sym, years=years, document=doc)
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


def _fallback_stock_data(
    symbol: str,
    *,
    apply_live_price: bool,
    fetch_realtime_prices: bool = False,
) -> Optional["StockData"]:
    """API fallback when the symbol is not in stock_documents."""
    stock = None
    try:
        from services.enhanced_stock_service import get_enhanced_stock_service

        stock = get_enhanced_stock_service(
            fetch_realtime_prices=fetch_realtime_prices,
        ).fetch(symbol)
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
