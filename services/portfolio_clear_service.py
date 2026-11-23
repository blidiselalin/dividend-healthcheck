"""
Wipe all portfolio-local tables for the current user (full replace before broker import).

REPLACE snapshots these tables first. A failed import restores that snapshot.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from db.connection import open_portfolio_db
from services.portfolio_context import create_portfolio_context

logger = logging.getLogger(__name__)

_PORTFOLIO_TABLES: tuple[str, ...] = (
    "holdings",
    "purchase_journal",
    "dividend_receipts",
    "net_dividends",
    "monthly_deposits",
)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_replace_active: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "portfolio_replace_active",
    default=False,
)


@dataclass(frozen=True)
class PortfolioClearResult:
    holdings: int
    journal: int
    receipts: int
    net_dividends: int
    deposits: int

    @property
    def total_rows(self) -> int:
        return self.holdings + self.journal + self.receipts + self.net_dividends + self.deposits


def _clear_session_caches() -> None:
    try:
        from services.portfolio_session import reset_portfolio_view_state

        reset_portfolio_view_state()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not reset portfolio view state: %s", exc)


def clear_user_portfolio(
    *,
    db_path: Path | None = None,
    reset_session: bool = True,
) -> PortfolioClearResult:
    """Delete all holdings, journal, receipts, net dividends, and deposits."""
    ctx = create_portfolio_context(db_path=db_path)
    receipts = ctx.receipts.delete_all()
    journal = ctx.journal.delete_all()
    net_dividends = ctx.dividends.delete_all()
    deposits = ctx.deposits.delete_all()
    holdings = ctx.portfolio.delete_all()
    if reset_session:
        _clear_session_caches()
    result = PortfolioClearResult(
        holdings=holdings,
        journal=journal,
        receipts=receipts,
        net_dividends=net_dividends,
        deposits=deposits,
    )
    logger.info(
        "Cleared portfolio: holdings=%d journal=%d receipts=%d net=%d deposits=%d",
        result.holdings,
        result.journal,
        result.receipts,
        result.net_dividends,
        result.deposits,
    )
    return result


@dataclass(frozen=True)
class _TableSnapshot:
    table: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True)
class PortfolioSnapshot:
    """In-memory copy of one user's portfolio tables."""

    tables: tuple[_TableSnapshot, ...]


def _identifier(name: str) -> str:
    if not _IDENTIFIER.fullmatch(name):
        raise ValueError(f"Unexpected SQL identifier: {name}")
    return name


