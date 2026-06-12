"""Tests for normalized stock market history tables."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from data_ingestion.models import DividendRecord, PriceHistory, StockDocument


def test_upsert_document_history_writes_price_and_dividend_rows() -> None:
    doc = StockDocument(symbol="KO", name="Coke")
    doc.price_history = [
        PriceHistory(
            date=date(2024, 1, 2),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1_000_000,
            adjusted_close=100.5,
        )
    ]
    doc.dividend_history = [
        DividendRecord(ex_date=date(2024, 2, 1), payment_date=date(2024, 2, 15), amount=0.46)
    ]

    mock_conn = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with (
        patch("db.connection.ensure_schema"),
        patch("db.connection.get_connection", return_value=mock_cm),
    ):
        from db.postgres_market_history_store import PostgresMarketHistoryStore

        PostgresMarketHistoryStore().upsert_document_history(doc)

    assert mock_conn.execute.call_count >= 3
    sql_calls = " ".join(str(call.args[0]) for call in mock_conn.execute.call_args_list)
    assert "stock_price_history" in sql_calls
    assert "stock_dividend_history" in sql_calls


def test_attach_history_prefers_table_when_json_prices_are_duplicated() -> None:
    from datetime import date

    doc = StockDocument(symbol="INTU", name="Intuit")
    doc.price_history = [
        PriceHistory(
            date=date(2024, 6, 1),
            open=650.0,
            high=660.0,
            low=640.0,
            close=650.0,
            volume=900_000,
        )
    ] * 1257

    table_prices = [
        PriceHistory(
            date=date(2020, 1, 1) + __import__("datetime").timedelta(days=i),
            open=400.0 + i * 0.1,
            high=401.0,
            low=399.0,
            close=400.0 + i * 0.1,
            volume=1_000_000,
        )
        for i in range(300)
    ]

    from db.postgres_market_history_store import PostgresMarketHistoryStore

    store = PostgresMarketHistoryStore()
    with (
        patch.object(store, "load_price_history", return_value=table_prices),
        patch.object(store, "load_dividend_history", return_value=[]),
    ):
        updated = store.attach_history_to_document(doc)

    assert len(updated.price_history) == 300


def test_attach_history_uses_table_when_equal_or_richer() -> None:
    doc = StockDocument(symbol="AAPL", name="Apple")
    doc.price_history = []

    table_prices = [
        PriceHistory(
            date=date(2024, 1, 1),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1,
        )
    ] * 300

    from db.postgres_market_history_store import PostgresMarketHistoryStore

    store = PostgresMarketHistoryStore()
    with (
        patch.object(store, "load_price_history", return_value=table_prices),
        patch.object(store, "load_dividend_history", return_value=[]),
    ):
        updated = store.attach_history_to_document(doc)

    assert len(updated.price_history) == 300
