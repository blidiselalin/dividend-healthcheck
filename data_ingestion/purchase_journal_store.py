"""
SQLite storage for stock purchase journal entries.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

from config import DATA_DIR
from db.connection import open_portfolio_db, use_cloud_sql
from db.parsing import parse_date


def _default_db_path() -> Path:
    try:
        from auth.user_context import resolve_portfolio_db_path

        return resolve_portfolio_db_path()
    except Exception:
        return DATA_DIR / "portfolio.db"


def _default_seed() -> bool:
    return False


PURCHASE_JOURNAL_DB_PATH = DATA_DIR / "portfolio.db"


def portfolio_symbols(db_path: Optional[Path] = None) -> Set[str]:
    """Tickers currently in the portfolio holdings table."""
    from data_ingestion.portfolio_store import PortfolioStore

    store = PortfolioStore(db_path=db_path, seed=False) if db_path else PortfolioStore(seed=False)
    return {holding.symbol for holding in store.list_holdings()}


@dataclass(frozen=True)
class PurchaseRecord:
    symbol: str
    purchase_date: date
    price_usd: float
    id: Optional[int] = None

    @property
    def label(self) -> str:
        return self.purchase_date.strftime("%d %b %Y")


class PurchaseJournalStore:
    def __init__(
        self,
        db_path: Optional[Path] = None,
        *,
        seed: Optional[bool] = None,
    ) -> None:
        self.db_path = Path(db_path or _default_db_path())
        if not use_cloud_sql():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        do_seed = _default_seed() if seed is None else seed
        if do_seed:
            self._seed_if_empty()
            self.sync_seed()

    def _connect(self):
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
                  UNIQUE(symbol, purchase_date, price_usd)
                )
                """
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

    def list_purchases(self, *, portfolio_only: bool = True) -> List[PurchaseRecord]:
        allowed = portfolio_symbols(self.db_path) if portfolio_only else None
        with self._connect() as connection:
            if connection.is_postgres:
                rows = connection.execute(
                    """
                    SELECT id, symbol, purchase_date, price_usd
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
                    SELECT id, symbol, purchase_date, price_usd
                    FROM purchase_journal
                    WHERE purchase_date IS NOT NULL
                      AND TRIM(purchase_date) <> ''
                    ORDER BY purchase_date, symbol, price_usd
                    """
                ).fetchall()

        records: List[PurchaseRecord] = []
        for row in rows:
            symbol = row["symbol"]
            if allowed is not None and symbol not in allowed:
                continue
            try:
                purchase_date = parse_date(row["purchase_date"])
                price_usd = float(row["price_usd"])
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "Skipping purchase_journal id=%s symbol=%s: %s (purchase_date=%r, price_usd=%r)",
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
                )
            )
        return records

    def add_purchase(
        self,
        symbol: str,
        purchase_date: date,
        price_usd: float,
    ) -> PurchaseRecord:
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValueError("Symbol is required")
        if price_usd <= 0:
            raise ValueError("Price must be positive")

        with self._connect() as connection:
            if connection.is_postgres:
                row = connection.execute(
                    """
                    INSERT INTO purchase_journal (user_id, symbol, purchase_date, price_usd)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (user_id, symbol, purchase_date, price_usd) DO NOTHING
                    RETURNING id, symbol, purchase_date, price_usd
                    """,
                    (connection.user_id, symbol, purchase_date.isoformat(), price_usd),
                ).fetchone()
                if row is None:
                    row = connection.execute(
                        """
                        SELECT id, symbol, purchase_date, price_usd
                        FROM purchase_journal
                        WHERE user_id = ? AND symbol = ? AND purchase_date = ? AND price_usd = ?
                        """,
                        (
                            connection.user_id,
                            symbol,
                            purchase_date.isoformat(),
                            price_usd,
                        ),
                    ).fetchone()
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO purchase_journal (symbol, purchase_date, price_usd)
                    VALUES (?, ?, ?)
                    ON CONFLICT(symbol, purchase_date, price_usd) DO NOTHING
                    """,
                    (symbol, purchase_date.isoformat(), price_usd),
                )
                if cursor.rowcount == 0:
                    row = connection.execute(
                        """
                        SELECT id, symbol, purchase_date, price_usd
                        FROM purchase_journal
                        WHERE symbol = ? AND purchase_date = ? AND price_usd = ?
                        """,
                        (symbol, purchase_date.isoformat(), price_usd),
                    ).fetchone()
                else:
                    row = connection.execute(
                        """
                        SELECT id, symbol, purchase_date, price_usd
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
            return cursor.rowcount > 0
