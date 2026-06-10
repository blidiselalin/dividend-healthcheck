"""
Database-first helpers for Dividends Don't Lie yield-channel charts.

Charts are built from the shared market library: ``stock_documents`` plus
normalized ``stock_price_history`` / ``stock_dividend_history`` when Postgres
is configured. Live API fallbacks are not used on the analysis UI path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

from config import MIN_YIELD_DIVIDEND_PAYMENTS, MIN_YIELD_PRICE_POINTS

if TYPE_CHECKING:
    from data_ingestion.models import StockDocument

# Minimum distinct price days to attempt a chart (adaptive attempts go lower).
CHART_MIN_UNIQUE_PRICE_DAYS = 52
CHART_MIN_DIVIDEND_PAYMENTS = 4


@dataclass(frozen=True)
class YieldChannelReadiness:
    """History available for one symbol (tables + merged library document)."""

    symbol: str
    document_found: bool
    unique_price_days: int
    dividend_payments: int
    table_price_rows: int
    table_dividend_rows: int
    prices_trustworthy: bool
    chart_ready: bool

    @property
    def needs_table_sync(self) -> bool:
        """JSONB/library has prices but normalized tables are empty or lagging."""
        if self.unique_price_days < CHART_MIN_UNIQUE_PRICE_DAYS:
            return False
        return self.table_price_rows < self.unique_price_days // 2

    @property
    def needs_history_backfill(self) -> bool:
        return (
            not self.prices_trustworthy
            or self.dividend_payments < CHART_MIN_DIVIDEND_PAYMENTS
            or self.unique_price_days < CHART_MIN_UNIQUE_PRICE_DAYS
        )


def assess_yield_channel_readiness(
    symbol: str,
    document: Optional["StockDocument"] = None,
) -> YieldChannelReadiness:
    """Summarize price/dividend coverage from DB tables and the library document."""
    from utils.library_document import resolve_library_document
    from utils.yfinance_history import library_prices_trustworthy, unique_price_dates

    sym = (symbol or "").strip().upper()
    doc = resolve_library_document(sym, document)
    table_prices = 0
    table_divs = 0

    try:
        from db.connection import use_cloud_sql

        if use_cloud_sql():
            from db.postgres_market_history_store import PostgresMarketHistoryStore

            counts = PostgresMarketHistoryStore().symbol_history_counts(sym)
            table_prices = int(counts.get("price_points") or 0)
            table_divs = int(counts.get("dividend_payments") or 0)
    except Exception:
        pass

    if doc is None:
        return YieldChannelReadiness(
            symbol=sym,
            document_found=False,
            unique_price_days=0,
            dividend_payments=0,
            table_price_rows=table_prices,
            table_dividend_rows=table_divs,
            prices_trustworthy=False,
            chart_ready=False,
        )

    unique_prices = unique_price_dates(doc)
    div_count = len(doc.dividend_history or [])
    trustworthy = library_prices_trustworthy(doc, min_unique=CHART_MIN_UNIQUE_PRICE_DAYS)
    chart_ready = trustworthy and div_count >= CHART_MIN_DIVIDEND_PAYMENTS

    return YieldChannelReadiness(
        symbol=sym,
        document_found=True,
        unique_price_days=unique_prices,
        dividend_payments=div_count,
        table_price_rows=table_prices,
        table_dividend_rows=table_divs,
        prices_trustworthy=trustworthy,
        chart_ready=chart_ready,
    )


def format_history_coverage_summary(readiness: YieldChannelReadiness) -> str:
    """One-line stats shown when a chart cannot be built."""
    return (
        f"`stock_price_history`: **{readiness.table_price_rows:,}** rows · "
        f"**{readiness.unique_price_days:,}** distinct price days in library · "
        f"`stock_dividend_history`: **{readiness.table_dividend_rows:,}** rows · "
        f"**{readiness.dividend_payments:,}** dividend payments in library "
        f"(target ≥ {CHART_MIN_UNIQUE_PRICE_DAYS} price days and "
        f"≥ {CHART_MIN_DIVIDEND_PAYMENTS} payments; full library goal "
        f"{MIN_YIELD_PRICE_POINTS} price days)."
    )


def format_history_reload_guidance(readiness: YieldChannelReadiness) -> str:
    """Actionable steps to populate historical tables from admin / ingest."""
    steps: List[str] = []
    if not readiness.document_found:
        steps.append(
            "Symbol is missing from **stock_documents** — run S&P ingest or add the holding to the library first."
        )
    elif readiness.needs_history_backfill:
        if readiness.dividend_payments >= CHART_MIN_DIVIDEND_PAYMENTS and readiness.unique_price_days == 0:
            steps.append(
                "Dividend history is present but **price history is missing** — run "
                "**Backfill thin history** in the admin console (or "
                "`python ingest_data.py --backfill-history --backfill-limit 120`) "
                "to fetch OHLCV into the library, then **Sync history tables**."
            )
        else:
            steps.append(
                "Use **Backfill thin history** in the admin console (or "
                "`python ingest_data.py --backfill-history --backfill-limit 120`) "
                "to fetch price and dividend series into the library."
            )
    if readiness.needs_table_sync or readiness.table_price_rows > 0:
        steps.append(
            "Use **Sync history tables** in the admin console (or "
            "`python ingest_data.py --sync-history-tables --sync-history-limit 500`) "
            "to copy library JSONB into `stock_price_history` and `stock_dividend_history`."
        )
    if not steps:
        steps.append(
            "Reload the portfolio, then run **Backfill thin history** followed by "
            "**Sync history tables** if counts stay below the target."
        )
    return " ".join(steps)
