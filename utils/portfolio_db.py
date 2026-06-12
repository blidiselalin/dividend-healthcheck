"""Small helpers for portfolio SQLite (no Streamlit)."""

from __future__ import annotations

import sqlite3
from pathlib import Path


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
