"""Tests for analysis evidence builders (no Streamlit)."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date, datetime

from data_ingestion.models import (
    DataSource,
    DividendRecord,
    PriceHistory,
    StockDocument,
)
from services.analysis_evidence import (
    build_evidence_rows,
    build_portfolio_session_rows,
    dividend_history_bounds,
    price_history_bounds,
    yield_channel_bounds,
)
from services.yield_channel_chart import YieldChannelData


def test_history_bounds_from_document() -> None:
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
            DividendRecord(
                ex_date=date(2019, 3, 14),
                payment_date=date(2019, 4, 1),
                amount=0.4,
            ),
            DividendRecord(
                ex_date=date(2026, 3, 14),
                payment_date=date(2026, 4, 1),
                amount=0.49,
            ),
        ],
    )
    p_start, p_end, p_count = price_history_bounds(doc)
    assert p_count == 2
    assert p_start == date(2020, 1, 2)
    assert p_end == date(2026, 4, 30)

    d_start, d_end, d_count = dividend_history_bounds(doc)
    assert d_count == 2
    assert d_start == date(2019, 3, 14)


def test_build_evidence_rows_includes_intervals() -> None:
    doc = StockDocument(
        symbol="KO",
        name="Coca-Cola",
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


def test_build_portfolio_session_rows() -> None:
    rows = build_portfolio_session_rows(
        loaded_at=datetime(2026, 5, 18),
        holding_count=3,
        charts_ready=2,
        library_ready=3,
    )
    assert rows[0] == ("Holdings in session", "3")
    assert "2 of 3" in rows[2][1]


def test_yield_channel_bounds_from_channel_data() -> None:
    channel = YieldChannelData(
        symbol="KO",
        company_name="Coca-Cola",
        current_yield=3.0,
        current_price=60.0,
        current_dividend=1.8,
        avg_yield=3.0,
        median_yield=3.0,
        min_yield=2.5,
        max_yield=3.5,
        std_yield=0.2,
        yield_10th=2.7,
        yield_25th=2.85,
        yield_75th=3.15,
        yield_90th=3.3,
        deep_value_price=50.0,
        value_price=55.0,
        fair_value_price=58.0,
        caution_price=62.0,
        expensive_price=65.0,
        zone="Fair Value",
        zone_score=50.0,
        percentile=50.0,
        dates=[date(2024, 1, 1), date(2026, 4, 30)],
        prices=[50.0, 60.0],
        yields=[3.0, 3.1],
        annual_dividends=[3.0, 3.1],
        years_analyzed=10,
        data_points=2,
    )
    start, end, count = yield_channel_bounds(channel)
    assert count == 2
    assert start == date(2024, 1, 1)
    assert end == date(2026, 4, 30)


def test_build_evidence_rows_includes_yield_channel() -> None:
    doc = StockDocument(symbol="KO", name="Coca-Cola", source=DataSource.YAHOO)
    channel = YieldChannelData(
        symbol="KO",
        company_name="Coca-Cola",
        current_yield=3.0,
        current_price=60.0,
        current_dividend=1.8,
        avg_yield=3.0,
        median_yield=3.0,
        min_yield=2.5,
        max_yield=3.5,
        std_yield=0.2,
        yield_10th=2.7,
        yield_25th=2.85,
        yield_75th=3.15,
        yield_90th=3.3,
        deep_value_price=50.0,
        value_price=55.0,
        fair_value_price=58.0,
        caution_price=62.0,
        expensive_price=65.0,
        zone="Fair Value",
        zone_score=50.0,
        percentile=50.0,
        dates=[date(2020, 6, 1)],
        prices=[55.0],
        yields=[3.0],
        annual_dividends=[3.0],
        years_analyzed=10,
        data_points=1,
    )
    rows = build_evidence_rows("KO", vector_doc=doc, yield_channel_data=channel)
    labels = [label for label, _ in rows]
    assert "Yield channel analysis window" in labels
    assert "Yield zone method" in labels
    assert any("2.70%" in detail and "3.30%" in detail for _, detail in rows)


def test_build_evidence_rows_missing_library() -> None:
    rows = build_evidence_rows("ZZZZ", portfolio_prices_at=None)
    detail = dict(rows)["Analysed stock library"]
    assert "ZZZZ" in detail
