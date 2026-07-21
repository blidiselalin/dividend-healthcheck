"""Tests for admin database inspection service."""
# ruff: noqa: S101

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from services.db_admin_service import (
    MANAGED_TABLES,
    inspect_stock_symbol,
    is_safe_select_sql,
    list_managed_tables,
    preset_queries,
    run_readonly_query,
    sample_table_rows,
    storage_label,
    table_row_counts,
    validate_all_tables,
)


def _scalar_row(value: Any) -> dict[str, Any]:
    return {"value": value}


def test_is_safe_select_sql_allows_select() -> None:
    ok, _ = is_safe_select_sql("SELECT * FROM users")
    assert ok is True


def test_is_safe_select_sql_allows_with_cte() -> None:
    ok, _ = is_safe_select_sql("WITH x AS (SELECT 1 AS n) SELECT n FROM x")
    assert ok is True


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM users",
        "SELECT 1; DROP TABLE users",
        "SELECT * FROM users -- comment",
        "INSERT INTO users VALUES ('a')",
    ],
)
def test_is_safe_select_sql_blocks_unsafe(sql: str) -> None:
    ok, reason = is_safe_select_sql(sql)
    assert ok is False
    assert reason


def test_preset_queries_are_select_only() -> None:
    for name, sql in preset_queries().items():
        ok, reason = is_safe_select_sql(sql)
        assert ok, f"{name}: {reason}"


def test_managed_tables_include_core_schema() -> None:
    for table in (
        "users",
        "holdings",
        "stock_documents",
        "dividend_receipts",
        "schema_migrations",
    ):
        assert table in MANAGED_TABLES


def test_storage_label_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert storage_label() == "SQLite (local dev)"


@pytest.mark.postgres_mock
def test_storage_label_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://local/test")
    assert storage_label() == "PostgreSQL"


def test_list_managed_tables_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIVIDENDSCOPE_DATA_DIR", str(tmp_path))
    tables = list_managed_tables()
    assert isinstance(tables, list)


def test_validate_all_tables_sqlite_includes_chroma_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DIVIDENDSCOPE_DATA_DIR", str(tmp_path))
    with patch("services.shared_market_db.document_count", return_value=12):
        checks = validate_all_tables()
    chroma = next((c for c in checks if "Chroma" in c.name), None)
    assert chroma is not None
    assert chroma.row_count == 12


