"""Tests for yfinance history helpers (no live API)."""

from __future__ import annotations

from datetime import date

from data_ingestion.models import DataSource, PriceHistory, StockDocument
from utils.yfinance_history import history_dataframe_from_document


def _sample_doc(symbol: str = "KO", n: int = 260) -> StockDocument:
    prices = []
    for i in range(n):
        d = date(2024, 1, 1)
        d = date.fromordinal(d.toordinal() + i)
        prices.append(
            PriceHistory(
                date=d,
                open=60.0,
                high=61.0,
                low=59.0,
                close=60.0 + (i % 10) * 0.1,
                volume=1_000_000,
                adjusted_close=60.0 + (i % 10) * 0.1,
            )
        )
    return StockDocument(symbol=symbol, name="Coca-Cola", source=DataSource.YAHOO, price_history=prices)


def test_history_dataframe_from_document():
    doc = _sample_doc()
    frame = history_dataframe_from_document(doc, years=10, min_rows=100)
    assert not frame.empty
    assert len(frame) >= 100
    assert "Close" in frame.columns
