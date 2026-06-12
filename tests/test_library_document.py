"""Tests for library document resolution."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from data_ingestion.models import DividendRecord, PriceHistory, StockDocument
from utils.library_document import resolve_library_document


def _dup_doc() -> StockDocument:
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
        DividendRecord(ex_date=date(2010, 2, 15), payment_date=None, amount=0.5)
    ]
    return doc


def _good_doc() -> StockDocument:
    doc = StockDocument(symbol="INTU", name="Intuit")
    doc.price_history = [
        PriceHistory(
            date=date(2020, 1, 1) + timedelta(days=i),
            open=400.0,
            high=401.0,
            low=399.0,
            close=400.0 + i * 0.01,
            volume=1,
        )
        for i in range(300)
    ]
    doc.dividend_history = [
        DividendRecord(ex_date=date(2010, 2, 15), payment_date=None, amount=0.5)
    ]
    return doc


def test_resolve_prefers_fresh_trustworthy_document() -> None:
    cached = _dup_doc()
    fresh = _good_doc()
    with patch("services.shared_market_db.get_document", return_value=fresh):
        resolved = resolve_library_document("INTU", cached)
    assert resolved is fresh


def test_resolve_keeps_cached_when_fresh_missing() -> None:
    cached = _good_doc()
    with patch("services.shared_market_db.get_document", return_value=None):
        resolved = resolve_library_document("INTU", cached)
    assert resolved is cached
