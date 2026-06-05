"""Tests for history-based dividend yield enrichment."""

from __future__ import annotations

from datetime import date

from data_ingestion.models import DividendRecord, PriceHistory, StockDocument
from models.stock import StockData
from utils.converters import document_to_stock_data
from utils.stock_history_enrichment import enrich_stock_data_from_history


def _sample_document() -> StockDocument:
    doc = StockDocument(symbol="INTU", name="Intuit", sector="Technology")
    doc.dividend_yield = None
    doc.annual_dividend = None
    doc.current_price = None
    doc.price_history = [
        PriceHistory(
            date=date(2024, 1, 2),
            open=600.0,
            high=610.0,
            low=595.0,
            close=600.0,
            volume=1_000_000,
        )
    ]
    doc.dividend_history = [
        DividendRecord(ex_date=date(2024, m, 1), payment_date=date(2024, m, 15), amount=1.0)
        for m in (2, 5, 8, 11)
    ]
    return doc


def test_enrich_computes_yield_from_dividend_history():
    doc = _sample_document()
    stock = document_to_stock_data(doc)
    stock.price = 600.0
    stock.dividend_yield_pct = None

    enriched, source = enrich_stock_data_from_history(stock, doc)

    assert source == "history"
    assert enriched.dividend_rate == 4.0
    assert enriched.dividend_yield_pct == round((4.0 / 600.0) * 100, 2)


def test_enrich_uses_price_history_when_price_missing():
    doc = _sample_document()
    stock = document_to_stock_data(doc)
    stock.price = None

    enriched, _ = enrich_stock_data_from_history(stock, doc)

    assert enriched.price == 600.0
    assert enriched.dividend_yield_pct is not None
