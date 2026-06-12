"""Tests for stock document history hydration and thin detection."""
# ruff: noqa: S101

from __future__ import annotations

import json

from data_ingestion.models import DataSource, StockDocument
from utils.stock_document_history import (
    history_is_thin,
    parse_history_payload,
    yield_channel_ready,
)


def test_from_dict_loads_legacy_price_history_json() -> None:
    payload = {
        "symbol": "INTU",
        "name": "Intuit",
        "source": "yahoo",
        "price_history": [],
        "dividend_history": [],
        "price_history_json": json.dumps(
            [
                {
                    "date": "2024-01-02",
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.5,
                    "close": 10.5,
                    "volume": 1000,
                }
            ]
        ),
        "dividend_history_json": json.dumps(
            [
                {
                    "ex_date": "2024-02-01",
                    "payment_date": None,
                    "amount": 0.5,
                }
            ]
        ),
    }
    doc = StockDocument.from_dict(payload)
    assert len(doc.price_history) == 1
    assert len(doc.dividend_history) == 1
    assert doc.price_history[0].close == 10.5


def test_history_is_thin_uses_yield_thresholds() -> None:
    doc = StockDocument(symbol="KO", name="Coca-Cola", source=DataSource.YAHOO)
    assert history_is_thin(doc) is True

    from datetime import date

    from data_ingestion.models import DividendRecord, PriceHistory

    doc.price_history = [
        PriceHistory(
            date=date(2024, 1, 1) + __import__("datetime").timedelta(days=i),
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        )
        for i in range(300)
    ]
    doc.dividend_history = [
        DividendRecord(ex_date=date(2020, 1, 1), payment_date=None, amount=1.0),
        DividendRecord(ex_date=date(2021, 1, 1), payment_date=None, amount=1.0),
        DividendRecord(ex_date=date(2022, 1, 1), payment_date=None, amount=1.0),
        DividendRecord(ex_date=date(2023, 1, 1), payment_date=None, amount=1.0),
    ]
    assert history_is_thin(doc) is False
    assert yield_channel_ready(doc) is True


def test_parse_history_payload_prefers_arrays() -> None:
    prices, dividends = parse_history_payload(
        {
            "price_history": [
                {
                    "date": "2024-01-01",
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 0,
                }
            ],
            "dividend_history": [],
        }
    )
    assert len(prices) == 1
    assert dividends == []
