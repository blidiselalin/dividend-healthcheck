"""
Persistent storage for dividend cash received per portfolio holding.
"""

from __future__ import annotations

import calendar
import contextlib
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from config import DATA_DIR
from data_ingestion.dividend_transaction import (
    DIVIDEND_TYPE_ACTUAL,
    DIVIDEND_TYPE_COMPUTED,
    TRANSACTION_STATUS_POSTED,
    DividendDedupInput,
    build_dedup_key,
    net_from_gross_and_withholding,
)
from db.connection import is_unique_violation, open_portfolio_db, use_cloud_sql
from db.parsing import parse_date

_POSTED_CASH_WHERE = """
  AND COALESCE(is_excluded, 0) = 0
  AND COALESCE(transaction_status, 'posted') = 'posted'
  AND COALESCE(dividend_type, 'actual') IN ('actual', 'payment_in_lieu')
"""

_COMPUTED_ONLY_WHERE = """
  AND COALESCE(is_excluded, 0) = 0
  AND COALESCE(dividend_type, 'actual') = 'computed'
"""


def _receipt_totals_filter(*, posted_cash_only: bool, computed_only: bool) -> str:
    if computed_only:
        return _COMPUTED_ONLY_WHERE
    if posted_cash_only:
        return _POSTED_CASH_WHERE
    return " AND COALESCE(is_excluded, 0) = 0"


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
    broker_account: str | None = None
    broker_transaction_id: str | None = None
    dedup_key: str | None = None
    transaction_status: str = TRANSACTION_STATUS_POSTED
    dividend_type: str = DIVIDEND_TYPE_ACTUAL
    withholding_usd: float = 0.0
    net_usd: float | None = None
    currency: str = "USD"
    is_excluded: bool = False
    exclusion_reason: str | None = None
    description: str | None = None
    source_row_number: int | None = None


