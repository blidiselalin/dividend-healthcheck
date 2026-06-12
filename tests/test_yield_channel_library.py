"""Tests for database-first yield channel readiness."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd

from data_ingestion.models import DividendRecord, PriceHistory, StockDocument
from utils.yield_channel_library import (
    assess_yield_channel_readiness,
    format_history_reload_guidance,
)


def _good_prices(n: int = 300) -> list:
    return [
        PriceHistory(
            date=date(2020, 1, 1) + timedelta(days=i),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0 + i * 0.01,
            volume=1,
        )
        for i in range(n)
    ]


def test_readiness_chart_ready_with_trustworthy_prices() -> None:
    doc = StockDocument(symbol="INTU", name="Intuit")
    doc.price_history = _good_prices()
    doc.dividend_history = [
        DividendRecord(ex_date=date(2020, 2, 15), payment_date=None, amount=1.0) for _ in range(8)
    ]

    with patch("services.shared_market_db.get_document", return_value=None):
        readiness = assess_yield_channel_readiness("INTU", doc)
    assert readiness.chart_ready is True
    assert readiness.unique_price_days == 300
    assert readiness.dividend_payments == 8


def test_readiness_detects_duplicate_price_rows() -> None:
    doc = StockDocument(symbol="INTU", name="Intuit")
    doc.price_history = [
        PriceHistory(
            date=date(2024, 6, 1),
            open=650.0,
            high=660.0,
            low=640.0,
            close=650.0,
            volume=1,
        )
    ] * 200
    doc.dividend_history = [
        DividendRecord(ex_date=date(2020, 2, 15), payment_date=None, amount=1.0) for _ in range(8)
    ]

    with patch("services.shared_market_db.get_document", return_value=None):
        readiness = assess_yield_channel_readiness("INTU", doc)
    assert readiness.chart_ready is False
    assert readiness.needs_history_backfill is True


def test_reload_guidance_mentions_backfill_when_prices_missing() -> None:
    doc = StockDocument(symbol="INTU", name="Intuit")
    doc.price_history = []
    doc.dividend_history = [
        DividendRecord(
            ex_date=date(2020, 2, 15) + timedelta(days=90 * i),
            payment_date=None,
            amount=1.0,
        )
        for i in range(8)
    ]
    with patch("services.shared_market_db.get_document", return_value=None):
        readiness = assess_yield_channel_readiness("INTU", doc)
    guidance = format_history_reload_guidance(readiness)
    assert "price history is missing" in guidance
    assert "Backfill thin history" in guidance


def test_prepare_history_frame_handles_empty_input() -> None:
    from services.yield_channel_chart import YieldChannelService

    assert YieldChannelService._prepare_history_frame(pd.DataFrame()).empty


def test_prepare_history_frame_handles_missing_close_column() -> None:
    from services.yield_channel_chart import YieldChannelService

    frame = pd.DataFrame({"Open": [1.0]}, index=pd.date_range("2020-01-01", periods=1))
    assert YieldChannelService._prepare_history_frame(frame).empty
