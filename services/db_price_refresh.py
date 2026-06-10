"""
Refresh latest market prices in the shared market library (PostgreSQL or local Chroma).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def remove_delisted_from_market_library(
    symbols: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Delete delisted / broken-quote symbols from the shared market library."""
    from config import DELISTED_SYMBOLS
    from services.shared_market_db import get_shared_vector_store

    targets = sorted(symbols or DELISTED_SYMBOLS)
    store = get_shared_vector_store()
    removed = store.delete_symbols(targets)
    return {
        "symbols": targets,
        "removed": removed,
        "timestamp": datetime.now().isoformat(),
    }


def _fetch_latest_price(symbol: str) -> Optional[float]:
    """Fetch the latest trade price from Yahoo Finance."""
    from services.live_price import fetch_latest_market_price

    return fetch_latest_market_price(symbol)


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
    """Symbols to refresh: market library entries plus portfolio holdings."""
    from config import DELISTED_SYMBOLS
    from services.shared_market_db import get_shared_vector_store

    symbols: Set[str] = set()

    try:
        store = get_shared_vector_store()
        for document in store.get_all_documents():
            if document.symbol:
                symbols.add(document.symbol.upper())
    except Exception as exc:
        logger.warning("Could not load market library symbols: %s", exc)

    try:
        from services.portfolio_context import create_portfolio_context

        for holding in create_portfolio_context().portfolio.list_holdings():
            symbols.add(holding.symbol.upper())
    except Exception:
        pass

    return sorted(symbol for symbol in symbols if symbol not in DELISTED_SYMBOLS)


def refresh_market_library_prices(
    symbols: Optional[List[str]] = None,
    *,
    max_workers: int = 8,
) -> Dict[str, Any]:
    """
    Pull latest prices and persist them on shared market library documents.

    Returns:
        Stats dict with updated, skipped, errors, and total counts.
    """
    from services.shared_market_db import get_shared_vector_store

    target_symbols = [
        symbol.upper()
        for symbol in (symbols if symbols is not None else _collect_symbols())
    ]
    stats: Dict[str, Any] = {
        "total": len(target_symbols),
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "timestamp": datetime.now().isoformat(),
    }

    if not target_symbols:
        return stats

    store = get_shared_vector_store()
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
        logger.info("Updated prices for %s symbols in market library", len(modified))

    return stats
