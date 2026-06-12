"""
Database connection and schema management for PostgreSQL.

When DATABASE_URL (or DIVIDENDSCOPE_DATABASE_URL) is set — including the
default Docker Compose `postgres` service — all app data uses PostgreSQL.
Otherwise stores fall back to local SQLite / ChromaDB files (Mac dev / tests).
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_pool = None
_schema_ready = False


def get_database_url() -> str | None:
    url = (
        os.environ.get("DATABASE_URL") or os.environ.get("DIVIDENDSCOPE_DATABASE_URL") or ""
    ).strip()

    if not url:
        try:
            import streamlit as st

            url = str(st.secrets.get("DATABASE_URL", "")).strip()
        except Exception:
            pass

    if not url and os.environ.get("PYTEST_USE_SQLITE") != "1":
        # Force PostgreSQL connection by default
        url = "postgresql://dividendscope:pass@127.0.0.1:5432/dividendscope"

    return url or None


def use_cloud_sql() -> bool:
    """True when DATABASE_URL is set (Docker Postgres or any remote Postgres)."""
    if os.environ.get("PYTEST_USE_SQLITE") == "1":
        return False
    return True


def use_postgres_db() -> bool:
    """Alias for use_cloud_sql()."""
    return use_cloud_sql()


def _migrations_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "migrations"


def _migration_path() -> Path:
    return _migrations_dir() / "001_initial.sql"


def _migration_statements_from_path(path: Path) -> list[str]:
    """Split one migration file into executable statements (ignore comment lines)."""
    sql = path.read_text(encoding="utf-8")
    lines = [
        line for line in sql.splitlines() if line.strip() and not line.strip().startswith("--")
    ]
    statements: list[str] = []
    for chunk in "\n".join(lines).split(";"):
        statement = chunk.strip()
        if statement:
            statements.append(statement)
    return statements


def _migration_statements() -> list[str]:
    statements: list[str] = []
    for path in sorted(_migrations_dir().glob("*.sql")):
        statements.extend(_migration_statements_from_path(path))
    return statements


def ensure_schema() -> None:
    """Apply pending SQL migrations once per process."""
    global _schema_ready
    if not use_postgres_db() or _schema_ready:
        return

    applied = 0
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version TEXT PRIMARY KEY,
              applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        for path in sorted(_migrations_dir().glob("*.sql")):
            version = path.stem
            row = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version = %s",
                (version,),
            ).fetchone()
            if row:
                continue
            for statement in _migration_statements_from_path(path):
                conn.execute(statement)
            conn.execute(
                """
                INSERT INTO schema_migrations (version)
                VALUES (%s)
                ON CONFLICT (version) DO NOTHING
                """,
                (version,),
            )
            applied += 1
    _schema_ready = True
    logger.info("PostgreSQL schema ready (%s new migration(s))", applied)


def _get_pool() -> Any:
    global _pool
    if _pool is not None:
        return _pool
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    url = get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")

    _pool = ConnectionPool(
        url,
        min_size=1,
        max_size=8,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    logger.info("PostgreSQL connection pool initialized")
    return _pool


@contextmanager
def get_connection() -> Iterator[Any]:
    """Borrow a PostgreSQL connection from the pool."""
    pool = _get_pool()
    with pool.connection() as conn:
        yield conn
        conn.commit()


def adapt_sql(sql: str, is_postgres: bool = True) -> str:
    if not is_postgres:
        return sql
    return sql.replace("?", "%s")


def portfolio_user_id() -> str:
    try:
        from auth.user_context import current_user_id

        uid = current_user_id()
        if uid:
            return uid
    except Exception:  # noqa: S110
        pass
    return "local"


def _ensure_user_row(user_id: str) -> None:
    if not use_cloud_sql():
        return
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, name, created_at, last_login_at, is_active, is_admin)
            VALUES (%s, %s, %s, now(), now(), TRUE, FALSE)
            ON CONFLICT (id) DO NOTHING
            """,
            (user_id, f"{user_id}@users.local", "User"),
        )


