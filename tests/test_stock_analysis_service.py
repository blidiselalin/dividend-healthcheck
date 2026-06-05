"""Tests for independent stock analysis service."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from data_ingestion.models import DividendRecord, PriceHistory, StockDocument


def _library_doc() -> StockDocument:
    doc = StockDocument(symbol="INTU", name="Intuit", sector="Technology")
    doc.dividend_yield = None
    doc.price_history = [
        PriceHistory(
            date=date(2024, 6, 1),
            open=650.0,
            high=660.0,
            low=640.0,
            close=650.0,
            volume=900_000,
        )
    ] * 200
    doc.dividend_history = [
        DividendRecord(ex_date=date(2024, m, 1), payment_date=date(2024, m, 15), amount=1.1)
        for m in (2, 5, 8, 11)
    ]
    return doc


def test_stock_data_from_document_uses_history():
    from services.stock_analysis_service import stock_data_from_document

    doc = _library_doc()
    with patch("services.live_price.apply_live_price", side_effect=lambda s: s):
        stock = stock_data_from_document(doc, apply_live_price=True)

    assert stock.dividend_rate == 4.4
    assert stock.dividend_yield_pct is not None
    assert stock.dividend_yield_pct > 0


def test_load_independent_stock_analysis_from_library():
    from services.stock_analysis_service import load_independent_stock_analysis

    doc = _library_doc()
    mock_channel = MagicMock(current_yield=0.68)

    with patch("services.live_price.apply_live_price", side_effect=lambda s: s), patch(
        "services.stock_analysis_service.load_yield_channel_data",
        return_value=mock_channel,
    ):
        analysis = load_independent_stock_analysis("INTU", document=doc)

    assert analysis is not None
    assert analysis.document is doc
    assert analysis.price_history_points == 200
    assert analysis.dividend_history_points == 4
    assert analysis.yield_channel is mock_channel


def test_postgres_document_from_row_merges_indexed_columns():
    from db.postgres_market_store import _document_from_row

    row = {
        "symbol": "INTU",
        "document": {
            "symbol": "INTU",
            "name": "Intuit",
            "sector": "Unknown",
            "price_history": [],
            "dividend_history": [],
        },
        "sector": "Technology",
        "dividend_streak_years": 5,
        "dividend_yield": 0.65,
        "data_quality": 88.0,
        "last_updated": "2024-06-01T12:00:00+00:00",
        "source": "yahoo",
    }
    doc = _document_from_row(row)

    assert doc.sector == "Technology"
    assert doc.dividend_yield == 0.65
    assert doc.dividend_streak_years == 5
    assert doc.data_quality == 88.0
