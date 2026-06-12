"""Portfolio store helpers for PostgreSQL user_id scoping."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def pf_filter(connection: Any, column: str = "user_id") -> tuple[str, Sequence[Any]]:
    if connection.is_postgres:
        return f"{column} = ?", (connection.user_id,)
    return "1=1", ()


def pf_and(connection: Any, clause: str) -> tuple[str, Sequence[Any]]:
    filt, params = pf_filter(connection)
    return f"{clause} AND {filt}", params
