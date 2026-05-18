"""Tests for analysis evidence builders (no Streamlit)."""

from __future__ import annotations

from datetime import date, datetime

from data_ingestion.models import DataSource, DividendRecord, PriceHistory, StockDocument
from services.analysis_evidence import (
    build_evidence_rows,
    build_portfolio_session_rows,
    dividend_history_bounds,
    price_history_bounds,
)


def test_history_bounds_from_document():
    doc = StockDocument(
        symbol="KO",
        name="Coca-Cola",
        source=DataSource.YAHOO,
        last_updated=datetime(2026, 5, 1, 12, 0),
        price_history=[
            PriceHistory(
                date=date(2020, 1, 2),
                open=1,
                high=1,
                low=1,
                close=1,
                volume=1,
            ),
            PriceHistory(
                date=date(2026, 4, 30),
                open=1,
                high=1,
                low=1,
                close=1,
                volume=1,
            ),
        ],
        dividend_history=[
            DividendRecord(ex_date=date(2019, 3, 14), amount=0.4),
            DividendRecord(ex_date=date(2026, 3, 14), amount=0.49),
        ],
    )
    p_start, p_end, p_count = price_history_bounds(doc)
    assert p_count == 2
    assert p_start == date(2020, 1, 2)
    assert p_end == date(2026, 4, 30)

    d_start, d_end, d_count = dividend_history_bounds(doc)
    assert d_count == 2
    assert d_start == date(2019, 3, 14)


def test_build_evidence_rows_includes_intervals():
    doc = StockDocument(
        symbol="KO",
        source=DataSource.YAHOO,
        last_updated=datetime(2026, 5, 1),
        price_history=[
            PriceHistory(
                date=date(2024, 1, 1),
                open=1,
                high=1,
                low=1,
                close=1,
                volume=1,
            ),
        ],
    )
    rows = build_evidence_rows(
        "KO",
        vector_doc=doc,
        portfolio_prices_at=datetime(2026, 5, 18, 9, 30),
    )
    labels = [label for label, _ in rows]
    assert "Price history interval" in labels
    assert "Portfolio price snapshot" in labels
    assert any("2024-01-01" in detail for _, detail in rows)


def test_build_portfolio_session_rows():
    rows = build_portfolio_session_rows(
        loaded_at=datetime(2026, 5, 18),
        holding_count=3,
        charts_ready=2,
        library_ready=3,
    )
    assert rows[0] == ("Holdings in session", "3")
    assert "2 of 3" in rows[2][1]