@pytest.mark.postgres_mock
def test_validate_all_tables_postgres(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: C901
    monkeypatch.setenv("DATABASE_URL", "postgresql://local/test")

    mock_conn = MagicMock()

    def fake_scalar(sql: str, params: Any = ()) -> Any:  # noqa: C901
        s = sql.lower()
        if "from users" in s and "is_active" in s:
            return _scalar_row(2)
        if "from users" in s and "is_admin" in s:
            return _scalar_row(1)
        if "from users" in s:
            return _scalar_row(3)
        if "access_requests" in s and "pending" in s:
            return _scalar_row(1)
        if "access_requests" in s:
            return _scalar_row(2)
        if "distinct user_id" in s:
            return _scalar_row(1)
        if "distinct symbol" in s and "holdings" in s:
            return _scalar_row(4)
        if "from holdings" in s:
            return _scalar_row(5)
        if "from purchase_journal" in s:
            return _scalar_row(0)
        if "from monthly_deposits" in s:
            return _scalar_row(0)
        if "from net_dividends" in s:
            return _scalar_row(0)
        if "from dividend_receipts" in s:
            return _scalar_row(0)
        if "from stock_documents" in s and "filter" in s:
            return {
                "price_year_plus": 400,
                "div_ttm_ready": 380,
                "price_two_year_plus": 350,
                "oldest_update": None,
                "newest_update": None,
            }
        if "from stock_documents" in s:
            return _scalar_row(500)
        if "from schema_migrations" in s and "order" in s:
            return [{"version": "001_initial", "applied_at": None}]
        if "from schema_migrations" in s:
            return _scalar_row(1)
        return _scalar_row(0)

    mock_conn.execute.side_effect = lambda sql, params=(): MagicMock(
        fetchone=lambda: fake_scalar(sql, params),
        fetchall=lambda: fake_scalar(sql, params) if "order by version" in sql.lower() else [],
    )

    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with (
        patch("services.db_admin_service.ensure_schema"),
        patch("services.db_admin_service.get_connection", return_value=mock_cm),
    ):
        checks = validate_all_tables()

    names = {c.name for c in checks}
    assert "users" in names
    assert "stock_documents" in names
    stock = next(c for c in checks if c.name == "stock_documents")
    assert stock.ok is True
    assert stock.row_count == 500


@pytest.mark.postgres_mock
def test_run_readonly_query_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://local/test")

    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = [
        {"symbol": "INTU", "price_points": 3000},
    ]

    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with (
        patch("services.db_admin_service.ensure_schema"),
        patch("services.db_admin_service.get_connection", return_value=mock_cm),
    ):
        result = run_readonly_query(
            "SELECT symbol, 3000 AS price_points FROM stock_documents WHERE symbol = 'INTU'"
        )

    assert result.ok is True
    assert result.rows[0]["symbol"] == "INTU"


@pytest.mark.postgres_mock
def test_run_readonly_query_applies_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://local/test")

    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = []

    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with (
        patch("services.db_admin_service.ensure_schema"),
        patch("services.db_admin_service.get_connection", return_value=mock_cm),
    ):
        run_readonly_query("SELECT * FROM users", row_limit=25)

    executed_sql = mock_conn.execute.call_args[0][0].lower()
    assert "limit 25" in executed_sql


def test_run_readonly_query_rejects_delete() -> None:
    result = run_readonly_query("DELETE FROM users")
    assert result.ok is False


def test_sample_table_rows_rejects_unknown_table() -> None:
    result = sample_table_rows("users;drop", allowed_tables=["users"])
    assert result.ok is False


def test_sample_table_rows_allows_listed_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with patch(
        "services.db_admin_service.run_readonly_query",
        return_value=type("R", (), {"ok": True, "columns": [], "rows": [], "message": "ok"})(),
    ) as run:
        sample_table_rows("holdings", allowed_tables=["holdings"], limit=10)
    run.assert_called_once_with("SELECT * FROM holdings", row_limit=10)


@pytest.mark.postgres_mock
def test_inspect_stock_symbol_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://local/test")

    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = None

    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with (
        patch("services.db_admin_service.ensure_schema"),
        patch("services.db_admin_service.get_connection", return_value=mock_cm),
    ):
        result = inspect_stock_symbol("ZZZZ")

    assert result["ok"] is False
    assert "not in stock_documents" in result["message"]


@pytest.mark.postgres_mock
def test_inspect_stock_symbol_with_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://local/test")

    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {
        "symbol": "INTU",
        "sector": "Technology",
        "price_points": 3200,
        "dividend_payments": 48,
        "first_price_date": "2010-01-04",
        "last_price_date": "2025-05-16",
        "first_dividend_date": "2010-02-01",
        "last_dividend_date": "2025-02-01",
        "last_updated": None,
        "dividend_streak_years": 10,
        "dividend_yield": 0.6,
        "data_quality": 0.9,
        "source": "ingest",
    }

    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with (
        patch("services.db_admin_service.ensure_schema"),
        patch("services.db_admin_service.get_connection", return_value=mock_cm),
    ):
        result = inspect_stock_symbol("intu")

    assert result["ok"] is True
    assert result["symbol"] == "INTU"
    assert result["yield_channel_ready"] is True


@pytest.mark.postgres_mock
def test_table_row_counts_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://local/test")

    mock_conn = MagicMock()
    mock_conn.execute.side_effect = lambda sql, params=(): MagicMock(
        fetchone=lambda: {"count": 3},
    )

    table_rows = [
        {"table_name": "users"},
        {"table_name": "holdings"},
        {"table_name": "stock_documents"},
    ]

    def execute_side_effect(sql: Any, params: Any = ()) -> Any:
        text = str(sql).lower()
        if "information_schema" in text:
            return MagicMock(fetchall=lambda: table_rows)
        return MagicMock(fetchone=lambda: {"count": 3})

    mock_conn.execute.side_effect = execute_side_effect

    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with (
        patch("services.db_admin_service.ensure_schema"),
        patch("services.db_admin_service.get_connection", return_value=mock_cm),
    ):
        counts = table_row_counts()

    assert counts["users"] == 3
    assert counts["holdings"] == 3
