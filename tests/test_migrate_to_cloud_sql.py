"""Tests for legacy SQLite → Postgres migration helpers."""

import sqlite3
from pathlib import Path

from scripts.migrate_to_cloud_sql import _sqlite_has_table, _sqlite_rows


def test_sqlite_rows_skips_missing_table(tmp_path: Path):
    db_path = tmp_path / "portfolio.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE holdings (symbol TEXT PRIMARY KEY, shares REAL NOT NULL)"
        )
        conn.execute("INSERT INTO holdings VALUES ('AAPL', 10)")

    with sqlite3.connect(db_path) as conn:
        assert _sqlite_has_table(conn, "holdings")
        assert not _sqlite_has_table(conn, "net_dividends")
        assert len(_sqlite_rows(conn, "holdings")) == 1
        assert _sqlite_rows(conn, "net_dividends") == []
