"""Unit tests for shared_market_db."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


import pytest


@pytest.mark.postgres_mock
def test_shared_market_db_status_postgres(monkeypatch):
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


def test_get_document_delegates_to_store():
    mock_store = MagicMock()
    mock_doc = MagicMock()
    mock_store.get_by_symbol.return_value = mock_doc

    with patch("services.shared_market_db.get_shared_vector_store", return_value=mock_store):
        from services.shared_market_db import get_document

        assert get_document("ko") is mock_doc
    mock_store.get_by_symbol.assert_called_once_with("KO")
