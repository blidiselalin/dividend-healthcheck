"""
Import Interactive Brokers Activity Statement CSV into portfolio stores.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from services.ibkr_activity_parser import (
    IBKRActivityStatement,
    IBKRStatementMeta,
    ImportIssue,
    has_blocking_errors,
    parse_activity_statement_csv,
    validate_statement,
)
from services.portfolio_clear_service import clear_user_portfolio
from services.portfolio_context import create_portfolio_context

logger = logging.getLogger(__name__)


class ImportMode(str, Enum):
    MERGE = "merge"
    REPLACE = "replace"


@dataclass(frozen=True)
class ImportPreview:
    meta: IBKRStatementMeta
    position_count: int
    trade_count: int
    dividend_count: int
    symbols: list[str]
    issues: list[ImportIssue]
    forex_trades_skipped: int = 0

    @property
    def blocking(self) -> bool:
        return has_blocking_errors(self.issues)


@dataclass(frozen=True)
class ImportApplyResult:
    mode: ImportMode
    holdings_upserted: int
    trades_imported: int
    dividends_imported: int
    symbols_touched: list[str]
    issues: list[ImportIssue]
    cleared: int | None = None


def preview_import(content: str | bytes) -> ImportPreview:
    statement = parse_activity_statement_csv(content)
    issues = validate_statement(statement)
    symbols = sorted({pos.symbol for pos in statement.open_positions})
    return ImportPreview(
        meta=statement.meta,
        position_count=len(statement.open_positions),
        trade_count=len(statement.trades),
        dividend_count=len(statement.dividends),
        symbols=symbols,
        issues=issues,
        forex_trades_skipped=statement.forex_trades_skipped,
    )


def apply_import(
    content: str | bytes,
    *,
    mode: ImportMode,
    db_path: Path | None = None,
) -> ImportApplyResult:
    statement = parse_activity_statement_csv(content)
    issues = validate_statement(statement)
    if has_blocking_errors(issues):
        return ImportApplyResult(
            mode=mode,
            holdings_upserted=0,
            trades_imported=0,
            dividends_imported=0,
            symbols_touched=[],
            issues=issues,
        )

    cleared: int | None = None
    if mode == ImportMode.REPLACE:
        clear_result = clear_user_portfolio(db_path=db_path)
        cleared = clear_result.total_rows

    ctx = create_portfolio_context(db_path=db_path)
    symbols = sorted({pos.symbol for pos in statement.open_positions})

    if mode == ImportMode.MERGE:
        for symbol in symbols:
            ctx.journal.delete_for_symbol(symbol, source="ibkr")
            ctx.receipts.delete_for_symbol(symbol, source="ibkr")

    commission_by_symbol = _commission_totals(statement)
    holdings_upserted = 0
    trades_imported = 0
    dividends_imported = 0

    for position in statement.open_positions:
        symbol = position.symbol
        existing = next(
            (h for h in ctx.portfolio.list_holdings() if h.symbol == symbol),
            None,
        )
        ctx.portfolio.upsert_holding(
            symbol,
            shares=position.shares,
            avg_cost_per_share=position.cost_price,
            commission=commission_by_symbol.get(symbol, 0.0),
            dividends_paid=0.0
            if mode == ImportMode.REPLACE
            else (existing.dividends_paid if existing else 0.0),
        )
        holdings_upserted += 1

    for trade in statement.trades:
        if mode == ImportMode.MERGE and trade.symbol not in symbols:
            continue
        ctx.journal.add_purchase(
            trade.symbol,
            trade.trade_date,
            trade.price_usd,
            shares=trade.quantity,
            commission_usd=trade.commission_usd,
            side=trade.side,
            source="ibkr",
        )
        trades_imported += 1

    for dividend in statement.dividends:
        shares_held = (
            round(dividend.gross_usd / dividend.per_share_usd, 4)
            if dividend.per_share_usd > 0
            else 0.0
        )
        outcome = ctx.receipts.sync_receipt(
            dividend.symbol,
            ex_date=dividend.pay_date,
            pay_date=dividend.pay_date,
            per_share_usd=dividend.per_share_usd,
            shares_held=shares_held,
            gross_usd=dividend.gross_usd,
            source="ibkr",
        )
        if outcome in {"added", "updated"}:
            dividends_imported += 1

    for symbol in symbols:
        total = ctx.receipts.total_for_symbol(symbol)
        ctx.portfolio.set_dividends_paid(symbol, total)

    _sync_monthly_net_from_receipts(ctx)

    logger.info(
        "IBKR import (%s): holdings=%d trades=%d dividends=%d symbols=%d",
        mode.value,
        holdings_upserted,
        trades_imported,
        dividends_imported,
        len(symbols),
    )
    return ImportApplyResult(
        mode=mode,
        holdings_upserted=holdings_upserted,
        trades_imported=trades_imported,
        dividends_imported=dividends_imported,
        symbols_touched=symbols,
        issues=issues,
        cleared=cleared,
    )


def _commission_totals(statement: IBKRActivityStatement) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for trade in statement.trades:
        totals[trade.symbol] += trade.commission_usd
    return {symbol: round(amount, 2) for symbol, amount in totals.items()}


def _sync_monthly_net_from_receipts(ctx: object) -> int:
    from services.portfolio_dividend_sync_service import _sync_monthly_net_from_receipts

    return _sync_monthly_net_from_receipts(ctx)
