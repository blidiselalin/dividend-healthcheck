"""
Month-end portfolio value from purchase journal share counts and library prices.
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from data_ingestion.deposits_store import MonthlyDeposit
from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore, PurchaseRecord
from services.portfolio_purchase_journal_service import PortfolioPurchaseJournalService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MonthPortfolioValuation:
    portfolio_usd: float
    portfolio_eur: float
    symbols_held: int
    symbols_priced: int

    @property
    def coverage(self) -> float:
        if self.symbols_held <= 0:
            return 0.0
        return self.symbols_priced / self.symbols_held


def month_end(day: date) -> date:
    last = calendar.monthrange(day.year, day.month)[1]
    return date(day.year, day.month, last)


def fx_rates_carry_forward(
    deposits: list[MonthlyDeposit],
    *,
    default_fx: float = 0.92,
) -> dict[str, float]:
    """Map each deposit month to EUR/USD using the latest known rate at or before that month."""
    running = default_fx
    rates: dict[str, float] = {}
    for deposit in deposits:
        if deposit.deposit_eur > 0 and deposit.deposit_usd > 0:
            running = deposit.deposit_eur / deposit.deposit_usd
        rates[deposit.period_key] = running
    return rates


def shares_from_records(records: list[PurchaseRecord], as_of: date) -> float:
    """Share balance on ``as_of`` from explicit journal buy/sell rows."""
    if not records:
        return 0.0
    if not any(record.shares is not None and record.shares > 0 for record in records):
        return 0.0

    total = 0.0
    for record in sorted(records, key=lambda item: item.purchase_date):
        if record.purchase_date > as_of:
            continue
        if record.shares is None or record.shares <= 0:
            continue
        delta = float(record.shares)
        if record.side == "sell":
            delta = -delta
        total += delta
    return max(total, 0.0)


def _close_on_or_before(series: list[tuple[date, float]], as_of: date) -> float | None:
    if not series:
        return None
    best: float | None = None
    for point_date, close in series:
        if point_date <= as_of:
            best = close
        else:
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
    try:
        from db.connection import use_cloud_sql

        if use_cloud_sql():
            from db.postgres_market_history_store import PostgresMarketHistoryStore

            history_store = PostgresMarketHistoryStore()
            for symbol in list(documents):
                doc = documents.get(symbol)
                if doc is not None:
                    documents[symbol] = history_store.attach_history_to_document(doc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not attach Postgres price history: %s", exc)

    out: dict[str, list[tuple[date, float]]] = {}
    for symbol in symbols:
        sym = symbol.strip().upper()
        doc = documents.get(sym) or documents.get(symbol)
        series = _price_series(doc)
        if series:
            out[sym] = series
    return out


def compute_monthly_portfolio_valuations(
    deposits: list[MonthlyDeposit],
    *,
    db_path: Path | None = None,
) -> dict[str, MonthPortfolioValuation]:
    """
    Estimate end-of-month portfolio value from journal share counts and library closes.

    Uses explicit buy/sell share counts when present. A month is only marked fully
    covered when every held symbol has a month-end (or prior) library close.
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

    records_by_symbol: dict[str, list[PurchaseRecord]] = {}
    for record in records:
        sym = record.symbol.strip().upper()
        records_by_symbol.setdefault(sym, []).append(record)

    symbols = sorted(records_by_symbol)
    price_series = _load_price_series(symbols)
    fx_by_month = fx_rates_carry_forward(deposits)
    values: dict[str, MonthPortfolioValuation] = {}

    for deposit in deposits:
        as_of = month_end(deposit.period)
        total_usd = 0.0
        symbols_held = 0
        symbols_priced = 0

        for symbol in symbols:
            symbol_records = records_by_symbol.get(symbol, [])
            shares = shares_from_records(symbol_records, as_of)
            if shares <= 0:
                continue
            symbols_held += 1
            close = _close_on_or_before(price_series.get(symbol, []), as_of)
            if close is None:
                continue
            total_usd += shares * close
            symbols_priced += 1

        if total_usd <= 0 or symbols_held == 0:
            continue

        fx = fx_by_month.get(deposit.period_key, 0.92)
        values[deposit.period_key] = MonthPortfolioValuation(
            portfolio_usd=round(total_usd, 2),
            portfolio_eur=round(total_usd * fx, 2),
            symbols_held=symbols_held,
            symbols_priced=symbols_priced,
        )

    return values


def compute_monthly_portfolio_eur(
    deposits: list[MonthlyDeposit],
    *,
    db_path: Path | None = None,
) -> dict[str, float]:
    """Backward-compatible EUR map for callers that only need the amount."""
    return {
        key: value.portfolio_eur
        for key, value in compute_monthly_portfolio_valuations(deposits, db_path=db_path).items()
    }


def pick_portfolio_eur_for_month(
    *,
    stored: float | None,
    valuation: MonthPortfolioValuation | None,
) -> float | None:
    """
    Prefer a full stock-based valuation; fall back to stored IBKR/manual NAV when incomplete.
    """
    if valuation is not None and valuation.portfolio_eur > 0:
        if valuation.coverage >= 1.0:
            return valuation.portfolio_eur
        if stored is not None and stored > 0:
            return stored
        return valuation.portfolio_eur
    if stored is not None and stored > 0:
        return stored
    return None
