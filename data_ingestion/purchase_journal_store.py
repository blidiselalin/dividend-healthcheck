"""
SQLite storage for stock purchase journal entries.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional, Set

from config import DATA_DIR
from data_ingestion.portfolio_store import PORTFOLIO_SHARES
from data_ingestion.purchase_journal_seed import PURCHASE_JOURNAL_SEED

PURCHASE_JOURNAL_DB_PATH = DATA_DIR / "portfolio.db"

PORTFOLIO_SYMBOLS: Set[str] = {symbol for symbol, _name, _shares in PORTFOLIO_SHARES}


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
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or PURCHASE_JOURNAL_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        self._seed_if_empty()
        self.sync_seed()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
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
        rows = [
            (symbol, purchase_date, price_usd)
            for symbol, purchase_date, price_usd in PURCHASE_JOURNAL_SEED
            if symbol in PORTFOLIO_SYMBOLS
        ]
        connection.executemany(
            """
            INSERT OR IGNORE INTO purchase_journal (symbol, purchase_date, price_usd)
            VALUES (?, ?, ?)
            """,
            rows,
        )

    def sync_seed(self) -> None:
        with self._connect() as connection:
            for symbol, purchase_date, price_usd in PURCHASE_JOURNAL_SEED:
                if symbol not in PORTFOLIO_SYMBOLS:
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
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, symbol, purchase_date, price_usd
                FROM purchase_journal
                ORDER BY purchase_date, symbol, price_usd
                """
            ).fetchall()

        records: List[PurchaseRecord] = []
        for row in rows:
            symbol = row["symbol"]
            if portfolio_only and symbol not in PORTFOLIO_SYMBOLS:
                continue
            records.append(
                PurchaseRecord(
                    id=int(row["id"]),
                    symbol=symbol,
                    purchase_date=date.fromisoformat(row["purchase_date"]),
                    price_usd=float(row["price_usd"]),
                )
            )
        return records
