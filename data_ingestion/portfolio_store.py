"""
Portfolio holdings storage (PostgreSQL per user, or SQLite file in local dev).

Static position data (shares, cost basis, fees, dividends received) lives here;
market metrics come from stock_documents and live APIs.

Holdings are never seeded from source code — each user starts with an empty
portfolio (or data from migration / the UI). Use auth/demo_portfolio for the
test-user demo only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from config import DATA_DIR
from db.connection import open_portfolio_db, use_cloud_sql
from db.parsing import parse_optional_date


def _default_portfolio_db_path() -> Path:
    try:
        from auth.user_context import resolve_portfolio_db_path

        return resolve_portfolio_db_path()
    except Exception:
        return DATA_DIR / "portfolio.db"


def _default_seed() -> bool:
    return False


@dataclass(frozen=True)
class PortfolioHolding:
    """A single portfolio position."""

    symbol: str
    shares: float
    avg_cost_per_share: float
    acquisition_value: float
    commission: float
    dividends_paid: float
    estimated_avg_price: float
    sort_order: int
    company_name: str | None = None
    dividend_tracking_since: date | None = None


class PortfolioStore:
    """Read and write portfolio holdings in SQLite."""

    def __init__(
        self,
        db_path: Path | None = None,
        *,
        seed: bool | None = None,  # noqa: ARG002
    ) -> None:
        self.db_path = Path(db_path or _default_portfolio_db_path())
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
                CREATE TABLE IF NOT EXISTS holdings (
                  symbol TEXT PRIMARY KEY,
                  shares REAL NOT NULL,
                  avg_cost_per_share REAL NOT NULL,
                  acquisition_value REAL NOT NULL,
                  commission REAL NOT NULL DEFAULT 0,
                  dividends_paid REAL NOT NULL DEFAULT 0,
                  estimated_avg_price REAL,
                  sort_order INTEGER NOT NULL DEFAULT 0,
                  company_name TEXT
                )
                """
            )
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(holdings)").fetchall()
            }
            if "company_name" not in columns:
                connection.execute("ALTER TABLE holdings ADD COLUMN company_name TEXT")
            if "dividend_tracking_since" not in columns:
                connection.execute("ALTER TABLE holdings ADD COLUMN dividend_tracking_since TEXT")

    def list_holdings(self) -> list[PortfolioHolding]:
        with self._connect() as connection:
            if connection.is_postgres:
                rows = connection.execute(
                    """
                    SELECT
                      symbol, shares, avg_cost_per_share, acquisition_value,
                      commission, dividends_paid, estimated_avg_price,
                      sort_order, company_name, dividend_tracking_since
                    FROM holdings
                    WHERE user_id = ?
                    ORDER BY sort_order, symbol
                    """,
                    (connection.user_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT
                      symbol,
                      shares,
                      avg_cost_per_share,
                      acquisition_value,
                      commission,
                      dividends_paid,
                      estimated_avg_price,
                      sort_order,
                      company_name,
                      dividend_tracking_since
                    FROM holdings
                    ORDER BY sort_order, symbol
                    """
                ).fetchall()

        return [
            PortfolioHolding(
                symbol=row["symbol"],
                shares=row["shares"],
                avg_cost_per_share=row["avg_cost_per_share"],
                acquisition_value=row["acquisition_value"],
                commission=row["commission"],
                dividends_paid=row["dividends_paid"],
                estimated_avg_price=row["estimated_avg_price"] or 0.0,
                sort_order=row["sort_order"],
                company_name=row["company_name"],
                dividend_tracking_since=parse_optional_date(row["dividend_tracking_since"]),
            )
            for row in rows
        ]

    def get_holding(self, symbol: str) -> PortfolioHolding | None:
        symbol = symbol.strip().upper()
        with self._connect() as connection:
            if connection.is_postgres:
                row = connection.execute(
                    """
                    SELECT
                      symbol, shares, avg_cost_per_share, acquisition_value,
                      commission, dividends_paid, estimated_avg_price,
                      sort_order, company_name, dividend_tracking_since
                    FROM holdings
                    WHERE user_id = ? AND symbol = ?
                    """,
                    (connection.user_id, symbol),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT
                      symbol, shares, avg_cost_per_share, acquisition_value,
                      commission, dividends_paid, estimated_avg_price,
                      sort_order, company_name, dividend_tracking_since
                    FROM holdings
                    WHERE symbol = ?
                    """,
                    (symbol,),
                ).fetchone()
        if row is None:
            return None
        return PortfolioHolding(
            symbol=row["symbol"],
            shares=row["shares"],
            avg_cost_per_share=row["avg_cost_per_share"],
            acquisition_value=row["acquisition_value"],
            commission=row["commission"],
            dividends_paid=row["dividends_paid"],
            estimated_avg_price=row["estimated_avg_price"] or 0.0,
            sort_order=row["sort_order"],
            company_name=row["company_name"],
            dividend_tracking_since=parse_optional_date(row["dividend_tracking_since"]),
        )

    def holding_exists(self, symbol: str) -> bool:
        return self.get_holding(symbol) is not None

    def _next_sort_order(self, connection: Any) -> int:
        if connection.is_postgres:
            row = connection.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order "
                "FROM holdings WHERE user_id = ?",
                (connection.user_id,),
            ).fetchone()
            return int(row["next_order"])
        row = connection.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM holdings").fetchone()
        return int(row[0])

    def upsert_holding(
        self,
        symbol: str,
        *,
        shares: float,
        avg_cost_per_share: float,
        commission: float = 0.0,
        dividends_paid: float = 0.0,
        estimated_avg_price: float | None = None,
        company_name: str | None = None,
    ) -> PortfolioHolding:
        """Insert or replace a position (used when adding tickers from the UI)."""
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValueError("Symbol is required")
        if shares <= 0:
            raise ValueError("Shares must be positive")
        if avg_cost_per_share < 0:
            raise ValueError("Average cost cannot be negative")

        acquisition_value = round(shares * avg_cost_per_share, 2)
        est = estimated_avg_price if estimated_avg_price is not None else avg_cost_per_share
        tracking_since = date.today().isoformat()

        with self._connect() as connection:
            if connection.is_postgres:
                existing = connection.execute(
                    "SELECT symbol FROM holdings WHERE user_id = ? AND symbol = ?",
                    (connection.user_id, symbol),
                ).fetchone()
            else:
                existing = connection.execute(
                    "SELECT symbol FROM holdings WHERE symbol = ?",
                    (symbol,),
                ).fetchone()
            if existing:
                if connection.is_postgres:
                    connection.execute(
                        """
                        UPDATE holdings SET
                          shares = ?, avg_cost_per_share = ?, acquisition_value = ?,
                          commission = ?, dividends_paid = ?, estimated_avg_price = ?,
                          company_name = COALESCE(?, company_name)
                        WHERE user_id = ? AND symbol = ?
                        """,
                        (
                            shares,
                            avg_cost_per_share,
                            acquisition_value,
                            commission,
                            dividends_paid,
                            est,
                            company_name,
                            connection.user_id,
                            symbol,
                        ),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE holdings SET
                          shares = ?,
                          avg_cost_per_share = ?,
                          acquisition_value = ?,
                          commission = ?,
                          dividends_paid = ?,
                          estimated_avg_price = ?,
                          company_name = COALESCE(?, company_name)
                        WHERE symbol = ?
                        """,
                        (
                            shares,
                            avg_cost_per_share,
                            acquisition_value,
                            commission,
                            dividends_paid,
                            est,
                            company_name,
                            symbol,
                        ),
                    )
            else:
                sort_order = self._next_sort_order(connection)
                if connection.is_postgres:
                    connection.execute(
                        """
                        INSERT INTO holdings (
                          user_id, symbol, shares, avg_cost_per_share, acquisition_value,
                          commission, dividends_paid, estimated_avg_price,
                          sort_order, company_name, dividend_tracking_since
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            connection.user_id,
                            symbol,
                            shares,
                            avg_cost_per_share,
                            acquisition_value,
                            commission,
                            dividends_paid,
                            est,
                            sort_order,
                            company_name,
                            tracking_since,
                        ),
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO holdings (
                          symbol, shares, avg_cost_per_share, acquisition_value,
                          commission, dividends_paid, estimated_avg_price,
                          sort_order, company_name, dividend_tracking_since
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            symbol,
                            shares,
                            avg_cost_per_share,
                            acquisition_value,
                            commission,
                            dividends_paid,
                            est,
                            sort_order,
                            company_name,
                            tracking_since,
                        ),
                    )

        holding = self.get_holding(symbol)
        if holding is None:
            raise RuntimeError(f"Failed to save holding for {symbol}")
        return holding

    def update_holding(
        self,
        symbol: str,
        *,
        shares: float | None = None,
        avg_cost_per_share: float | None = None,
        commission: float | None = None,
        dividends_paid: float | None = None,
        estimated_avg_price: float | None = None,
        company_name: str | None = None,
    ) -> PortfolioHolding | None:
        """Patch fields on an existing position."""
        current = self.get_holding(symbol)
        if current is None:
            return None

        new_shares = shares if shares is not None else current.shares
        new_avg = (
            avg_cost_per_share if avg_cost_per_share is not None else current.avg_cost_per_share
        )
        return self.upsert_holding(
            symbol,
            shares=new_shares,
            avg_cost_per_share=new_avg,
            commission=commission if commission is not None else current.commission,
            dividends_paid=(
                dividends_paid if dividends_paid is not None else current.dividends_paid
            ),
            estimated_avg_price=(
                estimated_avg_price
                if estimated_avg_price is not None
                else current.estimated_avg_price
            ),
            company_name=company_name if company_name is not None else current.company_name,
        )

    def delete_holding(self, symbol: str) -> bool:
        symbol = symbol.strip().upper()
        from data_ingestion.dividend_receipt_store import DividendReceiptStore

        DividendReceiptStore(db_path=self.db_path).delete_for_symbol(symbol)
        with self._connect() as connection:
            if connection.is_postgres:
                cursor = connection.execute(
                    "DELETE FROM holdings WHERE user_id = ? AND symbol = ?",
                    (connection.user_id, symbol),
                )
            else:
                cursor = connection.execute(
                    "DELETE FROM holdings WHERE symbol = ?",
                    (symbol,),
                )
            return bool(cursor.rowcount > 0)

    def set_dividends_paid(self, symbol: str, dividends_paid: float) -> None:
        """Update lifetime dividends received for a symbol (auto-sync)."""
        symbol = symbol.strip().upper()
        with self._connect() as connection:
            if connection.is_postgres:
                connection.execute(
                    """
                    UPDATE holdings SET dividends_paid = ?
                    WHERE user_id = ? AND symbol = ?
                    """,
                    (round(dividends_paid, 2), connection.user_id, symbol),
                )
            else:
                connection.execute(
                    "UPDATE holdings SET dividends_paid = ? WHERE symbol = ?",
                    (round(dividends_paid, 2), symbol),
                )

    def delete_all(self) -> int:
        with self._connect() as connection:
            if connection.is_postgres:
                cursor = connection.execute(
                    "DELETE FROM holdings WHERE user_id = ?",
                    (connection.user_id,),
                )
            else:
                cursor = connection.execute("DELETE FROM holdings")
            return int(cursor.rowcount or 0)
