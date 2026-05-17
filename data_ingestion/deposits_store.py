"""
SQLite storage for monthly account deposits and portfolio value snapshots.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

from config import DATA_DIR

DEPOSITS_DB_PATH = DATA_DIR / "portfolio.db"

# (year, month, label, deposit_eur, deposit_usd, portfolio_eur)
DEPOSITS_SEED: List[Tuple[int, int, str, float, float, float]] = [
    (2022, 12, "December 2022", 6800.00, 7215.89, 6691.00),
    (2023, 1, "January 2023", 1500.00, 1631.40, 8519.38),
    (2023, 2, "February 2023", 4000.00, 4279.60, 12213.37),
    (2023, 3, "March 2023", 3528.00, 3734.25, 15345.06),
    (2023, 4, "April 2023", 1506.08, 1626.94, 16851.22),
    (2023, 5, "May 2023", 2500.00, 2745.50, 18621.97),
    (2023, 6, "June 2023", 2000.00, 2192.80, 21227.30),
    (2023, 7, "July 2023", 1500.00, 1650.78, 23489.45),
    (2023, 8, "August 2023", 2000.00, 2196.26, 24962.17),
    (2023, 9, "September 2023", 1500.00, 1612.91, 25544.61),
    (2023, 10, "October 2023", 4500.00, 4771.89, 29479.00),
    (2023, 11, "November 2023", 1500.00, 1610.25, 32681.26),
    (2023, 12, "December 2023", 2500.00, 2726.75, 36543.80),
    (2024, 1, "January 2024", 1500.00, 1647.11, 38047.97),
    (2024, 2, "February 2024", 1500.00, 1620.75, 39585.49),
    (2024, 3, "March 2024", 2077.89, 2255.13, 43434.19),
    (2024, 4, "April 2024", 1600.00, 1734.05, 43377.98),
    (2024, 5, "May 2024", 1500.00, 1609.44, 46170.37),
    (2024, 6, "June 2024", 1500.00, 1632.20, 47603.12),
    (2024, 7, "July 2024", 2000.00, 2149.58, 52495.95),
    (2024, 8, "August 2024", 1500.00, 1637.85, 54942.85),
    (2024, 9, "September 2024", 1500.00, 1655.21, 57211.82),
    (2024, 10, "October 2024", 1500.00, 1642.20, 58395.46),
    (2024, 11, "November 2024", 1500.00, 1619.18, 63807.15),
    (2024, 12, "December 2024", 4500.00, 4729.10, 65006.66),
    (2025, 1, "January 2025", 2000.00, 2048.72, 68808.03),
    (2025, 2, "February 2025", 11800.00, 12343.27, 83338.68),
    (2025, 3, "March 2025", 1800.00, 1867.68, 83436.87),
    (2025, 4, "April 2025", 5360.25, 5919.32, 78763.73),
    (2025, 5, "May 2025", 3500.00, 3956.58, 82789.31),
    (2025, 6, "June 2025", 1500.00, 1732.55, 85439.23),
    (2025, 7, "July 2025", 1500.00, 1759.53, 88071.88),
    (2025, 8, "August 2025", 1500.00, 1737.45, 93188.74),
    (2025, 9, "September 2025", 1500.00, 1744.97, 95514.36),
    (2025, 10, "October 2025", 1500.00, 1759.95, 98356.58),
    (2025, 11, "November 2025", 1500.00, 1738.80, 99742.56),
    (2025, 12, "December 2025", 1000.00, 1160.67, 99084.96),
    (2026, 1, "January 2026", 1498.85, 1575.00, 105633.31),
    (2026, 2, "February 2026", 1687.88, 2000.00, 113902.50),
    (2026, 3, "March 2026", 4251.90, 5000.00, 115409.14),
    (2026, 4, "April 2026", 0.00, 0.00, 117565.63),
    (2026, 5, "May 2026", 4111.60, 4821.01, 0.00),
]


@dataclass(frozen=True)
class MonthlyDeposit:
    """One month of deposits and portfolio snapshot."""

    period: date
    label: str
    deposit_eur: float
    deposit_usd: float
    portfolio_eur: float
    sort_order: int

    @property
    def period_key(self) -> str:
        return self.period.strftime("%Y-%m")


class DepositsStore:
    """Read monthly deposit records from SQLite (same DB as holdings)."""

    def __init__(self, db_path: Optional[Path] = None, *, seed: bool = True) -> None:
        self.db_path = Path(db_path or DEPOSITS_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        if seed:
            self._seed_if_empty()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS monthly_deposits (
                  period_key TEXT PRIMARY KEY,
                  year INTEGER NOT NULL,
                  month INTEGER NOT NULL,
                  label TEXT NOT NULL,
                  deposit_eur REAL NOT NULL,
                  deposit_usd REAL NOT NULL,
                  portfolio_eur REAL NOT NULL,
                  sort_order INTEGER NOT NULL
                )
                """
            )

    def _seed_if_empty(self) -> None:
        with self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM monthly_deposits").fetchone()[0]
            if count:
                return
            rows = [
                (
                    f"{year:04d}-{month:02d}",
                    year,
                    month,
                    label,
                    deposit_eur,
                    deposit_usd,
                    portfolio_eur,
                    index,
                )
                for index, (year, month, label, deposit_eur, deposit_usd, portfolio_eur) in enumerate(
                    DEPOSITS_SEED, start=1
                )
            ]
            connection.executemany(
                """
                INSERT INTO monthly_deposits (
                  period_key, year, month, label,
                  deposit_eur, deposit_usd, portfolio_eur, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def list_deposits(self) -> List[MonthlyDeposit]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT year, month, label, deposit_eur, deposit_usd, portfolio_eur, sort_order
                FROM monthly_deposits
                ORDER BY sort_order
                """
            ).fetchall()

        return [
            MonthlyDeposit(
                period=date(row["year"], row["month"], 1),
                label=row["label"],
                deposit_eur=float(row["deposit_eur"]),
                deposit_usd=float(row["deposit_usd"]),
                portfolio_eur=float(row["portfolio_eur"]),
                sort_order=int(row["sort_order"]),
            )
            for row in rows
        ]

    def upsert_deposit(
        self,
        *,
        year: int,
        month: int,
        label: str,
        deposit_eur: float,
        deposit_usd: float,
        portfolio_eur: float,
    ) -> MonthlyDeposit:
        period_key = f"{year:04d}-{month:02d}"
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT sort_order FROM monthly_deposits WHERE period_key = ?",
                (period_key,),
            ).fetchone()
            if existing:
                connection.execute(
                    """
                    UPDATE monthly_deposits SET
                      year = ?, month = ?, label = ?,
                      deposit_eur = ?, deposit_usd = ?, portfolio_eur = ?
                    WHERE period_key = ?
                    """,
                    (
                        year,
                        month,
                        label,
                        deposit_eur,
                        deposit_usd,
                        portfolio_eur,
                        period_key,
                    ),
                )
                sort_order = int(existing["sort_order"])
            else:
                max_order = connection.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM monthly_deposits"
                ).fetchone()[0]
                sort_order = int(max_order)
                connection.execute(
                    """
                    INSERT INTO monthly_deposits (
                      period_key, year, month, label,
                      deposit_eur, deposit_usd, portfolio_eur, sort_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        period_key,
                        year,
                        month,
                        label,
                        deposit_eur,
                        deposit_usd,
                        portfolio_eur,
                        sort_order,
                    ),
                )

        for deposit in self.list_deposits():
            if deposit.period_key == period_key:
                return deposit
        raise RuntimeError(f"Failed to save deposit for {period_key}")

    def delete_deposit(self, period_key: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM monthly_deposits WHERE period_key = ?",
                (period_key,),
            )
            return cursor.rowcount > 0
