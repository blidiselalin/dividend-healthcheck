"""Tests for portfolio-first history backfill ordering."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from data_ingestion.models import DividendRecord, PriceHistory, StockDocument
from services.stock_history_backfill import sort_backfill_candidates


def _doc(symbol: str, *, prices: int = 0, divs: int = 4) -> StockDocument:
    doc = StockDocument(symbol=symbol, name=symbol)
    doc.price_history = [
        PriceHistory(
            date=date(2024, 6, 1),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1,
        )
    ] * prices
    doc.dividend_history = [
        DividendRecord(ex_date=date(2024, 2, 1), payment_date=None, amount=1.0)
    ] * divs
    doc.last_updated = datetime(2026, 1, 1)
    return doc


def test_sort_backfill_candidates_puts_portfolio_first():
    abbv = _doc("ABBV", prices=0, divs=54)
    ko = _doc("KO", prices=0, divs=8)
    ordered = sort_backfill_candidates(
        [ko, abbv],
        portfolio_symbols={"ABBV"},
    )
    assert [doc.symbol for doc in ordered] == ["ABBV", "KO"]


def test_sort_backfill_candidates_handles_aware_last_updated():
    aware = _doc("INTU", prices=10, divs=8)
    aware.last_updated = datetime(2026, 6, 1, tzinfo=timezone.utc)
    naive = _doc("MSFT", prices=5, divs=8)
    ordered = sort_backfill_candidates(
        [aware, naive],
        portfolio_symbols=set(),
    )
    assert ordered[0].symbol == "MSFT"
