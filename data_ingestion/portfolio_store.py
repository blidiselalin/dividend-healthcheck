"""
SQLite storage for portfolio holdings.

Static position data (shares, cost basis, fees, dividends received) is kept
locally while market metrics are resolved from the vector database and APIs.

Holdings are never seeded from source code — each user starts with an empty
portfolio (or data from migration / the UI). Use auth/demo_portfolio for the
test-user demo only.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from config import DATA_DIR


def _default_portfolio_db_path() -> Path:
    try:
        from auth.user_context import resolve_portfolio_db_path

        return resolve_portfolio_db_path()
    except Exception:
        return DATA_DIR / "portfolio.db"


def _default_seed() -> bool:
    return False


PORTFOLIO_DB_PATH = DATA_DIR / "portfolio.db"


@dataclass(frozen=True)
class PortfolioHolding:
    """A single portfolio position stored in SQLite."""

    symbol: str
    shares: float
    avg_cost_per_share: float
    acquisition_value: float
    commission: float
    dividends_paid: float
    estimated_avg_price: float
    sort_order: int
    company_name: Optional[str] = None


class PortfolioStore:
    """Read and write portfolio holdings in SQLite."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        *,
        seed: Optional[bool] = None,
    ) -> None:
        self.db_path = Path(db_path or _default_portfolio_db_path())
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        # seed kept for API compatibility; no built-in holdings to insert
        _ = seed if seed is not None else _default_seed()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
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
                row[1]
                for row in connection.execute("PRAGMA table_info(holdings)").fetchall()
            }
            if "company_name" not in columns:
                connection.execute(
                    "ALTER TABLE holdings ADD COLUMN company_name TEXT"
                )

    def list_holdings(self) -> List[PortfolioHolding]:
        with self._connect() as connection:
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
                  company_name
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
            )
            for row in rows
        ]

    def get_holding(self, symbol: str) -> Optional[PortfolioHolding]:
        symbol = symbol.strip().upper()
        for holding in self.list_holdings():
            if holding.symbol.upper() == symbol:
                return holding
        return None

    def holding_exists(self, symbol: str) -> bool:
        return self.get_holding(symbol) is not None

    def _next_sort_order(self, connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM holdings"
        ).fetchone()
        return int(row[0])

    def upsert_holding(
        self,
        symbol: str,
        *,
        shares: float,
        avg_cost_per_share: float,
        commission: float = 0.0,
        dividends_paid: float = 0.0,
        estimated_avg_price: Optional[float] = None,
        company_name: Optional[str] = None,
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

        with self._connect() as connection:
            existing = connection.execute(
                "SELECT symbol FROM holdings WHERE symbol = ?",
                (symbol,),
            ).fetchone()
            if existing:
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
                connection.execute(
                    """
                    INSERT INTO holdings (
                      symbol, shares, avg_cost_per_share, acquisition_value,
                      commission, dividends_paid, estimated_avg_price,
                      sort_order, company_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        shares: Optional[float] = None,
        avg_cost_per_share: Optional[float] = None,
        commission: Optional[float] = None,
        dividends_paid: Optional[float] = None,
        estimated_avg_price: Optional[float] = None,
        company_name: Optional[str] = None,
    ) -> Optional[PortfolioHolding]:
        """Patch fields on an existing position."""
        current = self.get_holding(symbol)
        if current is None:
            return None

        new_shares = shares if shares is not None else current.shares
        new_avg = (
            avg_cost_per_share
            if avg_cost_per_share is not None
            else current.avg_cost_per_share
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
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM holdings WHERE symbol = ?",
                (symbol,),
            )
            return cursor.rowcount > 0
