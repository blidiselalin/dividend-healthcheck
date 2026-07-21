"""
Fetch and apply live market prices on top of vector-DB snapshots.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _read_fast_info_value(fast_info: Any, key: str) -> float | None:
    """Read a numeric field from yfinance FastInfo (dict-like or attribute)."""
    value = None
    if hasattr(fast_info, "get"):
        try:
            value = fast_info.get(key)
        except Exception:
            value = None
    if value is None:
        value = getattr(fast_info, key, None)
    if value is None:
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def fetch_latest_market_price(symbol: str) -> float | None:
    """
    Fetch the latest trade price from Yahoo Finance.

    Tries fast_info first, then recent daily history as fallback.
    """
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return None

    try:
        import yfinance as yf

        from utils.yfinance_config import configure_yfinance
        from utils.yfinance_history import suppress_yfinance_noise

        configure_yfinance()
        ticker = yf.Ticker(symbol)
        with suppress_yfinance_noise():
            fast_info = getattr(ticker, "fast_info", None)
            if fast_info:
                for key in (
                    "lastPrice",
                    "last_price",
                    "regularMarketPrice",
                    "regular_market_price",
                ):
                    price = _read_fast_info_value(fast_info, key)
                    if price is not None:
                        return price

            history = ticker.history(period="5d", auto_adjust=True)
            if history is not None and not history.empty and "Close" in history.columns:
                closes = history["Close"].dropna()
                if not closes.empty:
                    return float(closes.iloc[-1])
    except Exception as exc:
        logger.debug("Live price fetch failed for %s: %s", symbol, exc)  # noqa: BLE001
    return None


def fetch_previous_close(symbol: str) -> float | None:
    """Previous session close from Yahoo Finance (for day-change on holdings)."""
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return None

    try:
        import yfinance as yf

        from utils.yfinance_config import configure_yfinance
        from utils.yfinance_history import suppress_yfinance_noise

        configure_yfinance()
        ticker = yf.Ticker(symbol)
        with suppress_yfinance_noise():
            fast_info = getattr(ticker, "fast_info", None)
            if fast_info:
                for key in (
                    "previousClose",
                    "previous_close",
                    "regularMarketPreviousClose",
                    "regular_market_previous_close",
                ):
                    price = _read_fast_info_value(fast_info, key)
                    if price is not None:
                        return price

            history = ticker.history(period="5d", auto_adjust=True)
            if history is not None and not history.empty and "Close" in history.columns:
                closes = history["Close"].dropna()
                if len(closes) >= 2:
                    return float(closes.iloc[-2])
    except Exception as exc:
        logger.debug("Previous close fetch failed for %s: %s", symbol, exc)
    return None


def apply_live_price(data: Any) -> Any:
    """
    Overlay a live quote on StockData (mutates in place).

    Leaves price unchanged when the live fetch fails.
    """
    if data is None or not getattr(data, "symbol", None):
        return data

    live = fetch_latest_market_price(data.symbol)
    if live is None:
        return data

    data.price = round(live, 4)
    sources = list(getattr(data, "data_sources", None) or [])
    if "Price: Live" not in sources:
        sources.append("Price: Live")
    data.data_sources = sources
    return data
