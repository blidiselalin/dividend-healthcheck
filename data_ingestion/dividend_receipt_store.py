"""
Persistent storage for dividend cash received per portfolio holding.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from config import DATA_DIR
from db.connection import open_portfolio_db, use_cloud_sql
from db.parsing import parse_date


def _default_db_path() -> Path:
    try:
        from auth.user_context import resolve_portfolio_db_path

        return resolve_portfolio_db_path()
    except Exception:
        return DATA_DIR / "portfolio.db"


@dataclass(frozen=True)
class DividendReceipt:
    symbol: str
    ex_date: date
    pay_date: date
    per_share_usd: float
    shares_held: float
    gross_usd: float
    id: int | None = None


class DividendReceiptStore:
    """Record and query dividend payments received for portfolio holdings."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or _default_db_path())
        if not use_cloud_sql():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> Any:
        return open_portfolio_db(self.db_path)

    def _ensure_schema(self) -> None:
        if use_cloud_sql():
            return
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS dividend_receipts (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  symbol TEXT NOT NULL,
                  ex_date TEXT NOT NULL,
                  pay_date TEXT NOT NULL,
                  per_share_usd REAL NOT NULL,
                  shares_held REAL NOT NULL,
                  gross_usd REAL NOT NULL,
                  recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                  UNIQUE(symbol, ex_date, per_share_usd)
                )
                """
            )
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(holdings)").fetchall()
            }
            if "dividend_tracking_since" not in columns:
                connection.execute("ALTER TABLE holdings ADD COLUMN dividend_tracking_since TEXT")

    def upsert_receipt(
        self,
        symbol: str,
        *,
        ex_date: date,
        pay_date: date,
        per_share_usd: float,
        shares_held: float,
        gross_usd: float,
    ) -> bool:
        """Insert a receipt if new. Returns True when a row was added."""
        symbol = symbol.strip().upper()
        with self._connect() as connection:
            if connection.is_postgres:
                row = connection.execute(
                    """
                    INSERT INTO dividend_receipts (
                      user_id, symbol, ex_date, pay_date,
                      per_share_usd, shares_held, gross_usd
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (user_id, symbol, ex_date, per_share_usd) DO NOTHING
                    RETURNING id
                    """,
                    (
                        connection.user_id,
                        symbol,
                        ex_date.isoformat(),
                        pay_date.isoformat(),
                        per_share_usd,
                        shares_held,
                        gross_usd,
                    ),
                ).fetchone()
                return row is not None

            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO dividend_receipts (
                  symbol, ex_date, pay_date, per_share_usd, shares_held, gross_usd
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    ex_date.isoformat(),
                    pay_date.isoformat(),
                    per_share_usd,
                    shares_held,
                    gross_usd,
                ),
            )
            return int(getattr(cursor, "rowcount", 0) or 0) > 0

    def list_for_symbol(self, symbol: str) -> list[DividendReceipt]:
        symbol = symbol.strip().upper()
        with self._connect() as connection:
            if connection.is_postgres:
                rows = connection.execute(
                    """
                    SELECT id, symbol, ex_date, pay_date, per_share_usd, shares_held, gross_usd
                    FROM dividend_receipts
                    WHERE user_id = ? AND symbol = ?
                    ORDER BY pay_date, ex_date
                    """,
                    (connection.user_id, symbol),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, symbol, ex_date, pay_date, per_share_usd, shares_held, gross_usd
                    FROM dividend_receipts
                    WHERE symbol = ?
                    ORDER BY pay_date, ex_date
                    """,
                    (symbol,),
                ).fetchall()

        return [
            DividendReceipt(
                id=int(row["id"]),
                symbol=row["symbol"],
                ex_date=parse_date(row["ex_date"]),
                pay_date=parse_date(row["pay_date"]),
                per_share_usd=float(row["per_share_usd"]),
                shares_held=float(row["shares_held"]),
                gross_usd=float(row["gross_usd"]),
            )
            for row in rows
        ]

    def total_for_symbol(self, symbol: str) -> float:
        symbol = symbol.strip().upper()
        with self._connect() as connection:
            if connection.is_postgres:
                row = connection.execute(
                    """
                    SELECT COALESCE(SUM(gross_usd), 0) AS total
                    FROM dividend_receipts
                    WHERE user_id = ? AND symbol = ?
                    """,
                    (connection.user_id, symbol),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT COALESCE(SUM(gross_usd), 0) AS total
                    FROM dividend_receipts
                    WHERE symbol = ?
                    """,
                    (symbol,),
                ).fetchone()
        return round(float(row["total"]), 2) if row else 0.0

    def monthly_gross_totals(self) -> dict[tuple[int, int], float]:
        """Aggregate gross cash by (year, month) of payment date."""
        with self._connect() as connection:
            if connection.is_postgres:
                rows = connection.execute(
                    """
                    SELECT
                      EXTRACT(YEAR FROM pay_date)::INTEGER AS year,
                      EXTRACT(MONTH FROM pay_date)::INTEGER AS month,
                      SUM(gross_usd) AS gross
                    FROM dividend_receipts
                    WHERE user_id = ?
                    GROUP BY 1, 2
                    ORDER BY 1, 2
                    """,
                    (connection.user_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT
                      CAST(strftime('%Y', pay_date) AS INTEGER) AS year,
                      CAST(strftime('%m', pay_date) AS INTEGER) AS month,
                      SUM(gross_usd) AS gross
                    FROM dividend_receipts
                    GROUP BY 1, 2
                    ORDER BY 1, 2
                    """
                ).fetchall()

        totals: dict[tuple[int, int], float] = {}
        for row in rows:
            totals[(int(row["year"]), int(row["month"]))] = round(float(row["gross"]), 2)
        return totals

    def delete_for_symbol(self, symbol: str) -> int:
        symbol = symbol.strip().upper()
        with self._connect() as connection:
            if connection.is_postgres:
                cursor = connection.execute(
                    "DELETE FROM dividend_receipts WHERE user_id = ? AND symbol = ?",
                    (connection.user_id, symbol),
                )
            else:
                cursor = connection.execute(
                    "DELETE FROM dividend_receipts WHERE symbol = ?",
                    (symbol,),
                )
            return int(cursor.rowcount or 0)
