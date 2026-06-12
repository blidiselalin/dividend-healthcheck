"""Unit tests for db.connection helpers."""
# ruff: noqa: S101

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from db.connection import (
    _migration_path,
    _migration_statements,
    adapt_sql,
    ensure_schema,
    get_database_url,
    holding_count_for_user,
    migrate_portfolio_user_id,
    use_cloud_sql,
)


def test_adapt_sql_replaces_placeholders() -> None:
    assert (
        adapt_sql("SELECT * FROM users WHERE id = ?", True) == "SELECT * FROM users WHERE id = %s"
    )
    assert (
        adapt_sql("SELECT * FROM users WHERE id = ?", False) == "SELECT * FROM users WHERE id = ?"
    )


def test_migration_statements_include_core_tables() -> None:
    statements = _migration_statements()
    assert statements, "migration file should produce statements"
    joined = "\n".join(statements).upper()
    assert "CREATE TABLE" in joined and "USERS" in joined
    for table in ("HOLDINGS", "STOCK_DOCUMENTS", "NET_DIVIDENDS", "DIVIDEND_RECEIPTS"):
        assert table in joined


def test_migration_file_exists() -> None:
    assert _migration_path().is_file()


@pytest.mark.postgres_mock
def test_use_cloud_sql_matches_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DIVIDENDSCOPE_DATABASE_URL", raising=False)
    assert use_cloud_sql() is False

    monkeypatch.setenv("DATABASE_URL", "postgresql://local/test")
    assert use_cloud_sql() is True
    assert get_database_url() == "postgresql://local/test"


@pytest.mark.postgres_mock
def test_holding_count_for_user_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://local/test")

    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {"count": 7}
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with (
        patch("db.connection.ensure_schema"),
        patch("db.connection.get_connection", return_value=mock_cm),
        patch("db.connection.portfolio_user_id", return_value="uid-1"),
    ):
        assert holding_count_for_user("uid-1") == 7


@pytest.mark.postgres_mock
def test_migrate_portfolio_user_id_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://local/test")

    mock_conn = MagicMock()
    mock_conn.execute.return_value.rowcount = 2
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with patch("db.connection.get_connection", return_value=mock_cm):
        assert migrate_portfolio_user_id("old", "new") is True
    assert mock_conn.execute.call_count == 5


def test_open_app_db_sqlite_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_path = tmp_path / "users.db"

    from db.connection import open_app_db

    with open_app_db(db_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT NOT NULL)")
        conn.execute("INSERT INTO users (id, email) VALUES (?, ?)", ("u1", "a@b.com"))

    with open_app_db(db_path) as conn:
        row = conn.execute("SELECT email FROM users WHERE id = ?", ("u1",)).fetchone()
    assert row["email"] == "a@b.com"


@pytest.mark.postgres_mock
def test_ensure_schema_bootstraps_schema_migrations_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import db.connection as db

    monkeypatch.setenv("DATABASE_URL", "postgresql://local/test")
    previous_schema_ready = db._schema_ready
    try:
        db._schema_ready = False

        migration = tmp_path / "001_initial.sql"
        migration.write_text(
            "CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY);",
            encoding="utf-8",
        )

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_conn)
        mock_cm.__exit__ = MagicMock(return_value=False)

        with (
            patch("db.connection.get_connection", return_value=mock_cm),
            patch("db.connection._migrations_dir", return_value=tmp_path),
        ):
            ensure_schema()

        executed_sql = [call.args[0] for call in mock_conn.execute.call_args_list]  # type: ignore[index]
        assert any("CREATE TABLE IF NOT EXISTS schema_migrations" in sql for sql in executed_sql)
        assert any("CREATE TABLE IF NOT EXISTS users" in sql for sql in executed_sql)
    finally:
        db._schema_ready = previous_schema_ready
