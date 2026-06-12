"""
Auto-sync dividend cash received into persistent storage and monthly net totals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from data_ingestion.models import StockDocument
from services.portfolio_context import create_portfolio_context

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DividendSyncStats:
    holdings_scanned: int
    receipts_added: int
    symbols_updated: int
    monthly_periods: int


def _load_documents(symbols: list[str]) -> dict[str, StockDocument | None]:
    from services.shared_market_db import load_documents

    found = load_documents(symbols)
    return {symbol: found.get(symbol.upper()) for symbol in symbols}


def maybe_sync_received_dividends(
    *,
    force: bool = False,
    db_path: Path | None = None,
    symbols: list[str] | None = None,
) -> DividendSyncStats | None:
    """
    Sync paid dividends when stale or forced (skips work on every app rerun).

    Returns None when skipped.
    """
    if not force:
        try:
            from services.portfolio_ui_cache import should_sync_dividends_on_startup

            if not should_sync_dividends_on_startup():
                logger.debug("Dividend sync skipped (recently completed)")
                return None
        except Exception:  # noqa: S110
            pass
    stats = sync_received_dividends(db_path=db_path, symbols=symbols)
    try:
        from services.portfolio_ui_cache import mark_dividend_sync_completed

        mark_dividend_sync_completed()
    except Exception:  # noqa: S110
        pass
    return stats


def sync_received_dividends(
    *,
    db_path: Path | None = None,
    symbols: list[str] | None = None,
) -> DividendSyncStats:
    """
    Record paid dividends for current holdings and refresh lifetime/monthly totals.

    Dividends are derived from the shared market library, share counts from the
    purchase journal when present, otherwise from the add date forward only.
    """
    ctx = create_portfolio_context(db_path=db_path)
    holdings = ctx.portfolio.list_holdings()
    if symbols:
        wanted = {symbol.strip().upper() for symbol in symbols}
        holdings = [holding for holding in holdings if holding.symbol in wanted]
    if not holdings:
        return DividendSyncStats(0, 0, 0, 0)

    documents = _load_documents([holding.symbol for holding in holdings])
    today = date.today()
    added = 0
    updated_symbols = 0

    for holding in holdings:
        document = documents.get(holding.symbol)
        rows = ctx.detail.dividend_history(
            holding.symbol,
            document,
            current_shares=holding.shares,
            tracking_since=holding.dividend_tracking_since,
            prefer_stored=False,
        )
        received = [row for row in rows if row.pay_date <= today]
        symbol_added = 0
        for row in received:
            if ctx.receipts.upsert_receipt(
                holding.symbol,
                ex_date=row.ex_date,
                pay_date=row.pay_date,
                per_share_usd=row.per_share_usd,
                shares_held=row.shares_held,
                gross_usd=row.cash_usd,
            ):
                added += 1
                symbol_added += 1

        total = ctx.receipts.total_for_symbol(holding.symbol)
        ctx.portfolio.set_dividends_paid(holding.symbol, total)
        if symbol_added or total > 0:
            updated_symbols += 1

    monthly_periods = _sync_monthly_net_from_receipts(ctx)
    logger.info(
        "Dividend sync: holdings=%d receipts_added=%d symbols=%d months=%d",
        len(holdings),
        added,
        updated_symbols,
        monthly_periods,
    )
    return DividendSyncStats(
        holdings_scanned=len(holdings),
        receipts_added=added,
        symbols_updated=updated_symbols,
        monthly_periods=monthly_periods,
    )


def _sync_monthly_net_from_receipts(ctx: Any) -> int:
    from data_ingestion.dividend_income_store import dividend_tax_rate

    totals = ctx.receipts.monthly_gross_totals()
    if not totals:
        return 0

    with ctx.dividends._connect() as connection:
        for (year, month), gross in totals.items():
            rate = dividend_tax_rate(year)
            net = round(gross * (1.0 - rate), 2)
            period_key = f"{year:04d}-{month:02d}"
            if connection.is_postgres:
                connection.execute(
                    """
                    INSERT INTO net_dividends (user_id, period_key, year, month, net_usd)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (user_id, period_key) DO UPDATE SET net_usd = excluded.net_usd
                    """,
                    (connection.user_id, period_key, year, month, net),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO net_dividends (period_key, year, month, net_usd)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(period_key) DO UPDATE SET net_usd = excluded.net_usd
                    """,
                    (period_key, year, month, net),
                )
    return len(totals)
