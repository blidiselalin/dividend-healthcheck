"""Ensure production paths write to PostgreSQL, not local SQLite files."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_vector_store_uses_postgres_when_database_url_set(postgres_env):
    from data_ingestion.vector_store import VectorStore

    with patch("db.postgres_market_store.PostgresMarketStore") as mock_pg:
        mock_pg.return_value.count.return_value = 0
        store = VectorStore()
        assert store._use_postgres is True
        assert store._pg_store is not None


def test_hourly_enrich_uses_shared_store(postgres_env):
    from services.hourly_market_update import enrich_stale_documents

    mock_store = MagicMock()
    mock_store.get_all_documents.return_value = []

    with patch("services.shared_market_db.get_shared_vector_store", return_value=mock_store):
        stats = enrich_stale_documents(limit=5)

    assert stats["candidates"] == 0
    mock_store.add_documents.assert_not_called()


def test_price_refresh_uses_shared_store(postgres_env):
    from services.db_price_refresh import refresh_market_library_prices

    mock_store = MagicMock()
    mock_store.get_all_documents.return_value = []

    with patch("services.shared_market_db.get_shared_vector_store", return_value=mock_store), patch(
        "services.db_price_refresh._collect_symbols", return_value=[]
    ):
        stats = refresh_market_library_prices(symbols=[])

    assert stats["total"] == 0
    mock_store.add_documents.assert_not_called()


def test_legacy_file_migration_skipped_when_postgres(postgres_env, tmp_path):
    from auth import migration

    user_dir = tmp_path / "users" / "owner"
    user_dir.mkdir(parents=True)
    assert migration.restore_owner_portfolio("owner", user_dir) is False
    assert migration.migrate_legacy_portfolio("owner", user_dir) is False
    assert migration.migrate_user_data_dir("old", "new") is False


def test_portfolio_store_does_not_create_sqlite_dir(postgres_env, tmp_path, monkeypatch):
    from data_ingestion.portfolio_store import PortfolioStore

    db_path = tmp_path / "users" / "u1" / "portfolio.db"
    monkeypatch.setattr(
        "data_ingestion.portfolio_store._default_portfolio_db_path",
        lambda: db_path,
    )

    with patch("db.connection.open_portfolio_db") as mock_open:
        mock_open.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        PortfolioStore()

    assert not db_path.parent.exists()
