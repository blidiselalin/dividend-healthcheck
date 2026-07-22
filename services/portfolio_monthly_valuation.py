"""
Month-end portfolio value from purchase journal share counts and library prices.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date
from pathlib import Path
from typing import Any

from data_ingestion.deposits_store import MonthlyDeposit
from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore
from services.portfolio_holding_detail_service import shares_as_of
from services.portfolio_purchase_journal_service import PortfolioPurchaseJournalService

logger = logging.getLogger(__name__)


def month_end(day: date) -> date:
    last = calendar.monthrange(day.year, day.month)[1]
    return date(day.year, day.month, last)


def eur_usd_rate(deposit: MonthlyDeposit, *, default_fx: float = 0.92) -> float:
    if deposit.deposit_eur > 0 and deposit.deposit_usd > 0:
        return deposit.deposit_eur / deposit.deposit_usd
    return default_fx


def _close_on_or_before(series: list[tuple[date, float]], as_of: date) -> float | None:
    if not series:
        return None
    best: float | None = None
    for point_date, close in series:
        if point_date <= as_of:
            best = close
        elif point_date > as_of:
            break
    return best


def _price_series(document: Any) -> list[tuple[date, float]]:
    if document is None:
        return []
    history = getattr(document, "price_history", None) or []
    points: list[tuple[date, float]] = []
    for point in history:
        point_date = getattr(point, "date", None)
        if point_date is None:
            continue
        close = getattr(point, "adjusted_close", None)
        if close in (None, 0):
            close = getattr(point, "close", None)
        try:
            value = float(close)
        except (TypeError, ValueError):
            continue
        if value > 0:
            points.append((point_date, value))
    points.sort(key=lambda item: item[0])
    return points


def _load_price_series(symbols: list[str]) -> dict[str, list[tuple[date, float]]]:
    if not symbols:
        return {}
    try:
        from services.shared_market_db import load_documents
    except ImportError:
        return {}

    documents = load_documents(symbols)
    out: dict[str, list[tuple[date, float]]] = {}
    for symbol in symbols:
        sym = symbol.strip().upper()
        doc = documents.get(sym) or documents.get(symbol)
        series = _price_series(doc)
        if series:
            out[sym] = series
    return out


def compute_monthly_portfolio_eur(
    deposits: list[MonthlyDeposit],
    *,
    db_path: Path | None = None,
) -> dict[str, float]:
    """
    Estimate end-of-month portfolio € from journal share counts and library closes.

    Returns ``period_key -> portfolio_eur`` for months where a positive value
    could be computed.
    """
    if not deposits:
        return {}

    if db_path is None:
        journal_service = PortfolioPurchaseJournalService()
    else:
        journal_service = PortfolioPurchaseJournalService(
            journal_store=PurchaseJournalStore(db_path=db_path, seed=False),
            portfolio_store=PortfolioStore(db_path=db_path, seed=False),
        )
    records = journal_service.journal.list_purchases(portfolio_only=False)
    if not records:
        return {}

    lots = journal_service.build_estimated_lots(records)
    lots_by_symbol: dict[str, list[Any]] = {}
    for lot in lots:
        lots_by_symbol.setdefault(lot.symbol, []).append(lot)

    symbols = sorted(lots_by_symbol)
    price_series = _load_price_series(symbols)
    values: dict[str, float] = {}

    for deposit in deposits:
        as_of = month_end(deposit.period)
        total_usd = 0.0
        priced_symbols = 0
        for symbol in symbols:
            symbol_lots = lots_by_symbol.get(symbol, [])
            shares = shares_as_of(symbol_lots, as_of, fallback_shares=0.0)
            if shares <= 0:
                continue
            close = _close_on_or_before(price_series.get(symbol, []), as_of)
            if close is None:
                continue
            total_usd += shares * close
            priced_symbols += 1

        if total_usd <= 0 or priced_symbols == 0:
            continue
        fx = eur_usd_rate(deposit)
        values[deposit.period_key] = round(total_usd * fx, 2)

    return values
