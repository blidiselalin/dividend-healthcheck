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
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

_pool = None
_schema_ready = False


def get_database_url() -> Optional[str]:
    return (
        os.environ.get("DATABASE_URL")
        or os.environ.get("DIVIDENDSCOPE_DATABASE_URL")
        or ""
    ).strip() or None


def use_cloud_sql() -> bool:
    """True when DATABASE_URL is set (Docker Postgres or any remote Postgres)."""
    return bool(get_database_url())


def use_postgres_db() -> bool:
    """Alias for use_cloud_sql()."""
    return use_cloud_sql()


def _migration_path() -> Path:
    return Path(__file__).resolve().parent.parent / "migrations" / "001_initial.sql"


def ensure_schema() -> None:
    """Apply SQL migrations once per process."""
    global _schema_ready
    if not use_cloud_sql() or _schema_ready:
        return

    sql = _migration_path().read_text(encoding="utf-8")
    with get_connection() as conn:
        for statement in sql.split(";"):
            chunk = statement.strip()
            if chunk and not chunk.startswith("--"):
                conn.execute(chunk)
    _schema_ready = True
    logger.info("PostgreSQL schema ready")


def _get_pool():
    global _pool
    if _pool is not None:
        return _pool
    import psycopg
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
    except Exception:
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
        self.lastrowid: Optional[int] = None
        self.rowcount: int = 0

    def fetchone(self) -> Optional[Any]:
        return self._cursor.fetchone()

    def fetchall(self) -> Sequence[Any]:
        return self._cursor.fetchall()


class DbConnection:
    """SQLite-compatible wrapper for PostgreSQL or SQLite connections."""

    def __init__(
        self,
        connection: Any,
        *,
        is_postgres: bool,
        user_id: Optional[str] = None,
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
def open_app_db(db_path: Optional[Path] = None) -> Iterator[DbConnection]:
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
    db_path: Optional[Path] = None,
    *,
    user_id: Optional[str] = None,
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
    )
    moved = False
    with get_connection() as conn:
        for table in tables:
            cur = conn.execute(
                f"UPDATE {table} SET user_id = %s WHERE user_id = %s",
                (new_user_id, old_user_id),
            )
            if cur.rowcount:
                moved = True
    return moved


def holding_count_for_user(user_id: Optional[str] = None) -> int:
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


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    if "--migrate" in sys.argv:
        ensure_schema()
        print("Schema applied.")
    else:
        print(f"cloud_sql={use_cloud_sql()} url={'set' if get_database_url() else 'unset'}")
