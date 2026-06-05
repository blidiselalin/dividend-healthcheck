"""Tests for yfinance history helpers (no live API)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from data_ingestion.models import DataSource, DividendRecord, PriceHistory, StockDocument
from utils.yfinance_history import (
    compute_ttm_from_payment_series,
    dividend_series_from_records,
    history_dataframe_from_document,
)


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


def test_compute_ttm_from_payment_series_newer_payer():
    """Simulate INTU-like history: long prices, quarterly dividends for several years."""
    index = pd.date_range("2014-01-06", periods=1200, freq="B")
    hist = pd.DataFrame(
        {"Close": [500.0 + i * 0.1 for i in range(len(index))]},
        index=index,
    )
    records = [
        DividendRecord(ex_date=date(y, month, 15), payment_date=None, amount=0.4 + y * 0.01)
        for y in range(2015, 2025)
        for month in (2, 5, 8, 11)
    ]
    payments = dividend_series_from_records(records)
    ttm = compute_ttm_from_payment_series(hist, payments, min_rows=60)
    assert ttm is not None
    assert len(ttm) >= 60
    assert (ttm["Div_TTM"] > 0).all()
    ttm["Yield"] = (ttm["Div_TTM"] / ttm["Close"]) * 100
    assert (ttm["Yield"] >= 0.01).any()