def _table_columns(connection: Any, table: str) -> list[str]:
    table_name = _identifier(table)
    if connection.is_postgres:
        fetched = connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ?
            ORDER BY ordinal_position
            """,
            (table_name,),
        ).fetchall()
        return [str(row["column_name"]) for row in fetched]
    fetched = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [str(row[1]) for row in fetched]


def _cell(row: Any, column: str) -> Any:
    if isinstance(row, dict):
        return row[column]
    return row[column]


def snapshot_user_portfolio(*, db_path: Path | None = None) -> PortfolioSnapshot:
    """Copy portfolio tables for the current user before a destructive replace."""
    create_portfolio_context(db_path=db_path)
    tables: list[_TableSnapshot] = []
    with open_portfolio_db(db_path) as connection:
        for table in _PORTFOLIO_TABLES:
            columns = _table_columns(connection, table)
            if not columns:
                continue
            column_sql = ", ".join(_identifier(column) for column in columns)
            table_name = _identifier(table)
            if connection.is_postgres:
                fetched = connection.execute(
                    f"SELECT {column_sql} FROM {table_name} WHERE user_id = ?",  # noqa: S608
                    (connection.user_id,),
                ).fetchall()
            else:
                fetched = connection.execute(
                    f"SELECT {column_sql} FROM {table_name}"  # noqa: S608
                ).fetchall()
            rows = tuple(tuple(_cell(row, column) for column in columns) for row in fetched)
            tables.append(_TableSnapshot(table, tuple(columns), rows))
    return PortfolioSnapshot(tuple(tables))


def restore_user_portfolio(
    snapshot: PortfolioSnapshot,
    *,
    db_path: Path | None = None,
) -> None:
    """Replace current portfolio rows with a snapshot taken before a failed replace."""
    with open_portfolio_db(db_path) as connection:
        for table in snapshot.tables:
            table_name = _identifier(table.table)
            if connection.is_postgres:
                connection.execute(
                    f"DELETE FROM {table_name} WHERE user_id = ?",  # noqa: S608
                    (connection.user_id,),
                )
            else:
                connection.execute(f"DELETE FROM {table_name}")  # noqa: S608
            if not table.rows or not table.columns:
                continue
            column_sql = ", ".join(_identifier(column) for column in table.columns)
            placeholders = ", ".join("?" for _ in table.columns)
            connection.executemany(
                f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders})",  # noqa: S608
                table.rows,
            )
    logger.info("Restored portfolio snapshot after a failed full replace")


def _recovery_path(db_path: Path | None) -> Path:
    path = Path(db_path) if db_path is not None else Path("data") / "portfolio.db"
    user_suffix = ""
    from db.connection import use_cloud_sql

    if use_cloud_sql():
        with open_portfolio_db(db_path) as connection:
            if connection.user_id:
                user_suffix = f".{connection.user_id}"
    return path.with_name(path.name + user_suffix + ".replace-recovery.json")


def _encode_cell(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"__t": "datetime", "v": value.isoformat()}
    if isinstance(value, date):
        return {"__t": "date", "v": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__t": "decimal", "v": str(value)}
    return value


def _decode_cell(value: Any) -> Any:
    if not isinstance(value, dict) or "__t" not in value:
        return value
    kind = value.get("__t")
    raw = value.get("v")
    if kind == "datetime" and isinstance(raw, str):
        return datetime.fromisoformat(raw)
    if kind == "date" and isinstance(raw, str):
        return date.fromisoformat(raw)
    if kind == "decimal" and isinstance(raw, str):
        return Decimal(raw)
    return value


def _write_recovery(snapshot: PortfolioSnapshot, db_path: Path | None) -> None:
    payload = {
        "tables": [
            {
                "table": table.table,
                "columns": list(table.columns),
                "rows": [[_encode_cell(cell) for cell in row] for row in table.rows],
            }
            for table in snapshot.tables
        ]
    }
    path = _recovery_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(path)


def _read_recovery(db_path: Path | None) -> PortfolioSnapshot | None:
    path = _recovery_path(db_path)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        tables = []
        for item in payload["tables"]:
            columns = tuple(str(column) for column in item["columns"])
            rows = tuple(tuple(_decode_cell(cell) for cell in row) for row in item["rows"])
            tables.append(_TableSnapshot(str(item["table"]), columns, rows))
        return PortfolioSnapshot(tuple(tables))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.exception("Could not read replace recovery file %s", path)
        return None


def _discard_recovery(db_path: Path | None) -> None:
    _recovery_path(db_path).unlink(missing_ok=True)


def recover_interrupted_replace(*, db_path: Path | None = None) -> bool:
    """Restore a snapshot left behind when a full replace process was killed."""
    if _replace_active.get():
        return False
    snapshot = _read_recovery(db_path)
    if snapshot is None:
        return False
    restore_user_portfolio(snapshot, db_path=db_path)
    _discard_recovery(db_path)
    return True


@contextmanager
def restoring_portfolio_on_failure(*, db_path: Path | None = None) -> Iterator[None]:
    """Snapshot portfolio rows and restore them if the wrapped replace raises.

    The snapshot is also written to disk before the clear. The next portfolio
    open restores it if this process dies after the clear has committed.
    """
    recover_interrupted_replace(db_path=db_path)
    token = _replace_active.set(True)
    try:
        snapshot = snapshot_user_portfolio(db_path=db_path)
        _write_recovery(snapshot, db_path)
        try:
            yield
        except Exception:
            logger.exception("Full replace failed; restoring the previous portfolio")
            restore_user_portfolio(snapshot, db_path=db_path)
            _discard_recovery(db_path)
            raise
        else:
            _discard_recovery(db_path)
            _clear_session_caches()
    finally:
        _replace_active.reset(token)
