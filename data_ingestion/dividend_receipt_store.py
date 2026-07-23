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
    source: str = "computed"


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
                  source TEXT NOT NULL DEFAULT 'computed',
                  UNIQUE(symbol, ex_date, per_share_usd, gross_usd)
                )
                """
            )
            receipt_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(dividend_receipts)").fetchall()
            }
            if "source" not in receipt_columns:
                connection.execute(
                    "ALTER TABLE dividend_receipts "
                    "ADD COLUMN source TEXT NOT NULL DEFAULT 'computed'"
                )
            table_row = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='holdings'"
            ).fetchone()
            if table_row:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(holdings)").fetchall()
                }
                if "dividend_tracking_since" not in columns:
                    connection.execute(
                        "ALTER TABLE holdings ADD COLUMN dividend_tracking_since TEXT"
                    )

    def upsert_receipt(
        self,
        symbol: str,
        *,
        ex_date: date,
        pay_date: date,
        per_share_usd: float,
        shares_held: float,
        gross_usd: float,
        source: str = "computed",
    ) -> bool:
        """Insert a receipt if new. Returns True when a row was added."""
        return (
            self.sync_receipt(
                symbol,
                ex_date=ex_date,
                pay_date=pay_date,
                per_share_usd=per_share_usd,
                shares_held=shares_held,
                gross_usd=gross_usd,
                source=source,
            )
            == "added"
        )

    def sync_receipt(
        self,
        symbol: str,
        *,
        ex_date: date,
        pay_date: date,
        per_share_usd: float,
        shares_held: float,
        gross_usd: float,
        source: str = "computed",
    ) -> str:
        """
        Insert or update a receipt keyed by (symbol, ex_date, per_share, gross).

        Returns ``added``, ``updated``, or ``unchanged``.
        """
        symbol = symbol.strip().upper()
        existing = self._find_receipt(symbol, ex_date, per_share_usd, gross_usd)
        if existing is None and source != "ibkr":
            fallback = self._find_receipt(symbol, ex_date, per_share_usd, gross_usd=None)
            if fallback is not None and fallback.source == "ibkr":
                return "unchanged"
            existing = fallback
        if existing is None:
            inserted = self._insert_receipt(
                symbol,
                ex_date=ex_date,
                pay_date=pay_date,
                per_share_usd=per_share_usd,
                shares_held=shares_held,
                gross_usd=gross_usd,
                source=source,
            )
            return "added" if inserted else "unchanged"

        if existing.source == "ibkr" and source != "ibkr":
            return "unchanged"

        if (
            existing.pay_date == pay_date
            and existing.ex_date == ex_date
            and existing.shares_held == shares_held
            and existing.gross_usd == gross_usd
            and existing.source == source
        ):
            return "unchanged"

        if existing.id is not None and self.update_receipt(
            existing.id,
            ex_date=ex_date,
            pay_date=pay_date,
            per_share_usd=per_share_usd,
            shares_held=shares_held,
            gross_usd=gross_usd,
            source=source,
        ):
            return "updated"
        return "unchanged"

    def update_receipt(
        self,
        receipt_id: int | None,
        *,
        ex_date: date,
        pay_date: date,
        per_share_usd: float,
        shares_held: float,
        gross_usd: float,
        source: str = "computed",
    ) -> bool:
        """Update an existing receipt row. Returns True when a row was modified."""
        if receipt_id is None:
            return False
        with self._connect() as connection:
            if connection.is_postgres:
                cursor = connection.execute(
                    """
                    UPDATE dividend_receipts
                    SET ex_date = ?, pay_date = ?, per_share_usd = ?,
                        shares_held = ?, gross_usd = ?, source = ?
                    WHERE user_id = ? AND id = ?
                    """,
                    (
                        ex_date.isoformat(),
                        pay_date.isoformat(),
                        per_share_usd,
                        shares_held,
                        gross_usd,
                        source,
                        connection.user_id,
                        receipt_id,
                    ),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE dividend_receipts
                    SET ex_date = ?, pay_date = ?, per_share_usd = ?,
                        shares_held = ?, gross_usd = ?, source = ?
                    WHERE id = ?
                    """,
                    (
                        ex_date.isoformat(),
                        pay_date.isoformat(),
                        per_share_usd,
                        shares_held,
                        gross_usd,
                        source,
                        receipt_id,
                    ),
                )
            return int(getattr(cursor, "rowcount", 0) or 0) > 0

    def _find_receipt(
        self,
        symbol: str,
        ex_date: date,
        per_share_usd: float,
        gross_usd: float | None = None,
    ) -> DividendReceipt | None:
        symbol = symbol.strip().upper()
        per = round(float(per_share_usd), 6)
        gross = round(float(gross_usd), 2) if gross_usd is not None else None
        with self._connect() as connection:
            if connection.is_postgres:
                if gross is not None:
                    row = connection.execute(
                        """
                        SELECT id, symbol, ex_date, pay_date, per_share_usd,
                               shares_held, gross_usd, source
                        FROM dividend_receipts
                        WHERE user_id = ? AND symbol = ? AND ex_date = ?
                          AND ABS(per_share_usd - ?) < 0.000001
                          AND ABS(gross_usd - ?) < 0.000001
                        LIMIT 1
                        """,
                        (connection.user_id, symbol, ex_date.isoformat(), per, gross),
                    ).fetchone()
                else:
                    row = connection.execute(
                        """
                        SELECT id, symbol, ex_date, pay_date, per_share_usd,
                               shares_held, gross_usd, source
                        FROM dividend_receipts
                        WHERE user_id = ? AND symbol = ? AND ex_date = ?
                          AND ABS(per_share_usd - ?) < 0.000001
                        LIMIT 1
                        """,
                        (connection.user_id, symbol, ex_date.isoformat(), per),
                    ).fetchone()
            elif gross is not None:
                row = connection.execute(
                    """
                    SELECT id, symbol, ex_date, pay_date, per_share_usd,
                           shares_held, gross_usd, source
                    FROM dividend_receipts
                    WHERE symbol = ? AND ex_date = ?
                      AND ABS(per_share_usd - ?) < 0.000001
                      AND ABS(gross_usd - ?) < 0.000001
                    LIMIT 1
                    """,
                    (symbol, ex_date.isoformat(), per, gross),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT id, symbol, ex_date, pay_date, per_share_usd,
                           shares_held, gross_usd, source
                    FROM dividend_receipts
                    WHERE symbol = ? AND ex_date = ?
                      AND ABS(per_share_usd - ?) < 0.000001
                    LIMIT 1
                    """,
                    (symbol, ex_date.isoformat(), per),
                ).fetchone()
        if not row:
            return None
        return DividendReceipt(
            id=int(row["id"]),
            symbol=row["symbol"],
            ex_date=parse_date(row["ex_date"]),
            pay_date=parse_date(row["pay_date"]),
            per_share_usd=float(row["per_share_usd"]),
            shares_held=float(row["shares_held"]),
            gross_usd=float(row["gross_usd"]),
            source=str(row["source"] or "computed"),
        )

    def _insert_receipt(
        self,
        symbol: str,
        *,
        ex_date: date,
        pay_date: date,
        per_share_usd: float,
        shares_held: float,
        gross_usd: float,
        source: str = "computed",
    ) -> bool:
        symbol = symbol.strip().upper()
        with self._connect() as connection:
            if connection.is_postgres:
                row = connection.execute(
                    """
                    INSERT INTO dividend_receipts (
                      user_id, symbol, ex_date, pay_date,
                      per_share_usd, shares_held, gross_usd, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (user_id, symbol, ex_date, per_share_usd, gross_usd) DO NOTHING
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
                        source,
                    ),
                ).fetchone()
                return row is not None

            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO dividend_receipts (
                  symbol, ex_date, pay_date, per_share_usd, shares_held, gross_usd, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    ex_date.isoformat(),
                    pay_date.isoformat(),
                    per_share_usd,
                    shares_held,
                    gross_usd,
                    source,
                ),
            )
            return int(getattr(cursor, "rowcount", 0) or 0) > 0

    def list_for_symbol(self, symbol: str) -> list[DividendReceipt]:
        symbol = symbol.strip().upper()
        with self._connect() as connection:
            if connection.is_postgres:
                rows = connection.execute(
                    """
                    SELECT id, symbol, ex_date, pay_date, per_share_usd,
                           shares_held, gross_usd, source
                    FROM dividend_receipts
                    WHERE user_id = ? AND symbol = ?
                    ORDER BY pay_date, ex_date
                    """,
                    (connection.user_id, symbol),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, symbol, ex_date, pay_date, per_share_usd,
                           shares_held, gross_usd, source
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
                source=str(row["source"] or "computed"),
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

    def delete_for_symbol(self, symbol: str, *, source: str | None = None) -> int:
        symbol = symbol.strip().upper()
        with self._connect() as connection:
            if connection.is_postgres:
                if source is None:
                    cursor = connection.execute(
                        "DELETE FROM dividend_receipts WHERE user_id = ? AND symbol = ?",
                        (connection.user_id, symbol),
                    )
                else:
                    cursor = connection.execute(
                        """
                        DELETE FROM dividend_receipts
                        WHERE user_id = ? AND symbol = ? AND source = ?
                        """,
                        (connection.user_id, symbol, source),
                    )
            elif source is None:
                cursor = connection.execute(
                    "DELETE FROM dividend_receipts WHERE symbol = ?",
                    (symbol,),
                )
            else:
                cursor = connection.execute(
                    "DELETE FROM dividend_receipts WHERE symbol = ? AND source = ?",
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
        """Delete receipts for one symbol, source, and pay dates in range."""
        symbol = symbol.strip().upper()
        start_text = start.isoformat()
        end_text = end.isoformat()
        with self._connect() as connection:
            if connection.is_postgres:
                cursor = connection.execute(
                    """
                    DELETE FROM dividend_receipts
                    WHERE user_id = ? AND symbol = ? AND source = ?
                      AND pay_date >= ? AND pay_date <= ?
                    """,
                    (connection.user_id, symbol, source, start_text, end_text),
                )
            else:
                cursor = connection.execute(
                    """
                    DELETE FROM dividend_receipts
                    WHERE symbol = ? AND source = ?
                      AND pay_date >= ? AND pay_date <= ?
                    """,
                    (symbol, source, start_text, end_text),
                )
            return int(cursor.rowcount or 0)

    def delete_all(self) -> int:
        with self._connect() as connection:
            if connection.is_postgres:
                cursor = connection.execute(
                    "DELETE FROM dividend_receipts WHERE user_id = ?",
                    (connection.user_id,),
                )
            else:
                cursor = connection.execute("DELETE FROM dividend_receipts")
            return int(cursor.rowcount or 0)
