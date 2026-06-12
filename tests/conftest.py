"""Shared pytest fixtures for portfolio and data-layer tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from data_ingestion.deposits_store import DepositsStore
from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore

pytest_plugins = ["tests.support.postgres_fixtures"]


@pytest.fixture(autouse=True)
def use_sqlite_backend(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests use isolated SQLite; integration tests keep DATABASE_URL."""
    if request.node.get_closest_marker("integration"):
        yield
        return
    if request.node.get_closest_marker("postgres_mock"):
        yield
        return

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DIVIDENDSCOPE_DATABASE_URL", raising=False)
    monkeypatch.setenv("PYTEST_USE_SQLITE", "1")

    import db.connection as db

    db._pool = None
    db._schema_ready = False
    yield
    db._pool = None
    db._schema_ready = False


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Isolated SQLite database path (holdings, journal, deposits share one file)."""
    return tmp_path / "portfolio.db"


@pytest.fixture
def portfolio_store(temp_db: Path) -> PortfolioStore:
    return PortfolioStore(db_path=temp_db, seed=False)


@pytest.fixture
def journal_store(temp_db: Path) -> PurchaseJournalStore:
    return PurchaseJournalStore(db_path=temp_db, seed=False)


@pytest.fixture
def deposits_store(temp_db: Path) -> DepositsStore:
    return DepositsStore(db_path=temp_db, seed=False)


@pytest.fixture
def store() -> Any:
    """Shared market library for optional data-quality checks (skipped when empty)."""
    from data_ingestion.vector_store import VectorStore
    from db.connection import use_cloud_sql
    from tests.support.postgres_fixtures import postgres_reachable

    if use_cloud_sql() and not postgres_reachable():
        pytest.skip("PostgreSQL unavailable for market library checks")

    vector_store = VectorStore()
    if getattr(vector_store, "_use_fallback", False):
        pytest.skip("Local fallback store empty; run ingest for data-quality tests")
    count = vector_store.count()
    if count == 0:
        pytest.skip("Market library is empty; run ingest to enable data-quality tests")
    if count < 100:
        pytest.skip(
            f"Market library has only {count} documents; run full ingest for data-quality tests"
        )
    return vector_store


@pytest.fixture
def sample_deposits(deposits_store: DepositsStore) -> DepositsStore:
    """Two months of deposit history for service-layer tests."""
    deposits_store.upsert_deposit(
        year=2024,
        month=1,
        label="January 2024",
        deposit_eur=1000.0,
        deposit_usd=1100.0,
        portfolio_eur=10000.0,
    )
    deposits_store.upsert_deposit(
        year=2024,
        month=2,
        label="February 2024",
        deposit_eur=500.0,
        deposit_usd=550.0,
        portfolio_eur=10800.0,
    )
    return deposits_store


@pytest.fixture
def portfolio_with_trades(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> tuple[PortfolioStore, PurchaseJournalStore]:
    """One holding with two journal lots."""
    portfolio_store.upsert_holding(
        "KO",
        shares=20,
        avg_cost_per_share=50.0,
        company_name="Coca-Cola Co",
    )
    journal_store.add_purchase("KO", date(2023, 6, 1), 48.0)
    journal_store.add_purchase("KO", date(2024, 1, 15), 52.0)
    return portfolio_store, journal_store
