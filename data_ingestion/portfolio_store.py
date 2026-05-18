"""
SQLite storage for portfolio holdings.

Static position data (shares, cost basis, fees, dividends received) is kept
locally while market metrics are resolved from the vector database and APIs.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import DATA_DIR


def _default_portfolio_db_path() -> Path:
    try:
        from auth.user_context import resolve_portfolio_db_path

        return resolve_portfolio_db_path()
    except Exception:
        return DATA_DIR / "portfolio.db"


def _default_seed() -> bool:
    try:
        from auth.settings import auth_required

        return not auth_required()
    except Exception:
        return True


PORTFOLIO_DB_PATH = DATA_DIR / "portfolio.db"

# Authoritative share counts — update this list when you buy or sell.
# Format: (symbol, company name, shares)
PORTFOLIO_SHARES: List[Tuple[str, str, float]] = [
    ("ABBV", "AbbVie Common Stock", 15),
    ("ADM", "Archer-Daniels-Midland Co", 60),
    ("ADP", "Automatic Data Processing Inc", 20),
    ("AFG", "American Financial Group Inc", 35),
    ("AMAT", "Applied Materials Inc", 36),
    ("AMT", "American Tower Corp", 15),
    ("ARCC", "Ares Capital Corporation", 30),
    ("ARE", "Alexandria Real Estate Equities, Inc", 60),
    ("AWK", "American Water Works Co Inc", 46),
    ("BAC", "Bank of America Corp", 30),
    ("BBY", "Best Buy Co Inc", 50),
    ("BEN", "Franklin Resources Inc", 30),
    ("BMY", "Bristol-Myers Squibb Co", 60),
    ("BTI", "British American Tobacco P.l.c", 63),
    ("CMCSA", "Comcast Corp", 102),
    ("CSCO", "Cisco Systems Inc", 15),
    ("DVN", "Devon Energy Corp", 60),
    ("ESS", "Essex Property Trust Inc", 4),
    ("HSY", "Hershey Co", 30),
    ("IBM", "IBM Common Stock", 5),
    ("INTU", "Intuit Inc", 10),
    ("JNJ", "Johnson & Johnson", 20),
    ("KO", "Coca-Cola Co", 20),
    ("MDLZ", "MONDELEZ INTERNATIONAL INC Common Stock", 40),
    ("MDT", "Medtronic PLC", 10),
    ("MMM", "3M Co", 8),
    ("MO", "Altria Group Inc", 45),
    ("NEE", "NextEra Energy Inc", 50),
    ("NKE", "Nike Inc", 90),
    ("NNN", "NNN REIT Inc", 20),
    ("NSP", "Insperity Inc", 20),
    ("O", "Realty Income Corp", 77),
    ("PEP", "PepsiCo Inc", 35),
    ("PRU", "Prudential Financial Inc", 10),
    ("QCOM", "Qualcomm Inc", 25),
    ("SBUX", "Starbucks Corp", 50),
    ("SWK", "Stanley Black & Decker Inc", 10),
    ("SWKS", "Skyworks Solutions Inc", 50),
    ("T", "AT&T Inc", 13),
    ("TROW", "T Rowe Price Group Inc", 15),
    ("UGI", "UGI Corp", 65),
    ("VSNT", "Versant Media Group Inc", 4),
    ("VZ", "Verizon Communications Inc", 47),
    ("WPC", "W.p. Carey Inc", 22),
    ("XOM", "Exxon Mobil Corp", 35),
    ("ZTS", "Zoetis Inc", 45),
]

# Cost basis and lifetime dividends (avg cost, commission, dividends paid, est. price, sort order)
_COST_BASIS: Dict[str, Tuple[float, float, float, float, int]] = {
    "ABBV": (148.85, 1.05, 215.95, 217.04, 1),
    "ADM": (52.41, 1.71, 163.50, 52.60, 2),
    "ADP": (207.25, 0.68, 17.00, 0.00, 3),
    "AFG": (123.12, 2.08, 521.75, 131.80, 4),
    "AMAT": (158.61, 2.03, 64.32, 205.43, 5),
    "AMT": (188.70, 1.05, 250.60, 249.60, 6),
    "ARCC": (18.26, 0.71, 177.60, 23.25, 7),
    "ARE": (80.85, 1.72, 232.56, 98.83, 8),
    "AWK": (130.18, 2.01, 77.79, 142.60, 9),
    "BAC": (30.27, 1.38, 91.80, 53.65, 10),
    "BBY": (71.34, 2.05, 308.50, 77.85, 11),
    "BEN": (24.00, 1.04, 88.80, 24.30, 12),
    "BMY": (49.28, 1.72, 296.40, 53.37, 13),
    "BTI": (33.37, 1.68, 467.81, 50.75, 14),
    "CMCSA": (35.57, 2.64, 190.38, 39.96, 15),
    "CSCO": (47.14, 1.02, 70.40, 72.53, 16),
    "DVN": (42.28, 2.06, 127.40, 45.66, 17),
    "ESS": (218.00, 0.35, 127.64, 309.63, 18),
    "HSY": (170.93, 1.77, 247.69, 181.35, 19),
    "IBM": (123.20, 0.35, 100.20, 286.71, 20),
    "INTU": (394.00, 0.34, 0.00, 286.71, 21),
    "JNJ": (150.03, 1.04, 226.50, 176.45, 22),
    "KO": (58.58, 1.05, 113.20, 79.52, 23),
    "MDLZ": (58.67, 1.68, 87.90, 74.48, 24),
    "MDT": (80.25, 0.69, 94.22, 95.54, 25),
    "MMM": (115.10, 0.70, 100.48, 165.62, 26),
    "MO": (44.45, 1.71, 469.66, 60.14, 27),
    "NEE": (62.49, 1.74, 270.85, 82.53, 28),
    "NKE": (61.37, 3.77, 115.41, 75.92, 29),
    "NNN": (39.63, 0.68, 127.45, 44.41, 30),
    "NSP": (60.70, 0.69, 45.60, 62.00, 31),
    "O": (54.41, 3.46, 581.52, 61.36, 32),
    "PEP": (135.76, 1.35, 198.48, 153.56, 33),
    "PRU": (81.93, 0.70, 157.50, 115.29, 34),
    "QCOM": (126.26, 1.36, 120.60, 176.13, 35),
    "SBUX": (86.78, 2.41, 186.50, 98.46, 36),
    "SWK": (72.75, 0.70, 61.40, 84.08, 37),
    "SWKS": (62.16, 1.31, 145.60, 71.24, 38),
    "T": (18.73, 0.68, 44.99, 30.33, 39),
    "TROW": (111.67, 1.36, 184.38, 100.92, 40),
    "UGI": (26.25, 2.04, 245.67, 40.00, 41),
    "VSNT": (48.41, 0.00, 0.00, 48.23, 42),
    "VZ": (38.36, 1.08, 306.19, 48.23, 43),
    "WPC": (67.90, 1.02, 186.23, 65.36, 44),
    "XOM": (105.58, 2.46, 257.81, 123.50, 45),
    "ZTS": (121.31, 1.66, 22.75, 196.21, 46),
}


def _build_holdings_seed() -> List[tuple[str, float, float, float, float, float, float, int]]:
    rows: List[tuple[str, float, float, float, float, float, float, int]] = []
    for symbol, _company, shares in PORTFOLIO_SHARES:
        avg_cost, commission, dividends_paid, estimated_avg_price, sort_order = _COST_BASIS[symbol]
        acquisition_value = round(shares * avg_cost, 2)
        rows.append(
            (
                symbol,
                shares,
                avg_cost,
                acquisition_value,
                commission,
                dividends_paid,
                estimated_avg_price,
                sort_order,
            )
        )
    return rows


HOLDINGS_SEED: List[tuple[str, float, float, float, float, float, float, int]] = _build_holdings_seed()


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
        do_seed = _default_seed() if seed is None else seed
        if do_seed:
            self._seed_if_empty()
            self.sync_share_counts()

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

    def _seed_if_empty(self) -> None:
        with self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
            if count:
                return

            connection.executemany(
                """
                INSERT INTO holdings (
                  symbol,
                  shares,
                  avg_cost_per_share,
                  acquisition_value,
                  commission,
                  dividends_paid,
                  estimated_avg_price,
                  sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                HOLDINGS_SEED,
            )

    def sync_share_counts(self) -> int:
        """
        Apply share counts from PORTFOLIO_SHARES to the database.

        Recalculates acquisition_value as shares × avg_cost_per_share.
        Returns the number of rows updated.
        """
        shares_by_symbol = {symbol: shares for symbol, _name, shares in PORTFOLIO_SHARES}
        updated = 0
        with self._connect() as connection:
            for symbol, target_shares in shares_by_symbol.items():
                row = connection.execute(
                    "SELECT shares, avg_cost_per_share FROM holdings WHERE symbol = ?",
                    (symbol,),
                ).fetchone()
                if row is None:
                    continue
                avg_cost = float(row["avg_cost_per_share"])
                acquisition_value = round(target_shares * avg_cost, 2)
                current_shares = float(row["shares"])
                if current_shares == target_shares:
                    connection.execute(
                        """
                        UPDATE holdings
                        SET acquisition_value = ?
                        WHERE symbol = ? AND acquisition_value != ?
                        """,
                        (acquisition_value, symbol, acquisition_value),
                    )
                    continue
                connection.execute(
                    """
                    UPDATE holdings
                    SET shares = ?, acquisition_value = ?
                    WHERE symbol = ?
                    """,
                    (target_shares, acquisition_value, symbol),
                )
                updated += 1
        return updated

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
