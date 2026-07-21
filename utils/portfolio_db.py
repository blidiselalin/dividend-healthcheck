"""Small helpers for portfolio SQLite (no Streamlit)."""

from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Any

_FINGERPRINT_CACHE: dict[str, tuple[str, float]] = {}
_FINGERPRINT_CACHE_TTL = 2.0


def sqlite_holding_count(db_path: Path) -> int:
    """Count holdings in a SQLite portfolio file."""
    if not db_path.is_file():
        return 0
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute("SELECT COUNT(*) FROM holdings").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def holding_count(db_path: Path) -> int:
    """
    Count holdings for ``db_path``.

    When Postgres is active and ``db_path`` is the current user's portfolio file,
    query ``holdings`` by ``user_id``. Otherwise read the SQLite file directly
    (tests and explicit temp paths).
    """
    path = Path(db_path)
    try:
        from db.connection import holding_count_for_user, use_cloud_sql

        if use_cloud_sql():
            from auth.user_context import resolve_portfolio_db_path

            if path.resolve() == resolve_portfolio_db_path().resolve():
                return holding_count_for_user()
    except Exception:  # noqa: S110
        pass
    return sqlite_holding_count(path)


def invalidate_portfolio_db_fingerprint_cache() -> None:
    """Drop cached DB fingerprints after portfolio writes."""
    _FINGERPRINT_CACHE.clear()


def _fingerprint_cache_key(db_path: Path) -> str:
    try:
        from db.connection import use_cloud_sql

        if use_cloud_sql():
            from auth.user_context import current_user_id

            uid = current_user_id()
            if uid:
                return f"pg:{uid}"
    except Exception:  # noqa: S110
        pass
    return str(db_path.resolve())


def _row_tuple(row: Any) -> tuple[Any, ...]:
    if hasattr(row, "keys"):
        return tuple(row[key] for key in row.keys())  # noqa: SIM118
    return tuple(row)


def _fingerprint_query(
    connection: Any,
    table: str,
    columns_sql: str,
) -> list[Any]:
    """Return ordered rows for ``table``, or [] when the table is missing."""
    where = "WHERE user_id = ?" if getattr(connection, "is_postgres", False) else ""
    sql = f"SELECT {columns_sql} FROM {table} {where} ORDER BY 1"
    params = (connection.user_id,) if getattr(connection, "is_postgres", False) else ()
    try:
        return connection.execute(sql, params).fetchall()
    except Exception:
        return []


def compute_portfolio_db_fingerprint(
    db_path: Path | None = None,
    *,
    use_cache: bool = True,
) -> str:
    """
    Stable hash of portfolio-local tables that drive the UI.

    Used to detect when the database changed since the last session load.
    """
    from db.connection import open_portfolio_db

    if db_path is None:
        from services.portfolio_session import resolve_current_portfolio_db

        db_path = resolve_current_portfolio_db()

    path = Path(db_path)
    cache_key = _fingerprint_cache_key(path)
    now = time.monotonic()
    if use_cache:
        cached = _FINGERPRINT_CACHE.get(cache_key)
        if cached is not None and (now - cached[1]) < _FINGERPRINT_CACHE_TTL:
            return cached[0]

    hasher = hashlib.sha256()
    table_specs = (
        (
            "holdings",
            "symbol, shares, avg_cost_per_share, acquisition_value, commission, "
            "dividends_paid, estimated_avg_price, sort_order, company_name, "
            "dividend_tracking_since",
        ),
        ("purchase_journal", "id, symbol, purchase_date, price_usd"),
        (
            "monthly_deposits",
            "period_key, year, month, label, deposit_eur, deposit_usd, portfolio_eur, sort_order",
        ),
        (
            "dividend_receipts",
            "id, symbol, ex_date, pay_date, per_share_usd, shares_held, gross_usd",
        ),
        ("net_dividends", "period_key, year, month, net_usd"),
    )

    with open_portfolio_db(path) as connection:
        for table, columns in table_specs:
            hasher.update(table.encode())
            for row in _fingerprint_query(connection, table, columns):
                hasher.update(repr(_row_tuple(row)).encode())

    digest = hasher.hexdigest()
    if use_cache:
        _FINGERPRINT_CACHE[cache_key] = (digest, now)
    return digest
