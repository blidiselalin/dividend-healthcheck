"""
Derive dividend yield and annual income from stored price/dividend history.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from data_ingestion.models import StockDocument
    from models.stock import StockData


def latest_close_from_document(doc: "StockDocument") -> Optional[float]:
    history = getattr(doc, "price_history", None) or []
    if not history:
        return None
    latest = max(history, key=lambda point: point.date)
    close = getattr(latest, "adjusted_close", None) or getattr(latest, "close", None)
    try:
        value = float(close) if close is not None else 0.0
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def compute_yield_from_annual_and_price(
    annual_dividend: Optional[float],
    price: Optional[float],
) -> Optional[float]:
    try:
        annual = float(annual_dividend) if annual_dividend is not None else 0.0
        px = float(price) if price is not None else 0.0
    except (TypeError, ValueError):
        return None
    if annual <= 0 or px <= 0:
        return None
    return round((annual / px) * 100, 2)


def enrich_stock_data_from_history(
    stock: "StockData",
    document: Optional["StockDocument"],
    *,
    prefer_history: bool = True,
) -> Tuple["StockData", str]:
    """
    Fill missing dividend rate/yield from library dividend_history.

    Returns (stock, yield_source) where yield_source is "metadata" or "history".
    """

    from utils.converters import _build_dividend_history
    from utils.dividend_amounts import resolve_annual_dividend_per_share

    records = document.dividend_history or []
    annual = resolve_annual_dividend_per_share(records, document, stock)
    if annual and annual > 0:
        stock.dividend_rate = annual
        document.annual_dividend = annual
        rebuilt = _build_dividend_history(document)
        if rebuilt is not None:
            stock.dividend_history = rebuilt

    price = stock.price
    if (price is None or price <= 0) and document.current_price:
        price = document.current_price
    if (price is None or price <= 0) and document.price_history:
        price = latest_close_from_document(document)
        if price:
            stock.price = price

    computed_yield = compute_yield_from_annual_and_price(annual, price)
    if computed_yield is None:
        return stock, "metadata"

    has_history = len(records) >= 4
    if stock.dividend_yield_pct is None:
        stock.dividend_yield_pct = computed_yield
        return stock, "history" if has_history else "metadata"

    if prefer_history and has_history:
        stock.dividend_yield_pct = computed_yield
        return stock, "history"

    return stock, "metadata"
