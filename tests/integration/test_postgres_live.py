"""Live PostgreSQL integration tests (run in CI with a Postgres service)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.support.postgres_fixtures import postgres_configured, reset_db_connection_state, skip_without_postgres

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("reset_db_connection_state"),
]


@pytest.fixture(autouse=True)
def _require_postgres(skip_without_postgres):
    pass


def test_schema_and_market_document_roundtrip(pg_user_id: str):
    from data_ingestion.models import StockDocument
    from db.connection import ensure_schema, get_connection, use_cloud_sql
    from db.postgres_market_store import PostgresMarketStore

    assert use_cloud_sql()
    ensure_schema()

    doc = StockDocument(symbol="INTC", name="Intel Corp", sector="Technology")
    store = PostgresMarketStore()
    store.add_documents([doc])

    loaded = store.get_by_symbol("INTC")
    assert loaded is not None
    assert loaded.name == "Intel Corp"
    assert store.count() >= 1

    store.delete_symbols(["INTC"])


def test_portfolio_holdings_roundtrip(pg_user_id: str, monkeypatch):
    from data_ingestion.portfolio_store import PortfolioStore
    from db.connection import ensure_schema, get_connection, open_portfolio_db

    ensure_schema()
    monkeypatch.setattr("db.connection.portfolio_user_id", lambda: pg_user_id)

    store = PortfolioStore(seed=False)
    store.upsert_holding("KO", shares=10, avg_cost_per_share=55.0, company_name="Coca-Cola")

    holdings = store.list_holdings()
    assert len(holdings) == 1
    assert holdings[0].symbol == "KO"
    assert holdings[0].shares == 10

    store.delete_holding("KO")
    assert store.list_holdings() == []


def test_user_store_upsert_and_admin_preserve(pg_user_id: str):
    from auth.user_store import UserStore
    from db.connection import ensure_schema

    ensure_schema()
    store = UserStore()

    user = store.upsert_from_login(
        user_id=pg_user_id,
        email=f"{pg_user_id}@example.com",
        name="Integration User",
        picture_url=None,
        is_admin=True,
    )
    assert user.is_admin is True

    again = store.upsert_from_login(
        user_id=pg_user_id,
        email=f"{pg_user_id}@example.com",
        name="Integration User",
        picture_url=None,
        is_admin=False,
    )
    assert again.is_admin is True


def test_dividend_and_deposit_stores(pg_user_id: str, monkeypatch):
    from data_ingestion.deposits_store import DepositsStore
    from data_ingestion.dividend_income_store import DividendIncomeStore
    from db.connection import ensure_schema

    ensure_schema()
    monkeypatch.setattr("db.connection.portfolio_user_id", lambda: pg_user_id)

    deposits = DepositsStore(seed=False)
    dep = deposits.upsert_deposit(
        year=2025,
        month=5,
        label="May 2025",
        deposit_eur=100.0,
        deposit_usd=110.0,
        portfolio_eur=5000.0,
    )
    assert dep.period_key == "2025-05"
    assert len(deposits.list_deposits()) == 1

    dividends = DividendIncomeStore(seed=False)
    with dividends._connect() as conn:
        conn.execute(
            """
            INSERT INTO net_dividends (user_id, period_key, year, month, net_usd)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (user_id, period_key) DO UPDATE SET net_usd = excluded.net_usd
            """,
            (conn.user_id, "2025-05", 2025, 5, 42.50),
        )
    listed = dividends.list_dividends()
    assert len(listed) == 1
    assert listed[0].net_usd == pytest.approx(42.50)


def test_migrate_script_users_and_portfolio(tmp_path: Path, pg_user_id: str):
    import sqlite3

    from db.connection import ensure_schema, get_connection, use_cloud_sql
    from scripts.migrate_to_cloud_sql import _import_portfolio_db, _import_users

    assert use_cloud_sql()
    ensure_schema()

    users_db = tmp_path / "users.db"
    with sqlite3.connect(users_db) as conn:
        conn.execute(
            """
            CREATE TABLE users (
              id TEXT PRIMARY KEY, email TEXT NOT NULL, name TEXT, picture_url TEXT,
              created_at TEXT NOT NULL, last_login_at TEXT NOT NULL,
              is_active INTEGER NOT NULL, is_admin INTEGER NOT NULL
            )
            """
        )
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO users VALUES (?,?,?,?,?,?,?,?)",
            (pg_user_id, f"{pg_user_id}@example.com", "Migrator", None, now, now, 1, 0),
        )

    portfolio_db = tmp_path / "users" / pg_user_id / "portfolio.db"
    portfolio_db.parent.mkdir(parents=True)
    with sqlite3.connect(portfolio_db) as conn:
        conn.execute(
            """
            CREATE TABLE holdings (
              symbol TEXT PRIMARY KEY, shares REAL, avg_cost_per_share REAL,
              acquisition_value REAL, commission REAL, dividends_paid REAL,
              estimated_avg_price REAL, sort_order INTEGER, company_name TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO holdings VALUES ('PEP', 5, 150, 750, 0, 0, 150, 1, 'PepsiCo')"
        )

    assert _import_users(tmp_path) == 1
    stats = _import_portfolio_db(portfolio_db, pg_user_id, data_dir=tmp_path)
    assert stats["holdings"] == 1

    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM holdings WHERE user_id = %s",
            (pg_user_id,),
        ).fetchone()
    assert int(row["count"]) == 1


def test_market_library_migration_from_fallback_json(tmp_path: Path):
    from data_ingestion.models import StockDocument
    from db.connection import ensure_schema, use_cloud_sql
    from scripts.migrate_to_cloud_sql import _import_market_library

    assert use_cloud_sql()
    ensure_schema()

    vdb = tmp_path / "vectordb"
    vdb.mkdir()
    doc = StockDocument(symbol="MIG", name="Migrate Test")
    (vdb / "fallback_store.json").write_text(
        json.dumps({doc.document_id: doc.to_full_dict()})
    )

    imported = _import_market_library(tmp_path)
    assert imported == 1

    from db.postgres_market_store import PostgresMarketStore

    assert PostgresMarketStore().get_by_symbol("MIG") is not None
    PostgresMarketStore().delete_symbols(["MIG"])
