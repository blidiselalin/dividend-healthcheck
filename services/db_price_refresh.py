"""
Refresh latest market prices in the vector database.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def remove_delisted_from_vector_db(
    symbols: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Delete delisted / broken-quote symbols from the vector database."""
    from config import DELISTED_SYMBOLS, VECTORDB_DIR
    from data_ingestion.vector_store import VectorStore

    targets = sorted(symbols or DELISTED_SYMBOLS)
    store = VectorStore(persist_directory=str(VECTORDB_DIR))
    removed = store.delete_symbols(targets)
    return {
        "symbols": targets,
        "removed": removed,
        "timestamp": datetime.now().isoformat(),
    }


def _fetch_latest_price(symbol: str) -> Optional[float]:
    """Fetch the latest trade price from Yahoo Finance."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        fast_info = getattr(ticker, "fast_info", None)
        if fast_info:
            for key in ("lastPrice", "regularMarketPrice", "previousClose"):
                value = fast_info.get(key) if hasattr(fast_info, "get") else None
                if value:
                    return float(value)

        history = ticker.history(period="5d", auto_adjust=True)
        if history is not None and not history.empty and "Close" in history.columns:
            closes = history["Close"].dropna()
            if not closes.empty:
                return float(closes.iloc[-1])
    except Exception as exc:
        logger.debug("Price fetch failed for %s: %s", symbol, exc)
    return None


def _apply_latest_price(document, price: float) -> None:
    """Update document current price and today's price-history bar."""
    from data_ingestion.models import PriceHistory

    document.current_price = round(price, 4)
    document.last_updated = datetime.now()

    if not document.price_history:
        return

    today = date.today()
    existing = next((point for point in document.price_history if point.date == today), None)
    if existing is not None:
        existing.close = price
        existing.high = max(existing.high, price)
        existing.low = min(existing.low, price)
        return

    document.price_history.append(
        PriceHistory(
            date=today,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=0,
        )
    )
    document.price_history.sort(key=lambda point: point.date, reverse=True)


def _collect_symbols() -> List[str]:
    """Symbols to refresh: all vector DB entries plus portfolio holdings."""
    from config import DELISTED_SYMBOLS

    symbols: Set[str] = set()

    try:
        from config import VECTORDB_DIR
        from data_ingestion.vector_store import VectorStore

        store = VectorStore(persist_directory=str(VECTORDB_DIR))
        for document in store.get_all_documents():
            if document.symbol:
                symbols.add(document.symbol.upper())
    except Exception as exc:
        logger.warning("Could not load vector DB symbols: %s", exc)

    try:
        from data_ingestion.portfolio_store import PortfolioStore

        for holding in PortfolioStore().list_holdings():
            symbols.add(holding.symbol.upper())
    except Exception:
        pass

    return sorted(symbol for symbol in symbols if symbol not in DELISTED_SYMBOLS)


def refresh_vector_db_prices(
    symbols: Optional[List[str]] = None,
    *,
    max_workers: int = 8,
) -> Dict[str, Any]:
    """
    Pull latest prices and persist them on vector DB documents.

    Returns:
        Stats dict with updated, skipped, errors, and total counts.
    """
    from config import VECTORDB_DIR
    from data_ingestion.vector_store import VectorStore

    target_symbols = [symbol.upper() for symbol in (symbols or _collect_symbols())]
    stats: Dict[str, Any] = {
        "total": len(target_symbols),
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "timestamp": datetime.now().isoformat(),
    }

    if not target_symbols:
        return stats

    store = VectorStore(persist_directory=str(VECTORDB_DIR))
    documents = {
        document.symbol.upper(): document
        for document in store.get_all_documents()
        if document.symbol
    }

    prices: Dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_fetch_latest_price, symbol): symbol
            for symbol in target_symbols
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                price = future.result()
            except Exception:
                stats["errors"] += 1
                continue
            if price is None or price <= 0:
                stats["skipped"] += 1
                continue
            prices[symbol] = price

    modified = []
    for symbol, price in prices.items():
        document = documents.get(symbol)
        if document is None:
            stats["skipped"] += 1
            continue
        _apply_latest_price(document, price)
        modified.append(document)
        stats["updated"] += 1

    if modified:
        store.add_documents(modified)
        logger.info("Updated prices for %s symbols in vector DB", len(modified))

    return stats