class DbCursor:
    def __init__(self, cursor: Any, *, is_postgres: bool) -> None:
        self._cursor = cursor
        self.is_postgres = is_postgres
        self.lastrowid: int | None = None
        self.rowcount: int = 0

    def fetchone(self) -> Any | None:
        return self._cursor.fetchone()

    def fetchall(self) -> Sequence[Any]:
        return list(self._cursor.fetchall())


class DbConnection:
    """SQLite-compatible wrapper for PostgreSQL or SQLite connections."""

    def __init__(
        self,
        connection: Any,
        *,
        is_postgres: bool,
        user_id: str | None = None,
    ) -> None:
        self._connection = connection
        self.is_postgres = is_postgres
        self.user_id = user_id

    def execute(
        self,
        sql: str,
        params: Sequence[Any] = (),
    ) -> DbCursor:
        sql = adapt_sql(sql, self.is_postgres)
        cursor = self._connection.execute(sql, params)
        wrapped = DbCursor(cursor, is_postgres=self.is_postgres)
        wrapped.rowcount = cursor.rowcount
        if not self.is_postgres:
            wrapped.lastrowid = cursor.lastrowid
        return wrapped

    def executemany(self, sql: str, params_seq: Sequence[Sequence[Any]]) -> None:
        sql = adapt_sql(sql, self.is_postgres)
        self._connection.executemany(sql, params_seq)

    def commit(self) -> None:
        self._connection.commit()

    def close(self) -> None:
        if not self.is_postgres:
            self._connection.close()


@contextmanager
def open_app_db(db_path: Path | None = None) -> Iterator[DbConnection]:
    """Users + access_requests database."""
    if use_cloud_sql():
        ensure_schema()
        with get_connection() as conn:
            yield DbConnection(conn, is_postgres=True)
        return

    path = Path(db_path) if db_path else None
    if path is None:
        from config import DATA_DIR

        path = DATA_DIR / "users.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(path)
    raw.row_factory = sqlite3.Row
    wrapper = DbConnection(raw, is_postgres=False)
    try:
        yield wrapper
        wrapper.commit()
    finally:
        raw.close()


@contextmanager
def open_portfolio_db(
    db_path: Path | None = None,
    *,
    user_id: str | None = None,
) -> Iterator[DbConnection]:
    """Per-user portfolio tables."""
    if use_cloud_sql():
        ensure_schema()
        uid = user_id or portfolio_user_id()
        _ensure_user_row(uid)
        with get_connection() as conn:
            yield DbConnection(conn, is_postgres=True, user_id=uid)
        return

    if db_path is None:
        try:
            from auth.user_context import resolve_portfolio_db_path

            db_path = resolve_portfolio_db_path()
        except Exception:
            from config import DATA_DIR

            db_path = DATA_DIR / "portfolio.db"
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(path)
    raw.row_factory = sqlite3.Row
    wrapper = DbConnection(raw, is_postgres=False)
    try:
        yield wrapper
        wrapper.commit()
    finally:
        raw.close()


def migrate_portfolio_user_id(old_user_id: str, new_user_id: str) -> bool:
    """Move portfolio rows when canonical user id changes."""
    if not old_user_id or not new_user_id or old_user_id == new_user_id:
        return False
    if not use_cloud_sql():
        from auth.migration import migrate_user_data_dir

        return migrate_user_data_dir(old_user_id, new_user_id)

    tables = (
        "holdings",
        "purchase_journal",
        "monthly_deposits",
        "net_dividends",
        "dividend_receipts",
    )
    moved = False
    with get_connection() as conn:
        for table in tables:
            cur = conn.execute(
                f"UPDATE {table} SET user_id = %s WHERE user_id = %s",  # noqa: S608
                (new_user_id, old_user_id),
            )
            if cur.rowcount:
                moved = True
    return moved


def holding_count_for_user(user_id: str | None = None) -> int:
    uid = user_id or portfolio_user_id()
    if use_cloud_sql():
        ensure_schema()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM holdings WHERE user_id = %s",
                (uid,),
            ).fetchone()
        return int(row["count"]) if row else 0

    from auth.user_context import resolve_user_data_dir

    db_path = resolve_user_data_dir() / "portfolio.db"
    from utils.portfolio_db import holding_count

    return holding_count(db_path)
