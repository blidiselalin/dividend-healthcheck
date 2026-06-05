"""Unit tests for PostgresMarketStore."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from data_ingestion.models import StockDocument


def test_add_documents_executes_upsert():
    mock_conn = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_cm.__exit__ = MagicMock(return_value=False)

    doc = StockDocument(symbol="TST", name="Test Co")

    with patch("db.connection.ensure_schema"), patch(
        "db.connection.get_connection", return_value=mock_cm
    ):
        from db.postgres_market_store import PostgresMarketStore

        PostgresMarketStore().add_documents([doc])

    assert mock_conn.execute.called
    sql = mock_conn.execute.call_args[0][0]
    assert "INSERT INTO stock_documents" in sql
    assert "ON CONFLICT (symbol)" in sql


def test_get_by_symbol_returns_none_when_missing():
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = None
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with patch("db.connection.ensure_schema"), patch(
        "db.connection.get_connection", return_value=mock_cm
    ):
        from db.postgres_market_store import PostgresMarketStore

        assert PostgresMarketStore().get_by_symbol("MISSING") is None


def test_get_by_symbol_merges_table_columns():
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {
        "symbol": "KO",
        "document": {
            "symbol": "KO",
            "name": "Coca-Cola",
            "sector": "Unknown",
            "price_history": [],
            "dividend_history": [],
        },
        "sector": "Consumer Staples",
        "dividend_streak_years": 61,
        "dividend_yield": 3.1,
        "data_quality": 90.0,
        "last_updated": None,
        "source": "yahoo",
    }
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with patch("db.connection.ensure_schema"), patch(
        "db.connection.get_connection", return_value=mock_cm
    ):
        from db.postgres_market_store import PostgresMarketStore

        doc = PostgresMarketStore().get_by_symbol("KO")

    assert doc is not None
    assert doc.sector == "Consumer Staples"
    assert doc.dividend_yield == 3.1
    assert doc.dividend_streak_years == 61
