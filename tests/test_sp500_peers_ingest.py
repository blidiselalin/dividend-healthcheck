"""Tests for S&P 500 and top-dividend library ingest helpers."""
# ruff: noqa: S101

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from data_ingestion.models import DataSource, StockDocument


def test_ensure_top_dividend_all_present(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import sp500_peers_service

    store = MagicMock()
    store.get_all_documents.return_value = [
        StockDocument(symbol=s, name=s, source=DataSource.YAHOO) for s in ("KO", "PEP")
    ]
    monkeypatch.setattr(sp500_peers_service, "_store", lambda: store)
    monkeypatch.setattr(
        "data_ingestion.dividend_universe.get_top_dividend_symbols",
        lambda: ["KO", "PEP"],
    )

    stats = sp500_peers_service.ensure_top_dividend_in_vectordb()
    assert stats["created"] == 0
    assert stats["already_present"] == 2
    store.add_documents.assert_not_called()


def test_ensure_top_dividend_creates_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import sp500_peers_service

    store = MagicMock()
    store.get_all_documents.return_value = []
    monkeypatch.setattr(sp500_peers_service, "_store", lambda: store)
    monkeypatch.setattr(
        "data_ingestion.dividend_universe.get_top_dividend_symbols",
        lambda: ["KO"],
    )

    mock_doc = StockDocument(symbol="KO", name="Coca-Cola", source=DataSource.YAHOO)
    mock_enricher = MagicMock()
    mock_enricher.fetch_document.return_value = mock_doc

    with patch(
        "data_ingestion.stock_enricher.create_stock_enricher",
        return_value=mock_enricher,
    ):
        stats = sp500_peers_service.ensure_top_dividend_in_vectordb(limit=1)

    assert stats["created"] == 1
    assert stats["errors"] == 0
    store.add_documents.assert_called_once()
    added = store.add_documents.call_args[0][0]
    assert added[0].symbol == "KO"


def test_ensure_sp500_no_store_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import sp500_peers_service

    monkeypatch.setattr(sp500_peers_service, "_store", lambda: None)
    stats = sp500_peers_service.ensure_sp500_in_vectordb(limit=5)
    assert stats["errors"] == 1


def test_remove_delisted_from_market_library(postgres_env: Any) -> None:
    from services.db_price_refresh import remove_delisted_from_market_library

    mock_store = MagicMock()
    mock_store.delete_symbols.return_value = 2

    with patch(
        "services.shared_market_db.get_shared_vector_store",
        return_value=mock_store,
    ):
        result = remove_delisted_from_market_library(["ZZ", "WBA"])

    assert result["removed"] == 2
    assert result["symbols"] == ["WBA", "ZZ"]
    mock_store.delete_symbols.assert_called_once_with(["WBA", "ZZ"])
