"""
Resolve analysed-library documents for charting (fresh DB + trustworthy history).
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from data_ingestion.models import StockDocument


def resolve_library_document(
    symbol: str,
    document: Optional["StockDocument"] = None,
) -> Optional["StockDocument"]:
    """
    Load the best library document for yield-channel / history charts.

    Always prefers a fresh lookup (PostgreSQL attach_history merges normalized
    tables). Ignores stale session caches when the library has better data.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return document

    from services.shared_market_db import get_document
    from utils.yfinance_history import library_prices_trustworthy, unique_price_dates

    fresh = get_document(sym)
    if fresh is None:
        return document
    if document is None:
        return fresh

    fresh_ok = library_prices_trustworthy(fresh)
    cached_ok = library_prices_trustworthy(document)
    if fresh_ok and not cached_ok:
        return fresh
    if fresh_ok and cached_ok:
        if unique_price_dates(fresh) >= unique_price_dates(document):
            return fresh
        return document
    if not fresh_ok and cached_ok:
        return document
    if len(fresh.dividend_history or []) >= len(document.dividend_history or []):
        return fresh
    return document
