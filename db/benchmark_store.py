"""
Persistent storage for benchmark ETF/index price history and metadata.

Two tables (shared, not per-user):
  benchmark_price_history — daily close prices fetched from Yahoo Finance.
  benchmark_etf_info      — display name, description, expense ratio, best-practices text.

In Postgres mode (use_cloud_sql()) both tables live in the main DB and are
created by migration 004_benchmark_price_history.sql.

In SQLite mode (local dev / unit tests) the tables are created on first use
in the file passed as ``db_path`` (defaults to DATA_DIR/benchmark_cache.db).
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

from config import DATA_DIR
from db.connection import use_cloud_sql

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Seed metadata — one entry per yfinance symbol used in benchmark_purchases_seed
# ---------------------------------------------------------------------------

BENCHMARK_ETF_SEED: dict[str, dict[str, Any]] = {
    "^GSPC": {
        "display_name": "S&P 500",
        "full_name": "S&P 500 Index",
        "description": (
            "Tracks the 500 largest US publicly traded companies by market capitalisation, "
            "weighted by float-adjusted market cap.  Broadly diversified across all GICS sectors."
        ),
        "expense_ratio_pct": None,
        "category": "US Large Cap Blend",
        "currency": "USD",
        "best_practices": (
            "• Use as the primary equity benchmark for any long-only US portfolio.\n"
            "• Total-return version (including dividends) gives a more complete comparison.\n"
            "• Accessible via low-cost ETFs: SPY (0.09 %), IVV (0.03 %), VOO (0.03 %).\n"
            "• Rebalances quarterly; sector tilts shift over time — monitor concentration."
        ),
    },
    "SCHD": {
        "display_name": "SCHD",
        "full_name": "Schwab U.S. Dividend Equity ETF",
        "description": (
            "Tracks the Dow Jones U.S. Dividend 100 Index — 100 US stocks selected for "
            "dividend consistency, fundamental quality (cash-flow/debt, ROE), and high "
            "relative dividend yield.  Market-cap weighted within the screen."
        ),
        "expense_ratio_pct": 0.06,
        "category": "US Large Cap Dividend",
        "currency": "USD",
        "best_practices": (
            "• Natural benchmark for dividend-growth investors: combines yield with quality.\n"
            "• Requires ≥10 consecutive years of dividend payments — high cut-risk filter.\n"
            "• Rebalances quarterly; turnover is low (~15 % p.a.) for a factor ETF.\n"
            "• Complements growth-heavy S&P 500 exposure; underweights tech, overweights financials.\n"
            "• Expense ratio 0.06 % — one of the cheapest dividend ETFs available."
        ),
    },
    "^DJI": {
        "display_name": "Dow Jones",
        "full_name": "Dow Jones Industrial Average",
        "description": (
            "Price-weighted index of 30 large, blue-chip US companies.  One of the oldest "
            "equity benchmarks; less diversified and more price-distorted than cap-weighted indexes."
        ),
        "expense_ratio_pct": None,
        "category": "US Large Cap Blend",
        "currency": "USD",
        "best_practices": (
            "• Use for historical context only; price weighting skews exposure unpredictably.\n"
            "• Accessible via DIA ETF (0.16 %).\n"
            "• Not recommended as a primary benchmark — S&P 500 is preferred for diversification."
        ),
    },
    "^IXIC": {
        "display_name": "Nasdaq",
        "full_name": "Nasdaq Composite Index",
        "description": (
            "Cap-weighted index of all ~3 000 stocks listed on the Nasdaq exchange.  "
            "Heavily tilted towards technology and growth companies; low dividend yield."
        ),
        "expense_ratio_pct": None,
        "category": "US Technology / Growth",
        "currency": "USD",
        "best_practices": (
            "• Useful benchmark when portfolio has significant tech/growth exposure.\n"
            "• Nasdaq-100 (QQQ, 0.20 %) is a more concentrated and investable variant.\n"
            "• High volatility; not a suitable benchmark for income-focused portfolios."
        ),
    },
}


def _default_db_path() -> Path:
    return DATA_DIR / "benchmark_cache.db"


class BenchmarkPriceStore:
    """Read/write benchmark price history and ETF metadata (Postgres + SQLite)."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _default_db_path()
        if not use_cloud_sql():
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_schema_sqlite()

    # ------------------------------------------------------------------
    # Internal connection helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _connect(self) -> Any:
        if use_cloud_sql():
            from db.connection import ensure_schema, get_connection
            from db.connection import DbConnection

            ensure_schema()
            with get_connection() as conn:
                yield DbConnection(conn, is_postgres=True)
        else:
            raw = sqlite3.connect(self._db_path)
            raw.row_factory = sqlite3.Row
            from db.connection import DbConnection

            wrapper = DbConnection(raw, is_postgres=False)
            try:
                yield wrapper
                wrapper.commit()
            finally:
                raw.close()

    def _ensure_schema_sqlite(self) -> None:
        raw = sqlite3.connect(self._db_path)
        raw.row_factory = sqlite3.Row
        try:
            raw.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_price_history (
                  symbol      TEXT NOT NULL,
                  price_date  TEXT NOT NULL,
                  close_usd   REAL NOT NULL,
                  fetched_at  TEXT NOT NULL DEFAULT (datetime('now')),
                  PRIMARY KEY (symbol, price_date)
                )
                """
            )
            raw.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_bph_symbol_date
                  ON benchmark_price_history (symbol, price_date DESC)
                """
            )
            raw.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_etf_info (
                  symbol             TEXT PRIMARY KEY,
                  display_name       TEXT NOT NULL,
                  full_name          TEXT NOT NULL,
                  description        TEXT,
                  expense_ratio_pct  REAL,
                  category           TEXT,
                  currency           TEXT NOT NULL DEFAULT 'USD',
                  best_practices     TEXT,
                  updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            raw.commit()
        finally:
            raw.close()

    # ------------------------------------------------------------------
    # Price history
    # ------------------------------------------------------------------

    def upsert_prices(self, symbol: str, prices: dict[date, float]) -> int:
        """Persist a {date: close_usd} mapping; returns the number of rows written."""
        if not prices:
            return 0
        sym = symbol.upper()
        rows = [(sym, d.isoformat(), float(v)) for d, v in prices.items() if v is not None]
        if not rows:
            return 0
        with self._connect() as conn:
            for sym_val, date_str, close in rows:
                conn.execute(
                    """
                    INSERT INTO benchmark_price_history (symbol, price_date, close_usd)
                    VALUES (?, ?, ?)
                    ON CONFLICT (symbol, price_date) DO UPDATE SET
                      close_usd  = EXCLUDED.close_usd,
                      fetched_at = EXCLUDED.fetched_at
                    """,
                    (sym_val, date_str, close),
                )
        return len(rows)

    def load_prices(self, symbol: str, start: date, end: date) -> dict[date, float]:
        """Return {date: close_usd} for *symbol* between *start* and *end* inclusive."""
        sym = symbol.upper()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT price_date, close_usd
                FROM benchmark_price_history
                WHERE symbol = ?
                  AND price_date >= ?
                  AND price_date <= ?
                ORDER BY price_date
                """,
                (sym, start.isoformat(), end.isoformat()),
            ).fetchall()
        result: dict[date, float] = {}
        for row in rows:
            pd_val = row["price_date"]
            if isinstance(pd_val, str):
                pd_val = date.fromisoformat(pd_val[:10])
            result[pd_val] = float(row["close_usd"])
        return result

    def covered_symbols(self) -> set[str]:
        """Return the set of symbols that have at least one stored price row."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM benchmark_price_history"
            ).fetchall()
        return {row["symbol"] for row in rows}

    def latest_date(self, symbol: str) -> date | None:
        """Most recent price_date for *symbol*, or None if not stored."""
        sym = symbol.upper()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT price_date FROM benchmark_price_history
                WHERE symbol = ?
                ORDER BY price_date DESC
                LIMIT 1
                """,
                (sym,),
            ).fetchone()
        if not row:
            return None
        val = row["price_date"]
        if isinstance(val, str):
            return date.fromisoformat(val[:10])
        return val

    def price_count(self, symbol: str) -> int:
        sym = symbol.upper()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM benchmark_price_history WHERE symbol = ?",
                (sym,),
            ).fetchone()
        return int(row["n"]) if row else 0

    # ------------------------------------------------------------------
    # ETF metadata / best practices
    # ------------------------------------------------------------------

    def get_etf_info(self, symbol: str) -> dict[str, Any] | None:
        sym = symbol.upper()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT symbol, display_name, full_name, description,
                       expense_ratio_pct, category, currency, best_practices
                FROM benchmark_etf_info
                WHERE symbol = ?
                """,
                (sym,),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def get_all_etf_info(self) -> dict[str, dict[str, Any]]:
        """Return {symbol: info_dict} for all stored ETF metadata rows."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT symbol, display_name, full_name, description,
                       expense_ratio_pct, category, currency, best_practices
                FROM benchmark_etf_info
                ORDER BY symbol
                """
            ).fetchall()
        return {row["symbol"]: dict(row) for row in rows}

    def upsert_etf_info(
        self,
        symbol: str,
        *,
        display_name: str,
        full_name: str,
        description: str | None = None,
        expense_ratio_pct: float | None = None,
        category: str | None = None,
        currency: str = "USD",
        best_practices: str | None = None,
    ) -> None:
        sym = symbol.upper()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO benchmark_etf_info (
                  symbol, display_name, full_name, description,
                  expense_ratio_pct, category, currency, best_practices
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (symbol) DO UPDATE SET
                  display_name      = EXCLUDED.display_name,
                  full_name         = EXCLUDED.full_name,
                  description       = EXCLUDED.description,
                  expense_ratio_pct = EXCLUDED.expense_ratio_pct,
                  category          = EXCLUDED.category,
                  currency          = EXCLUDED.currency,
                  best_practices    = EXCLUDED.best_practices,
                  updated_at        = EXCLUDED.updated_at
                """,
                (
                    sym,
                    display_name,
                    full_name,
                    description,
                    expense_ratio_pct,
                    category,
                    currency,
                    best_practices,
                ),
            )

    def seed_etf_info_if_empty(self) -> int:
        """Write BENCHMARK_ETF_SEED rows for any symbol not yet in the table."""
        written = 0
        existing = set(self.get_all_etf_info().keys())
        for symbol, meta in BENCHMARK_ETF_SEED.items():
            if symbol.upper() in existing:
                continue
            self.upsert_etf_info(symbol, **meta)
            written += 1
        return written