@dataclass(frozen=True)
class DividendImportStats:
    rows_processed: int = 0
    inserted: int = 0
    updated: int = 0
    duplicates_ignored: int = 0
    rejected: int = 0
    net_imported_usd: float = 0.0


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
            for ddl in (
                "ALTER TABLE dividend_receipts ADD COLUMN broker_account TEXT",
                "ALTER TABLE dividend_receipts ADD COLUMN broker_transaction_id TEXT",
                "ALTER TABLE dividend_receipts ADD COLUMN source_file_hash TEXT",
                "ALTER TABLE dividend_receipts ADD COLUMN source_row_number INTEGER",
                "ALTER TABLE dividend_receipts ADD COLUMN dedup_key TEXT",
                (
                    "ALTER TABLE dividend_receipts ADD COLUMN transaction_status "
                    "TEXT NOT NULL DEFAULT 'posted'"
                ),
                (
                    "ALTER TABLE dividend_receipts ADD COLUMN dividend_type "
                    "TEXT NOT NULL DEFAULT 'actual'"
                ),
                "ALTER TABLE dividend_receipts ADD COLUMN withholding_usd REAL NOT NULL DEFAULT 0",
                "ALTER TABLE dividend_receipts ADD COLUMN net_usd REAL",
                "ALTER TABLE dividend_receipts ADD COLUMN currency TEXT NOT NULL DEFAULT 'USD'",
                "ALTER TABLE dividend_receipts ADD COLUMN is_excluded INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE dividend_receipts ADD COLUMN exclusion_reason TEXT",
                "ALTER TABLE dividend_receipts ADD COLUMN description TEXT",
            ):
                with contextlib.suppress(sqlite3.OperationalError):
                    connection.execute(ddl)
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_dividend_receipts_dedup_unique
                ON dividend_receipts (dedup_key)
                WHERE dedup_key IS NOT NULL
                """
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

    _RECEIPT_SELECT = """
        SELECT id, symbol, ex_date, pay_date, per_share_usd, shares_held, gross_usd, source,
               broker_account, broker_transaction_id, dedup_key, transaction_status,
               dividend_type, withholding_usd, net_usd, currency, is_excluded,
               exclusion_reason, description, source_row_number
    """

    @staticmethod
    def _row_to_receipt(row: Any) -> DividendReceipt:
        def _col(name: str, default: Any = None) -> Any:
            try:
                return row[name]
            except (KeyError, IndexError, TypeError):
                return default

        gross = float(_col("gross_usd", 0.0))
        withholding = float(_col("withholding_usd", 0.0) or 0.0)
        net_val = _col("net_usd")
        net_usd = (
            float(net_val)
            if net_val is not None
            else net_from_gross_and_withholding(
                gross_usd=gross,
                withholding_usd=withholding,
            )
        )
        excluded = _col("is_excluded", 0)
        return DividendReceipt(
            id=int(_col("id")) if _col("id") is not None else None,
            symbol=str(_col("symbol")),
            ex_date=parse_date(_col("ex_date")),
            pay_date=parse_date(_col("pay_date")),
            per_share_usd=float(_col("per_share_usd")),
            shares_held=float(_col("shares_held")),
            gross_usd=gross,
            source=str(_col("source") or "computed"),
            broker_account=_col("broker_account"),
            broker_transaction_id=_col("broker_transaction_id"),
            dedup_key=_col("dedup_key"),
            transaction_status=str(_col("transaction_status") or TRANSACTION_STATUS_POSTED),
            dividend_type=str(_col("dividend_type") or DIVIDEND_TYPE_ACTUAL),
            withholding_usd=withholding,
            net_usd=net_usd,
            currency=str(_col("currency") or "USD"),
            is_excluded=bool(excluded),
            exclusion_reason=_col("exclusion_reason"),
            description=_col("description"),
            source_row_number=(
                int(_col("source_row_number")) if _col("source_row_number") is not None else None
            ),
        )

    def upsert_broker_receipt(
        self,
        *,
        symbol: str,
        ex_date: date,
        pay_date: date,
        per_share_usd: float,
        shares_held: float,
        gross_usd: float,
        withholding_usd: float,
        net_usd: float,
        dedup_key: str,
        broker_account: str | None = None,
        broker_transaction_id: str | None = None,
        source_file_hash: str | None = None,
        source_row_number: int | None = None,
        dividend_type: str = DIVIDEND_TYPE_ACTUAL,
        description: str | None = None,
        currency: str = "USD",
    ) -> str:
        """Idempotent upsert keyed by ``dedup_key``. Returns added/updated/duplicate/unchanged."""
        symbol = symbol.strip().upper()
        existing = self._find_by_dedup_key(dedup_key)
        if existing is not None:
            if (
                existing.gross_usd == round(gross_usd, 2)
                and existing.net_usd == round(net_usd, 2)
                and existing.withholding_usd == round(withholding_usd, 2)
                and existing.pay_date == pay_date
                and not existing.is_excluded
            ):
                return "duplicate"
            if existing.id is not None and self._update_receipt_row(
                existing.id,
                ex_date=ex_date,
                pay_date=pay_date,
                per_share_usd=per_share_usd,
                shares_held=shares_held,
                gross_usd=gross_usd,
                withholding_usd=withholding_usd,
                net_usd=net_usd,
                source="ibkr",
                dividend_type=dividend_type,
                description=description,
                source_file_hash=source_file_hash,
                source_row_number=source_row_number,
                is_excluded=False,
                exclusion_reason=None,
            ):
                return "updated"
            return "unchanged"

        inserted = self._insert_receipt(
            symbol,
            ex_date=ex_date,
            pay_date=pay_date,
            per_share_usd=per_share_usd,
            shares_held=shares_held,
            gross_usd=gross_usd,
            source="ibkr",
            withholding_usd=withholding_usd,
            net_usd=net_usd,
            dedup_key=dedup_key,
            broker_account=broker_account,
            broker_transaction_id=broker_transaction_id,
            source_file_hash=source_file_hash,
            source_row_number=source_row_number,
            dividend_type=dividend_type,
            description=description,
            currency=currency,
        )
        return "added" if inserted else "duplicate"

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
            if fallback is None:
                fallback = self._find_ibkr_receipt_by_pay_date(
                    symbol,
                    pay_date=pay_date,
                    per_share_usd=per_share_usd,
                    gross_usd=gross_usd,
                )
            if fallback is not None and fallback.source == "ibkr":
                return "unchanged"
            existing = fallback
        if existing is None:
            dedup_key = build_dedup_key(
                DividendDedupInput(
                    broker_account=None,
                    broker_transaction_id=None,
                    symbol=symbol,
                    isin=None,
                    pay_date=pay_date,
                    currency="USD",
                    gross_usd=gross_usd,
                    withholding_usd=0.0,
                    net_usd=gross_usd,
                )
            )
            if source != "ibkr":
                broker_row = self._find_by_dedup_key(dedup_key)
                if broker_row is not None and broker_row.source == "ibkr":
                    return "unchanged"
            inserted = self._insert_receipt(
                symbol,
                ex_date=ex_date,
                pay_date=pay_date,
                per_share_usd=per_share_usd,
                shares_held=shares_held,
                gross_usd=gross_usd,
                source=source,
                dedup_key=dedup_key,
                dividend_type=DIVIDEND_TYPE_COMPUTED if source != "ibkr" else DIVIDEND_TYPE_ACTUAL,
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

        if existing.id is not None and existing.source == "ibkr" and source != "ibkr":
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

    def _find_by_dedup_key(self, dedup_key: str) -> DividendReceipt | None:
        with self._connect() as connection:
            if connection.is_postgres:
                row = connection.execute(
                    f"{self._RECEIPT_SELECT} FROM dividend_receipts "
                    "WHERE user_id = ? AND dedup_key = ? LIMIT 1",
                    (connection.user_id, dedup_key),
                ).fetchone()
            else:
                row = connection.execute(
                    f"{self._RECEIPT_SELECT} FROM dividend_receipts WHERE dedup_key = ? LIMIT 1",
                    (dedup_key,),
                ).fetchone()
        return self._row_to_receipt(row) if row else None

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

    def _find_ibkr_receipt_by_pay_date(
        self,
        symbol: str,
        *,
        pay_date: date,
        per_share_usd: float,
        gross_usd: float,
    ) -> DividendReceipt | None:
        """Match broker receipts when library sync uses a different ex-date."""
        symbol = symbol.strip().upper()
        per = round(float(per_share_usd), 6)
        gross = round(float(gross_usd), 2)
        with self._connect() as connection:
            if connection.is_postgres:
                row = connection.execute(
                    """
                    SELECT id, symbol, ex_date, pay_date, per_share_usd,
                           shares_held, gross_usd, source
                    FROM dividend_receipts
                    WHERE user_id = ? AND symbol = ? AND pay_date = ? AND source = 'ibkr'
                      AND ABS(per_share_usd - ?) < 0.000001
                      AND ABS(gross_usd - ?) < 0.05
                    LIMIT 1
                    """,
                    (connection.user_id, symbol, pay_date.isoformat(), per, gross),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT id, symbol, ex_date, pay_date, per_share_usd,
                           shares_held, gross_usd, source
                    FROM dividend_receipts
                    WHERE symbol = ? AND pay_date = ? AND source = 'ibkr'
                      AND ABS(per_share_usd - ?) < 0.000001
                      AND ABS(gross_usd - ?) < 0.05
                    LIMIT 1
                    """,
                    (symbol, pay_date.isoformat(), per, gross),
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
            source=str(row["source"] or "ibkr"),
        )

    def _update_receipt_row(
        self,
        receipt_id: int,
        *,
        ex_date: date,
        pay_date: date,
        per_share_usd: float,
        shares_held: float,
        gross_usd: float,
        source: str,
        withholding_usd: float = 0.0,
        net_usd: float | None = None,
        dividend_type: str = DIVIDEND_TYPE_ACTUAL,
        description: str | None = None,
        source_file_hash: str | None = None,
        source_row_number: int | None = None,
        is_excluded: bool = False,
        exclusion_reason: str | None = None,
    ) -> bool:
        net = (
            net_usd
            if net_usd is not None
            else net_from_gross_and_withholding(
                gross_usd=gross_usd,
                withholding_usd=withholding_usd,
            )
        )
        with self._connect() as connection:
            params = (
                ex_date.isoformat(),
                pay_date.isoformat(),
                per_share_usd,
                shares_held,
                gross_usd,
                source,
                withholding_usd,
                net,
                dividend_type,
                description,
                source_file_hash,
                source_row_number,
                int(is_excluded),
                exclusion_reason,
                receipt_id,
            )
            if connection.is_postgres:
                cursor = connection.execute(
                    """
                    UPDATE dividend_receipts
                    SET ex_date = ?, pay_date = ?, per_share_usd = ?, shares_held = ?,
                        gross_usd = ?, source = ?, withholding_usd = ?, net_usd = ?,
                        dividend_type = ?, description = ?, source_file_hash = ?,
                        source_row_number = ?, is_excluded = ?, exclusion_reason = ?
                    WHERE user_id = ? AND id = ?
                    """,
                    (*params[:-1], connection.user_id, receipt_id),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE dividend_receipts
                    SET ex_date = ?, pay_date = ?, per_share_usd = ?, shares_held = ?,
                        gross_usd = ?, source = ?, withholding_usd = ?, net_usd = ?,
                        dividend_type = ?, description = ?, source_file_hash = ?,
                        source_row_number = ?, is_excluded = ?, exclusion_reason = ?
                    WHERE id = ?
                    """,
                    params,
                )
            return int(getattr(cursor, "rowcount", 0) or 0) > 0

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
        withholding_usd: float = 0.0,
        net_usd: float | None = None,
        dedup_key: str | None = None,
        broker_account: str | None = None,
        broker_transaction_id: str | None = None,
        source_file_hash: str | None = None,
        source_row_number: int | None = None,
        dividend_type: str | None = None,
        description: str | None = None,
        currency: str = "USD",
    ) -> bool:
        symbol = symbol.strip().upper()
        dtype = dividend_type or (
            DIVIDEND_TYPE_COMPUTED if source != "ibkr" else DIVIDEND_TYPE_ACTUAL
        )
        net = (
            net_usd
            if net_usd is not None
            else net_from_gross_and_withholding(
                gross_usd=gross_usd,
                withholding_usd=withholding_usd,
            )
        )
        if dedup_key is None:
            dedup_key = build_dedup_key(
                DividendDedupInput(
                    broker_account=broker_account,
                    broker_transaction_id=broker_transaction_id,
                    symbol=symbol,
                    isin=None,
                    pay_date=pay_date,
                    currency=currency,
                    gross_usd=gross_usd,
                    withholding_usd=withholding_usd,
                    net_usd=net,
                )
            )
        with self._connect() as connection:
            if connection.is_postgres:
                try:
                    row = connection.execute(
                        """
                        INSERT INTO dividend_receipts (
                          user_id, symbol, ex_date, pay_date, per_share_usd, shares_held,
                          gross_usd, source, broker_account, broker_transaction_id,
                          source_file_hash, source_row_number, dedup_key, transaction_status,
                          dividend_type, withholding_usd, net_usd, currency, description
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'posted', ?, ?, ?, ?, ?)
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
                            broker_account,
                            broker_transaction_id,
                            source_file_hash,
                            source_row_number,
                            dedup_key,
                            dtype,
                            withholding_usd,
                            net,
                            currency,
                            description,
                        ),
                    ).fetchone()
                except Exception as exc:
                    if is_unique_violation(exc):
                        return False
                    raise
                return row is not None

            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO dividend_receipts (
                  symbol, ex_date, pay_date, per_share_usd, shares_held, gross_usd, source,
                  broker_account, broker_transaction_id, source_file_hash, source_row_number,
                  dedup_key, transaction_status, dividend_type, withholding_usd, net_usd,
                  currency, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'posted', ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    ex_date.isoformat(),
                    pay_date.isoformat(),
                    per_share_usd,
                    shares_held,
                    gross_usd,
                    source,
                    broker_account,
                    broker_transaction_id,
                    source_file_hash,
                    source_row_number,
                    dedup_key,
                    dtype,
                    withholding_usd,
                    net,
                    currency,
                    description,
                ),
            )
            return int(getattr(cursor, "rowcount", 0) or 0) > 0

    def list_for_symbol(self, symbol: str) -> list[DividendReceipt]:
        symbol = symbol.strip().upper()
        with self._connect() as connection:
            if connection.is_postgres:
                rows = connection.execute(
                    f"{self._RECEIPT_SELECT} FROM dividend_receipts "
                    "WHERE user_id = ? AND symbol = ? ORDER BY pay_date, ex_date",
                    (connection.user_id, symbol),
                ).fetchall()
            else:
                rows = connection.execute(
                    f"{self._RECEIPT_SELECT} FROM dividend_receipts "
                    "WHERE symbol = ? ORDER BY pay_date, ex_date",
                    (symbol,),
                ).fetchall()

        return [self._row_to_receipt(row) for row in rows]

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

    def monthly_gross_totals(
        self,
        *,
        symbols: set[str] | None = None,
        posted_cash_only: bool = True,
        computed_only: bool = False,
        through: date | None = None,
    ) -> dict[tuple[int, int], float]:
        """Aggregate gross cash by (year, month) of payment date."""
        symbol_filter = ""
        symbol_params: tuple[str, ...] = ()
        if symbols:
            normalized = sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
            if normalized:
                placeholders = ",".join("?" * len(normalized))
                symbol_filter = f" AND symbol IN ({placeholders})"
                symbol_params = tuple(normalized)
        totals_filter = _receipt_totals_filter(
            posted_cash_only=posted_cash_only,
            computed_only=computed_only,
        )
        through_filter = ""
        through_params: tuple[str, ...] = ()
        if through is not None:
            through_filter = " AND pay_date <= ?"
            through_params = (through.isoformat(),)

        with self._connect() as connection:
            if connection.is_postgres:
                rows = connection.execute(
                    f"""
                    SELECT
                      EXTRACT(YEAR FROM pay_date)::INTEGER AS year,
                      EXTRACT(MONTH FROM pay_date)::INTEGER AS month,
                      SUM(gross_usd) AS gross
                    FROM dividend_receipts
                    WHERE user_id = ?{symbol_filter}{through_filter}{totals_filter}
                    GROUP BY 1, 2
                    ORDER BY 1, 2
                    """,
                    (connection.user_id, *symbol_params, *through_params),
                ).fetchall()
            else:
                rows = connection.execute(
                    f"""
                    SELECT
                      CAST(strftime('%Y', pay_date) AS INTEGER) AS year,
                      CAST(strftime('%m', pay_date) AS INTEGER) AS month,
                      SUM(gross_usd) AS gross
                    FROM dividend_receipts
                    WHERE 1=1{symbol_filter}{through_filter}{totals_filter}
                    GROUP BY 1, 2
                    ORDER BY 1, 2
                    """,
                    (*symbol_params, *through_params),
                ).fetchall()

        totals: dict[tuple[int, int], float] = {}
        for row in rows:
            totals[(int(row["year"]), int(row["month"]))] = round(float(row["gross"]), 2)
        return totals

    def monthly_net_totals(
        self,
        *,
        symbols: set[str] | None = None,
        through: date | None = None,
        posted_cash_only: bool = True,
        computed_only: bool = False,
    ) -> dict[tuple[int, int], float]:
        """Aggregate net cash by (year, month) of payment date for posted dividends."""
        symbol_filter = ""
        symbol_params: tuple[str, ...] = ()
        if symbols:
            normalized = sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
            if normalized:
                placeholders = ",".join("?" * len(normalized))
                symbol_filter = f" AND symbol IN ({placeholders})"
                symbol_params = tuple(normalized)
        totals_filter = _receipt_totals_filter(
            posted_cash_only=posted_cash_only,
            computed_only=computed_only,
        )
        through_filter = ""
        through_params: tuple[str, ...] = ()
        if through is not None:
            through_filter = " AND pay_date <= ?"
            through_params = (through.isoformat(),)

        with self._connect() as connection:
            if connection.is_postgres:
                rows = connection.execute(
                    f"""
                    SELECT
                      EXTRACT(YEAR FROM pay_date)::INTEGER AS year,
                      EXTRACT(MONTH FROM pay_date)::INTEGER AS month,
                      SUM(COALESCE(net_usd, gross_usd - withholding_usd)) AS net
                    FROM dividend_receipts
                    WHERE user_id = ?{symbol_filter}{through_filter}{totals_filter}
                    GROUP BY 1, 2
                    ORDER BY 1, 2
                    """,
                    (connection.user_id, *symbol_params, *through_params),
                ).fetchall()
            else:
                rows = connection.execute(
                    f"""
                    SELECT
                      CAST(strftime('%Y', pay_date) AS INTEGER) AS year,
                      CAST(strftime('%m', pay_date) AS INTEGER) AS month,
                      SUM(COALESCE(net_usd, gross_usd - withholding_usd)) AS net
                    FROM dividend_receipts
                    WHERE 1=1{symbol_filter}{through_filter}{totals_filter}
                    GROUP BY 1, 2
                    ORDER BY 1, 2
                    """,
                    (*symbol_params, *through_params),
                ).fetchall()

        totals: dict[tuple[int, int], float] = {}
        for row in rows:
            totals[(int(row["year"]), int(row["month"]))] = round(float(row["net"]), 2)
        return totals

    def yearly_net_totals(self, *, through: date | None = None) -> dict[int, float]:
        monthly = self.monthly_net_totals(through=through)
        yearly: dict[int, float] = {}
        for (year, _month), net in monthly.items():
            yearly[year] = round(yearly.get(year, 0.0) + net, 2)
        return yearly

    def backfill_dedup_keys(self) -> int:
        """Assign dedup keys to legacy rows missing them."""
        updated = 0
        with self._connect() as connection:
            if connection.is_postgres:
                rows = connection.execute(
                    f"{self._RECEIPT_SELECT} FROM dividend_receipts "
                    "WHERE user_id = ? AND (dedup_key IS NULL OR dedup_key = '') "
                    "AND COALESCE(is_excluded, false) = false",
                    (connection.user_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    f"{self._RECEIPT_SELECT} FROM dividend_receipts "
                    "WHERE (dedup_key IS NULL OR dedup_key = '') "
                    "AND COALESCE(is_excluded, 0) = 0",
                ).fetchall()
        for row in rows:
            receipt = self._row_to_receipt(row)
            dedup_key = build_dedup_key(
                DividendDedupInput(
                    broker_account=receipt.broker_account,
                    broker_transaction_id=receipt.broker_transaction_id,
                    symbol=receipt.symbol,
                    isin=None,
                    pay_date=receipt.pay_date,
                    currency=receipt.currency,
                    gross_usd=receipt.gross_usd,
                    withholding_usd=receipt.withholding_usd,
                    net_usd=receipt.net_usd or receipt.gross_usd,
                )
            )
            if receipt.id is not None and self._update_dedup_key(receipt.id, dedup_key):
                updated += 1
        return updated

    def _update_dedup_key(self, receipt_id: int, dedup_key: str) -> bool:
        with self._connect() as connection:
            if connection.is_postgres:
                cursor = connection.execute(
                    "UPDATE dividend_receipts SET dedup_key = ? WHERE user_id = ? AND id = ?",
                    (dedup_key, connection.user_id, receipt_id),
                )
            else:
                cursor = connection.execute(
                    "UPDATE dividend_receipts SET dedup_key = ? WHERE id = ?",
                    (dedup_key, receipt_id),
                )
            return int(getattr(cursor, "rowcount", 0) or 0) > 0

    def dedupe_mark_duplicates(self) -> int:
        """Keep one canonical row per dedup key; mark others excluded (non-destructive)."""
        marked = 0
        with self._connect() as connection:
            if connection.is_postgres:
                rows = connection.execute(
                    """
                    SELECT dedup_key, MIN(id) AS keep_id, COUNT(*) AS cnt
                    FROM dividend_receipts
                    WHERE user_id = ? AND dedup_key IS NOT NULL AND dedup_key != ''
                      AND COALESCE(is_excluded, false) = false
                    GROUP BY dedup_key
                    HAVING COUNT(*) > 1
                    """,
                    (connection.user_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT dedup_key, MIN(id) AS keep_id, COUNT(*) AS cnt
                    FROM dividend_receipts
                    WHERE dedup_key IS NOT NULL AND dedup_key != ''
                      AND COALESCE(is_excluded, 0) = 0
                    GROUP BY dedup_key
                    HAVING COUNT(*) > 1
                    """,
                ).fetchall()

        for row in rows:
            dedup_key = row["dedup_key"]
            keep_id = int(row["keep_id"])
            with self._connect() as connection:
                if connection.is_postgres:
                    cursor = connection.execute(
                        """
                        UPDATE dividend_receipts
                        SET is_excluded = TRUE,
                            exclusion_reason = 'duplicate_dedup_key',
                            dedup_key = NULL
                        WHERE user_id = ? AND dedup_key = ? AND id != ?
                          AND COALESCE(is_excluded, false) = false
                        """,
                        (connection.user_id, dedup_key, keep_id),
                    )
                else:
                    cursor = connection.execute(
                        """
                        UPDATE dividend_receipts
                        SET is_excluded = 1,
                            exclusion_reason = 'duplicate_dedup_key',
                            dedup_key = NULL
                        WHERE dedup_key = ? AND id != ?
                          AND COALESCE(is_excluded, 0) = 0
                        """,
                        (dedup_key, keep_id),
                    )
                marked += int(getattr(cursor, "rowcount", 0) or 0)
        return marked

    def quarterly_gross_totals(
        self,
        *,
        symbols: set[str] | None = None,
    ) -> dict[tuple[int, int], float]:
        """Aggregate gross cash by (year, calendar quarter) of payment date."""
        monthly = self.monthly_gross_totals(symbols=symbols)
        totals: dict[tuple[int, int], float] = {}
        for (year, month), gross in monthly.items():
            quarter = (month - 1) // 3 + 1
            key = (year, quarter)
            totals[key] = round(totals.get(key, 0.0) + gross, 2)
        return totals

    def list_for_month(
        self,
        year: int,
        month: int,
        *,
        through: date | None = None,
        symbols: set[str] | None = None,
    ) -> list[DividendReceipt]:
        """Receipts with pay_date in the month, capped at ``through`` (default month-end)."""
        through = through or date.today()
        if (year, month) > (through.year, through.month):
            return []

        last_day = calendar.monthrange(year, month)[1]
        month_end = date(year, month, last_day)
        cutoff = month_end if (year, month) < (through.year, through.month) else through
        start = date(year, month, 1).isoformat()
        end = cutoff.isoformat()

        with self._connect() as connection:
            posted_filter = _POSTED_CASH_WHERE
            if connection.is_postgres:
                if symbols:
                    placeholders = ", ".join("?" for _ in symbols)
                    rows = connection.execute(
                        f"""
                        {self._RECEIPT_SELECT}
                        FROM dividend_receipts
                        WHERE user_id = ?
                          AND pay_date >= ?
                          AND pay_date <= ?
                          AND symbol IN ({placeholders}){posted_filter}
                        ORDER BY pay_date, symbol, ex_date
                        """,
                        (connection.user_id, start, end, *sorted(symbols)),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        f"""
                        {self._RECEIPT_SELECT}
                        FROM dividend_receipts
                        WHERE user_id = ?
                          AND pay_date >= ?
                          AND pay_date <= ?{posted_filter}
                        ORDER BY pay_date, symbol, ex_date
                        """,
                        (connection.user_id, start, end),
                    ).fetchall()
            elif symbols:
                placeholders = ", ".join("?" for _ in symbols)
                rows = connection.execute(
                    f"""
                    {self._RECEIPT_SELECT}
                    FROM dividend_receipts
                    WHERE pay_date >= ?
                      AND pay_date <= ?
                      AND symbol IN ({placeholders}){posted_filter}
                    ORDER BY pay_date, symbol, ex_date
                    """,
                    (start, end, *sorted(symbols)),
                ).fetchall()
            else:
                rows = connection.execute(
                    f"""
                    {self._RECEIPT_SELECT}
                    FROM dividend_receipts
                    WHERE pay_date >= ?
                      AND pay_date <= ?{posted_filter}
                    ORDER BY pay_date, symbol, ex_date
                    """,
                    (start, end),
                ).fetchall()

        return [self._row_to_receipt(row) for row in rows]

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
