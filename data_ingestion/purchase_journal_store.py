"""
Purchase journal storage (PostgreSQL per user, or SQLite file in local dev).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from config import DATA_DIR
from db.connection import open_portfolio_db, use_cloud_sql
from db.parsing import parse_date

logger = logging.getLogger(__name__)


def _default_db_path() -> Path:
    try:
        from auth.user_context import resolve_portfolio_db_path

        return resolve_portfolio_db_path()
    except Exception:
        return DATA_DIR / "portfolio.db"


def _default_seed() -> bool:
    return False


def portfolio_symbols(db_path: Path | None = None) -> set[str]:
    """Tickers with an open position (positive share count) in holdings."""
    from data_ingestion.portfolio_store import PortfolioStore

    store = PortfolioStore(db_path=db_path, seed=False) if db_path else PortfolioStore(seed=False)
    return {holding.symbol for holding in store.list_holdings() if holding.shares > 0}


@dataclass(frozen=True)
class PurchaseRecord:
    symbol: str
    purchase_date: date
    price_usd: float
    id: int | None = None
    shares: float | None = None
    commission_usd: float = 0.0
    side: str = "buy"
    source: str = "manual"

    @property
    def label(self) -> str:
        return self.purchase_date.strftime("%d %b %Y")

    @property
    def lot_cost_usd(self) -> float | None:
        if self.shares is None or self.shares <= 0:
            return None
        gross = round(self.shares * self.price_usd + self.commission_usd, 2)
        return -gross if self.side == "sell" else gross


class PurchaseJournalStore:
    def __init__(
        self,
        db_path: Path | None = None,
        *,
        seed: bool | None = None,
    ) -> None:
        self.db_path = Path(db_path or _default_db_path())
        if not use_cloud_sql():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        do_seed = _default_seed() if seed is None else seed
        if do_seed:
            self._seed_if_empty()
            self.sync_seed()

    def _connect(self) -> Any:
        return open_portfolio_db(self.db_path)

    def _ensure_schema(self) -> None:
        if use_cloud_sql():
            return
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS purchase_journal (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  symbol TEXT NOT NULL,
                  purchase_date TEXT NOT NULL,
                  price_usd REAL NOT NULL,
                  shares REAL,
                  commission_usd REAL NOT NULL DEFAULT 0,
                  side TEXT NOT NULL DEFAULT 'buy',
                  source TEXT NOT NULL DEFAULT 'manual',
                  UNIQUE(symbol, purchase_date, price_usd, side)
                )
                """
            )
            column_rows = connection.execute("PRAGMA table_info(purchase_journal)").fetchall()
            columns = {row[1] for row in column_rows}
            if "shares" not in columns:
                connection.execute("ALTER TABLE purchase_journal ADD COLUMN shares REAL")
            if "commission_usd" not in columns:
                connection.execute(
                    "ALTER TABLE purchase_journal ADD COLUMN commission_usd REAL NOT NULL DEFAULT 0"
                )
            if "side" not in columns:
                connection.execute(
                    "ALTER TABLE purchase_journal ADD COLUMN side TEXT NOT NULL DEFAULT 'buy'"
                )
            if "source" not in columns:
                connection.execute(
                    "ALTER TABLE purchase_journal ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'"
                )

    def _seed_if_empty(self) -> None:
        with self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM purchase_journal").fetchone()[0]
            if count:
                return
            self._insert_seed(connection)

    def _insert_seed(self, connection: sqlite3.Connection) -> None:
        from data_ingestion.purchase_journal_seed import PURCHASE_JOURNAL_SEED

        symbols = portfolio_symbols(self.db_path)
        rows = [
            (symbol, purchase_date, price_usd)
            for symbol, purchase_date, price_usd in PURCHASE_JOURNAL_SEED
            if symbol in symbols
        ]
        connection.executemany(
            """
            INSERT OR IGNORE INTO purchase_journal (symbol, purchase_date, price_usd)
            VALUES (?, ?, ?)
            """,
            rows,
        )

    def sync_seed(self) -> None:
        from data_ingestion.purchase_journal_seed import PURCHASE_JOURNAL_SEED

        symbols = portfolio_symbols(self.db_path)
        with self._connect() as connection:
            for symbol, purchase_date, price_usd in PURCHASE_JOURNAL_SEED:
                if symbol not in symbols:
                    continue
                connection.execute(
                    """
                    INSERT INTO purchase_journal (symbol, purchase_date, price_usd)
                    VALUES (?, ?, ?)
                    ON CONFLICT(symbol, purchase_date, price_usd) DO NOTHING
                    """,
                    (symbol, purchase_date, price_usd),
                )

    def list_purchases(self, *, portfolio_only: bool = True) -> list[PurchaseRecord]:
        allowed = portfolio_symbols(self.db_path) if portfolio_only else None
        with self._connect() as connection:
            if connection.is_postgres:
                rows = connection.execute(
                    """
                    SELECT id, symbol, purchase_date, price_usd, shares, commission_usd,
                           side, source
                    FROM purchase_journal
                    WHERE user_id = ?
                      AND purchase_date IS NOT NULL
                      AND TRIM(CAST(purchase_date AS TEXT)) <> ''
                    ORDER BY purchase_date, symbol, price_usd
                    """,
                    (connection.user_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, symbol, purchase_date, price_usd, shares, commission_usd,
                           side, source
                    FROM purchase_journal
                    WHERE purchase_date IS NOT NULL
                      AND TRIM(purchase_date) <> ''
                    ORDER BY purchase_date, symbol, price_usd
                    """
                ).fetchall()

        records: list[PurchaseRecord] = []
        for row in rows:
            symbol = row["symbol"]
            if allowed is not None and symbol not in allowed:
                continue
            try:
                purchase_date = parse_date(row["purchase_date"])
                price_usd = float(row["price_usd"])
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "Skipping purchase_journal id=%s symbol=%s: %s "
                    "(purchase_date=%r, price_usd=%r)",
                    row.get("id"),
                    symbol,
                    exc,
                    row.get("purchase_date"),
                    row.get("price_usd"),
                )
                continue
            records.append(
                PurchaseRecord(
                    id=int(row["id"]),
                    symbol=symbol,
                    purchase_date=purchase_date,
                    price_usd=price_usd,
                    shares=float(row["shares"]) if row["shares"] is not None else None,
                    commission_usd=float(row["commission_usd"] or 0.0),
                    side=str(row["side"] or "buy"),
                    source=str(row["source"] or "manual"),
                )
            )
        return records

    def _find_purchase(
        self,
        symbol: str,
        purchase_date: date,
        price_usd: float,
        side: str,
    ) -> PurchaseRecord | None:
        symbol = symbol.strip().upper()
        side_value = side.strip().lower() or "buy"
        with self._connect() as connection:
            if connection.is_postgres:
                row = connection.execute(
                    """
                    SELECT id, symbol, purchase_date, price_usd, shares, commission_usd,
                           side, source
                    FROM purchase_journal
                    WHERE user_id = ? AND symbol = ? AND purchase_date = ?
                      AND price_usd = ? AND side = ?
                    LIMIT 1
                    """,
                    (
                        connection.user_id,
                        symbol,
                        purchase_date.isoformat(),
                        price_usd,
                        side_value,
                    ),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT id, symbol, purchase_date, price_usd, shares, commission_usd,
                           side, source
                    FROM purchase_journal
                    WHERE symbol = ? AND purchase_date = ? AND price_usd = ? AND side = ?
                    LIMIT 1
                    """,
                    (symbol, purchase_date.isoformat(), price_usd, side_value),
                ).fetchone()
        if row is None:
            return None
        return PurchaseRecord(
            id=int(row["id"]),
            symbol=row["symbol"],
            purchase_date=parse_date(row["purchase_date"]),
            price_usd=float(row["price_usd"]),
            shares=float(row["shares"]) if row["shares"] is not None else None,
            commission_usd=float(row["commission_usd"] or 0.0),
            side=str(row["side"] or "buy"),
            source=str(row["source"] or "manual"),
        )

    def update_purchase(
        self,
        purchase_id: int,
        *,
        shares: float | None,
        commission_usd: float,
        source: str,
    ) -> bool:
        with self._connect() as connection:
            if connection.is_postgres:
                cursor = connection.execute(
                    """
                    UPDATE purchase_journal
                    SET shares = ?, commission_usd = ?, source = ?
                    WHERE user_id = ? AND id = ?
                    """,
                    (
                        shares,
                        commission_usd,
                        source.strip().lower() or "manual",
                        connection.user_id,
                        purchase_id,
                    ),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE purchase_journal
                    SET shares = ?, commission_usd = ?, source = ?
                    WHERE id = ?
                    """,
                    (
                        shares,
                        commission_usd,
                        source.strip().lower() or "manual",
                        purchase_id,
                    ),
                )
            return int(getattr(cursor, "rowcount", 0) or 0) > 0

    def sync_purchase(
        self,
        symbol: str,
        purchase_date: date,
        price_usd: float,
        *,
        shares: float | None = None,
        commission_usd: float = 0.0,
        side: str = "buy",
        source: str = "ibkr",
    ) -> str:
        """
        Insert or refresh a journal lot keyed by (symbol, date, price, side).

        Returns ``added``, ``updated``, or ``unchanged``. Manual rows are never
        overwritten by broker imports.
        """
        symbol = symbol.strip().upper()
        side_value = side.strip().lower() or "buy"
        source_value = source.strip().lower() or "manual"
        existing = self._find_purchase(symbol, purchase_date, price_usd, side_value)
        if existing is None:
            self.add_purchase(
                symbol,
                purchase_date,
                price_usd,
                shares=shares,
                commission_usd=commission_usd,
                side=side_value,
                source=source_value,
            )
            return "added"

        if existing.source not in ("ibkr", "ibkr-open") and source_value == "ibkr":
            return "unchanged"

        shares_match = existing.shares is None and shares is None
        if not shares_match and existing.shares is not None and shares is not None:
            shares_match = abs(float(existing.shares) - float(shares)) < 0.0001
        if (
            shares_match
            and abs(existing.commission_usd - commission_usd) < 0.0001
            and existing.source == source_value
        ):
            return "unchanged"

        if source_value != "ibkr" or existing.source not in ("ibkr", "ibkr-open"):
            return "unchanged"

        if existing.id is not None and self.update_purchase(
            existing.id,
            shares=shares,
            commission_usd=commission_usd,
            source=source_value,
        ):
            return "updated"
        return "unchanged"

    def add_purchase(
        self,
        symbol: str,
        purchase_date: date,
        price_usd: float,
        *,
        shares: float | None = None,
        commission_usd: float = 0.0,
        side: str = "buy",
        source: str = "manual",
    ) -> PurchaseRecord:
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValueError("Symbol is required")
        if price_usd <= 0:
            raise ValueError("Price must be positive")
        if shares is not None and shares <= 0:
            raise ValueError("Shares must be positive")
        if commission_usd < 0:
            raise ValueError("Commission cannot be negative")

        share_value = shares
        commission_value = commission_usd
        side_value = side.strip().lower() or "buy"
        source_value = source.strip().lower() or "manual"

        with self._connect() as connection:
            if connection.is_postgres:
                row = connection.execute(
                    """
                    INSERT INTO purchase_journal (
                      user_id, symbol, purchase_date, price_usd, shares,
                      commission_usd, side, source
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (user_id, symbol, purchase_date, price_usd, side) DO NOTHING
                    RETURNING id, symbol, purchase_date, price_usd, shares, commission_usd,
                              side, source
                    """,
                    (
                        connection.user_id,
                        symbol,
                        purchase_date.isoformat(),
                        price_usd,
                        share_value,
                        commission_value,
                        side_value,
                        source_value,
                    ),
                ).fetchone()
                if row is None:
                    row = connection.execute(
                        """
                        SELECT id, symbol, purchase_date, price_usd, shares, commission_usd,
                               side, source
                        FROM purchase_journal
                        WHERE user_id = ? AND symbol = ? AND purchase_date = ?
                          AND price_usd = ? AND side = ?
                        """,
                        (
                            connection.user_id,
                            symbol,
                            purchase_date.isoformat(),
                            price_usd,
                            side_value,
                        ),
                    ).fetchone()
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO purchase_journal (
                      symbol, purchase_date, price_usd, shares, commission_usd, side, source
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, purchase_date, price_usd, side) DO NOTHING
                    """,
                    (
                        symbol,
                        purchase_date.isoformat(),
                        price_usd,
                        share_value,
                        commission_value,
                        side_value,
                        source_value,
                    ),
                )
                if cursor.rowcount == 0:
                    row = connection.execute(
                        """
                        SELECT id, symbol, purchase_date, price_usd, shares, commission_usd,
                               side, source
                        FROM purchase_journal
                        WHERE symbol = ? AND purchase_date = ? AND price_usd = ? AND side = ?
                        """,
                        (symbol, purchase_date.isoformat(), price_usd, side_value),
                    ).fetchone()
                else:
                    row = connection.execute(
                        """
                        SELECT id, symbol, purchase_date, price_usd, shares, commission_usd,
                               side, source
                        FROM purchase_journal WHERE id = ?
                        """,
                        (cursor.lastrowid,),
                    ).fetchone()

        if row is None:
            raise RuntimeError("Failed to save purchase")

        return PurchaseRecord(
            id=int(row["id"]),
            symbol=row["symbol"],
            purchase_date=parse_date(row["purchase_date"]),
            price_usd=float(row["price_usd"]),
            shares=float(row["shares"]) if row["shares"] is not None else None,
            commission_usd=float(row["commission_usd"] or 0.0),
            side=str(row["side"] or "buy"),
            source=str(row["source"] or "manual"),
        )

    def delete_purchase(self, purchase_id: int) -> bool:
        with self._connect() as connection:
            if connection.is_postgres:
                cursor = connection.execute(
                    "DELETE FROM purchase_journal WHERE user_id = ? AND id = ?",
                    (connection.user_id, purchase_id),
                )
            else:
                cursor = connection.execute(
                    "DELETE FROM purchase_journal WHERE id = ?",
                    (purchase_id,),
                )
            return bool(cursor.rowcount > 0)

    def delete_for_symbol(self, symbol: str, *, source: str | None = None) -> int:
        symbol = symbol.strip().upper()
        with self._connect() as connection:
            if connection.is_postgres:
                if source is None:
                    cursor = connection.execute(
                        "DELETE FROM purchase_journal WHERE user_id = ? AND symbol = ?",
                        (connection.user_id, symbol),
                    )
                else:
                    cursor = connection.execute(
                        """
                        DELETE FROM purchase_journal
                        WHERE user_id = ? AND symbol = ? AND source = ?
                        """,
                        (connection.user_id, symbol, source),
                    )
            elif source is None:
                cursor = connection.execute(
                    "DELETE FROM purchase_journal WHERE symbol = ?",
                    (symbol,),
                )
            else:
                cursor = connection.execute(
                    "DELETE FROM purchase_journal WHERE symbol = ? AND source = ?",
                    (symbol, source),
                )
            return int(cursor.rowcount or 0)

    def delete_for_symbol_in_date_range(
        self,
        symbol: str,
        *,
        source: str,
        start: date,
        end: date,
    ) -> int:
        """Delete journal rows for one symbol, source, and inclusive date range."""
        symbol = symbol.strip().upper()
        start_text = start.isoformat()
        end_text = end.isoformat()
        with self._connect() as connection:
            if connection.is_postgres:
                cursor = connection.execute(
                    """
                    DELETE FROM purchase_journal
                    WHERE user_id = ? AND symbol = ? AND source = ?
                      AND purchase_date >= ? AND purchase_date <= ?
                    """,
                    (connection.user_id, symbol, source, start_text, end_text),
                )
            else:
                cursor = connection.execute(
                    """
                    DELETE FROM purchase_journal
                    WHERE symbol = ? AND source = ?
                      AND purchase_date >= ? AND purchase_date <= ?
                    """,
                    (symbol, source, start_text, end_text),
                )
            return int(cursor.rowcount or 0)

    def delete_all(self) -> int:
        with self._connect() as connection:
            if connection.is_postgres:
                cursor = connection.execute(
                    "DELETE FROM purchase_journal WHERE user_id = ?",
                    (connection.user_id,),
                )
            else:
                cursor = connection.execute("DELETE FROM purchase_journal")
            return int(cursor.rowcount or 0)
