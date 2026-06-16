"""Unit tests for shared_market_db."""
# ruff: noqa: S101

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.postgres_mock
def test_shared_market_db_status_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://local/test")

    mock_store = MagicMock()
    mock_store.count.return_value = 42

    with patch("services.shared_market_db.get_shared_vector_store", return_value=mock_store):
        from services.shared_market_db import shared_market_db_status

        status = shared_market_db_status()

    assert status["storage"] == "postgresql"
    assert status["document_count"] == 42
    assert status["populated"] is True
    assert "stock_documents" in status["path"]


def test_get_document_delegates_to_store() -> None:
    mock_store = MagicMock()
    mock_doc = MagicMock()
    mock_store.get_by_symbol.return_value = mock_doc

    with patch("services.shared_market_db.get_shared_vector_store", return_value=mock_store):
        from services.shared_market_db import get_document

        assert get_document("ko") is mock_doc
    mock_store.get_by_symbol.assert_called_once_with("KO")


def test_load_documents_uses_single_batch_call() -> None:
    """load_documents must call get_by_symbols once, not get_by_symbol per ticker."""
    import services.shared_market_db as smd

    mock_doc_a = MagicMock()
    mock_doc_b = MagicMock()
    mock_store = MagicMock()
    mock_store.get_by_symbols.return_value = {"AAPL": mock_doc_a, "KO": mock_doc_b}

    with patch("services.shared_market_db.get_shared_vector_store", return_value=mock_store):
        result = smd.load_documents(["aapl", "ko", "MSFT"])

    mock_store.get_by_symbols.assert_called_once()
    called_symbols = mock_store.get_by_symbols.call_args[0][0]
    assert set(called_symbols) == {"AAPL", "KO", "MSFT"}
    assert result == {"AAPL": mock_doc_a, "KO": mock_doc_b}


def test_load_documents_empty_input_returns_empty_dict() -> None:
    import services.shared_market_db as smd

    mock_store = MagicMock()

    with patch("services.shared_market_db.get_shared_vector_store", return_value=mock_store):
        result = smd.load_documents([])

    mock_store.get_by_symbols.assert_not_called()
    assert result == {}


def test_load_documents_uppercases_symbols() -> None:
    import services.shared_market_db as smd

    mock_store = MagicMock()
    mock_store.get_by_symbols.return_value = {}

    with patch("services.shared_market_db.get_shared_vector_store", return_value=mock_store):
        smd.load_documents(["ko", "jnj"])

    called_symbols = mock_store.get_by_symbols.call_args[0][0]
    assert set(called_symbols) == {"KO", "JNJ"}
