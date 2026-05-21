"""Small helpers for portfolio SQLite (no Streamlit)."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def holding_count(db_path: Path) -> int:
    if not db_path.is_file():
        return 0
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute("SELECT COUNT(*) FROM holdings").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0
