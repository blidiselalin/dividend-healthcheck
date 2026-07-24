"""
EUR/USD conversion using the latest available market rate on or before each date.
"""

from __future__ import annotations

import logging
from datetime import date
from functools import lru_cache

from data_ingestion.deposits_store import MonthlyDeposit

logger = logging.getLogger(__name__)

DEFAULT_EUR_PER_USD = 0.92
EURUSD_YAHOO = "EURUSD=X"


def _rate_on_or_before(series: list[tuple[date, float]], as_of: date) -> float | None:
    """Latest EUR-per-USD rate on or before ``as_of``."""
    if not series:
        return None
    best: float | None = None
    for point_date, rate in series:
        if point_date <= as_of:
            best = rate
        else:
            break
    return best


def _history_frame_to_eur_per_usd(frame: object) -> list[tuple[date, float]]:
    """Convert Yahoo EURUSD=X history (USD per EUR) to EUR per USD."""
    if frame is None or getattr(frame, "empty", True):
        return []
    points: list[tuple[date, float]] = []
    for index, row in frame.iterrows():  # type: ignore[union-attr]
        point_date = index.date() if hasattr(index, "date") else index
        if not isinstance(point_date, date):
            continue
        try:
            usd_per_eur = float(row["Close"])
        except (KeyError, TypeError, ValueError):
            continue
        if usd_per_eur <= 0:
            continue
        points.append((point_date, 1.0 / usd_per_eur))
    points.sort(key=lambda item: item[0])
    return points


@lru_cache(maxsize=2)
def _load_eur_usd_market_series_cached(cache_day: str) -> tuple[tuple[date, float], ...]:
    del cache_day
    try:
        from utils.yfinance_history import YFINANCE_AVAILABLE, fetch_price_history
    except ImportError:
        return ()

    if not YFINANCE_AVAILABLE:
        return ()

    try:
        frame = fetch_price_history(EURUSD_YAHOO, years=15)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not load EURUSD market history: %s", exc)
        return ()

    return tuple(_history_frame_to_eur_per_usd(frame))


def load_eur_usd_market_series() -> list[tuple[date, float]]:
    """Daily EUR-per-USD closes from Yahoo, cached for the current UTC day."""
    return list(_load_eur_usd_market_series_cached(date.today().isoformat()))


def deposit_eur_per_usd_on_or_before(
    deposits: list[MonthlyDeposit],
    as_of: date,
) -> float | None:
    """Latest deposit-implied EUR/USD at or before ``as_of``."""
    best: float | None = None
    for deposit in sorted(deposits, key=lambda item: item.period):
        if deposit.period > as_of:
            break
        if deposit.deposit_eur > 0 and deposit.deposit_usd > 0:
            best = deposit.deposit_eur / deposit.deposit_usd
    return best


def eur_per_usd_on_or_before(
    as_of: date,
    *,
    market_series: list[tuple[date, float]] | None = None,
) -> float | None:
    series = market_series if market_series is not None else load_eur_usd_market_series()
    return _rate_on_or_before(series, as_of)


def resolve_eur_per_usd(
    as_of: date,
    deposits: list[MonthlyDeposit] | None = None,
    *,
    market_series: list[tuple[date, float]] | None = None,
    default: float = DEFAULT_EUR_PER_USD,
) -> float:
    """
    EUR per 1 USD for converting USD portfolio marks to EUR.

    Uses the latest market close on or before ``as_of``, then deposit-implied
    rates, then ``default``.
    """
    market = eur_per_usd_on_or_before(as_of, market_series=market_series)
    if market is not None and market > 0:
        return market
    if deposits:
        deposit_rate = deposit_eur_per_usd_on_or_before(deposits, as_of)
        if deposit_rate is not None and deposit_rate > 0:
            return deposit_rate
    return default
