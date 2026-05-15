"""
SQLite storage for net dividend cash received (after withholding tax).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

from config import DATA_DIR

DIVIDEND_INCOME_DB_PATH = DATA_DIR / "portfolio.db"

# (year, month, net_dividend_usd) — net = brut × (1 − tax_rate)
DIVIDEND_NET_SEED: List[Tuple[int, int, float]] = [
    (2022, 12, 3.24),
    (2023, 1, 20.05),
    (2023, 2, 19.95),
    (2023, 3, 55.61),
    (2023, 4, 64.57),
    (2023, 5, 48.02),
    (2023, 6, 101.80),
    (2023, 7, 86.28),
    (2023, 8, 75.76),
    (2023, 9, 128.31),
    (2023, 10, 108.69),
    (2023, 11, 94.58),
    (2023, 12, 171.45),
    (2024, 1, 115.70),
    (2024, 2, 142.06),
    (2024, 3, 152.53),
    (2024, 4, 140.29),
    (2024, 5, 131.81),
    (2024, 6, 183.86),
    (2024, 7, 164.12),
    (2024, 8, 152.69),
    (2024, 9, 197.51),
    (2024, 10, 179.42),
    (2024, 11, 226.66),
    (2024, 12, 234.50),
    (2025, 1, 182.04),
    (2025, 2, 196.02),
    (2025, 3, 332.79),
    (2025, 4, 279.61),
    (2025, 5, 178.52),
    (2025, 6, 337.96),
    (2025, 7, 329.71),
    (2025, 8, 178.65),
    (2025, 9, 373.20),
    (2025, 10, 343.44),
    (2025, 11, 253.13),
    (2025, 12, 355.11),
    (2026, 1, 303.41),
    (2026, 2, 274.77),
    (2026, 3, 380.91),
    (2026, 4, 342.52),
]

MONTH_LABELS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]


@dataclass(frozen=True)
class MonthlyNetDividend:
    period: date
    year: int
    month: int
    month_label: str
    net_usd: float
    tax_rate_pct: float
    gross_usd: float
    tax_withheld_usd: float

    @property
    def period_key(self) -> str:
        return self.period.strftime("%Y-%m")


def dividend_tax_rate(year: int) -> float:
    """Withholding tax rate (fraction). 10% through 2025, 16% from 2026."""
    return 0.10 if year <= 2025 else 0.16


def net_to_gross(net_usd: float, year: int) -> float:
    rate = dividend_tax_rate(year)
    factor = 1.0 - rate
    if factor <= 0:
        return net_usd
    return net_usd / factor


class DividendIncomeStore:
    """Monthly net dividend records."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DIVIDEND_INCOME_DB_PATH)
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
                CREATE TABLE IF NOT EXISTS net_dividends (
                  period_key TEXT PRIMARY KEY,
                  year INTEGER NOT NULL,
                  month INTEGER NOT NULL,
                  net_usd REAL NOT NULL
                )
                """
            )

    def _seed_if_empty(self) -> None:
        with self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM net_dividends").fetchone()[0]
            if count:
                return
            self._insert_seed(connection)

    def _insert_seed(self, connection: sqlite3.Connection) -> None:
        rows = [
            (f"{year:04d}-{month:02d}", year, month, net_usd)
            for year, month, net_usd in DIVIDEND_NET_SEED
        ]
        connection.executemany(
            """
            INSERT INTO net_dividends (period_key, year, month, net_usd)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )

    def sync_seed(self) -> None:
        """Upsert authoritative seed values (safe to run on each load)."""
        with self._connect() as connection:
            for year, month, net_usd in DIVIDEND_NET_SEED:
                key = f"{year:04d}-{month:02d}"
                connection.execute(
                    """
                    INSERT INTO net_dividends (period_key, year, month, net_usd)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(period_key) DO UPDATE SET net_usd = excluded.net_usd
                    """,
                    (key, year, month, net_usd),
                )

    def list_dividends(self) -> List[MonthlyNetDividend]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT year, month, net_usd
                FROM net_dividends
                ORDER BY year, month
                """
            ).fetchall()

        records: List[MonthlyNetDividend] = []
        for row in rows:
            year = int(row["year"])
            month = int(row["month"])
            net = float(row["net_usd"])
            rate = dividend_tax_rate(year)
            gross = net_to_gross(net, year)
            records.append(
                MonthlyNetDividend(
                    period=date(year, month, 1),
                    year=year,
                    month=month,
                    month_label=MONTH_LABELS[month - 1],
                    net_usd=net,
                    tax_rate_pct=rate * 100,
                    gross_usd=round(gross, 2),
                    tax_withheld_usd=round(gross - net, 2),
                )
            )
        return records
