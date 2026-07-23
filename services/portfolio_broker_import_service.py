"""
Import Interactive Brokers Activity Statement CSV into portfolio stores.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path

from services.ibkr_activity_parser import (
    IBKRActivityStatement,
    IBKRStatementMeta,
    ImportIssue,
    build_monthly_deposits,
    deposit_months_with_inflows,
    has_blocking_errors,
    parse_activity_statement_csv,
    statement_deposit_period,
    statement_symbol_scope,
    validate_statement,
)
from services.portfolio_clear_service import clear_user_portfolio
from services.portfolio_context import create_portfolio_context

logger = logging.getLogger(__name__)

ImportProgressCallback = Callable[[str, float], None]


def _report(progress: ImportProgressCallback | None, message: str, fraction: float) -> None:
    if progress is not None:
        progress(message, fraction)


class ImportMode(str, Enum):
    MERGE = "merge"
    REPLACE = "replace"


@dataclass(frozen=True)
class ImportPreview:
    meta: IBKRStatementMeta
    position_count: int
    trade_count: int
    dividend_count: int
    deposit_month_count: int
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
    deposits_imported: int
    symbols_touched: list[str]
    issues: list[ImportIssue]
    cleared: int | None = None

    @property
    def wrote_data(self) -> bool:
        return (
            self.holdings_upserted > 0
            or self.trades_imported > 0
            or self.dividends_imported > 0
            or self.deposits_imported > 0
        )


def preview_import(content: str | bytes) -> ImportPreview:
    statement = parse_activity_statement_csv(content)
    issues = validate_statement(statement)
    symbols = sorted(statement_symbol_scope(statement))
    monthly_deposits = build_monthly_deposits(statement)
    return ImportPreview(
        meta=statement.meta,
        position_count=len(statement.open_positions),
        trade_count=len(statement.trades),
        dividend_count=len(statement.dividends),
        deposit_month_count=deposit_months_with_inflows(monthly_deposits),
        symbols=symbols,
        issues=issues,
        forex_trades_skipped=statement.forex_trades_skipped,
    )


def apply_import(  # noqa: C901
    content: str | bytes,
    *,
    mode: ImportMode,
    db_path: Path | None = None,
    progress: ImportProgressCallback | None = None,
) -> ImportApplyResult:
    _report(progress, "Parsing activity statement…", 0.05)
    statement = parse_activity_statement_csv(content)
    _report(progress, "Validating statement…", 0.10)
    issues = validate_statement(statement)
    if has_blocking_errors(issues):
        return ImportApplyResult(
            mode=mode,
            holdings_upserted=0,
            trades_imported=0,
            dividends_imported=0,
            deposits_imported=0,
            symbols_touched=[],
            issues=issues,
        )

    cleared: int | None = None
    if mode == ImportMode.REPLACE:
        _report(progress, "Clearing existing portfolio data…", 0.15)
        clear_result = clear_user_portfolio(db_path=db_path)
        cleared = clear_result.total_rows

    _report(progress, "Opening portfolio stores…", 0.18)
    ctx = create_portfolio_context(db_path=db_path)
    open_symbols = {pos.symbol for pos in statement.open_positions}
    scope_symbols = statement_symbol_scope(statement)

    commission_by_symbol = _commission_totals(statement)
    holdings_upserted = 0
    trades_imported = 0
    dividends_imported = 0
    deposits_imported = 0

    positions = statement.open_positions
    _report(progress, "Importing open positions…", 0.25)
    for index, position in enumerate(positions, start=1):
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
        if positions:
            fraction = 0.25 + (0.20 * index / len(positions))
            _report(progress, f"Importing positions ({index}/{len(positions)})…", fraction)

    if mode == ImportMode.MERGE:
        for symbol in sorted(scope_symbols - open_symbols):
            ctx.portfolio.drop_holding(symbol)

    trades = statement.trades
    _report(progress, "Importing stock trades…", 0.48)
    for index, trade in enumerate(trades, start=1):
        if mode == ImportMode.MERGE and trade.symbol not in scope_symbols:
            continue
        if mode == ImportMode.MERGE:
            outcome = ctx.journal.sync_purchase(
                trade.symbol,
                trade.trade_date,
                trade.price_usd,
                shares=trade.quantity,
                commission_usd=trade.commission_usd,
                side=trade.side,
                source="ibkr",
            )
            if outcome in {"added", "updated"}:
                trades_imported += 1
        else:
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
        if trades:
            fraction = 0.48 + (0.15 * index / len(trades))
            _report(progress, f"Importing trades ({index}/{len(trades)})…", fraction)

    _sync_opening_balance_lots(ctx, statement)

    dividends = statement.dividends
    _report(progress, "Importing dividends…", 0.65)
    for index, dividend in enumerate(dividends, start=1):
        if mode == ImportMode.MERGE and dividend.symbol not in scope_symbols:
            continue
        if dividend.gross_usd == 0:
            continue
        shares_held = (
            round(abs(dividend.gross_usd) / dividend.per_share_usd, 4)
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
        if dividends:
            fraction = 0.65 + (0.10 * index / len(dividends))
            _report(progress, f"Importing dividends ({index}/{len(dividends)})…", fraction)

    _report(progress, "Updating dividend totals on holdings…", 0.78)
    for symbol in open_symbols:
        total = ctx.receipts.total_for_symbol(symbol)
        ctx.portfolio.set_dividends_paid(symbol, total)

    monthly_deposits = build_monthly_deposits(
        statement,
        include_zero_months=(mode == ImportMode.REPLACE),
    )
    if mode == ImportMode.MERGE:
        issues.extend(_deposit_overlap_issues(ctx, monthly_deposits))
    _report(progress, "Importing monthly deposits…", 0.82)
    if monthly_deposits:
        for index, month_deposit in enumerate(monthly_deposits, start=1):
            if mode == ImportMode.MERGE:
                outcome = ctx.deposits.merge_deposit(
                    year=month_deposit.year,
                    month=month_deposit.month,
                    label=month_deposit.label,
                    deposit_eur=month_deposit.deposit_eur,
                    deposit_usd=month_deposit.deposit_usd,
                    portfolio_eur=month_deposit.portfolio_eur,
                    native_eur=month_deposit.native_eur,
                    native_usd=month_deposit.native_usd,
                )
                if outcome in {"added", "updated"}:
                    deposits_imported += 1
            else:
                ctx.deposits.upsert_deposit(
                    year=month_deposit.year,
                    month=month_deposit.month,
                    label=month_deposit.label,
                    deposit_eur=month_deposit.deposit_eur,
                    deposit_usd=month_deposit.deposit_usd,
                    portfolio_eur=month_deposit.portfolio_eur,
                )
                deposits_imported += 1
            fraction = 0.82 + (0.08 * index / len(monthly_deposits))
            _report(
                progress,
                f"Importing deposits ({index}/{len(monthly_deposits)})…",
                fraction,
            )
        ctx.deposits.resequence_sort_order()

    _report(progress, "Syncing monthly dividend totals…", 0.92)
    _sync_monthly_net_from_receipts(ctx)
    from services.portfolio_open_holdings import reconcile_closed_holdings

    reconcile_closed_holdings(db_path=db_path)
    issues.extend(_holdings_journal_consistency_issues(ctx, open_symbols))
    _report(progress, "Finalizing import…", 0.96)
    _finalize_broker_import(ctx, db_path=db_path)
    _report(progress, "Import complete", 1.0)

    logger.info(
        "IBKR import (%s): holdings=%d trades=%d dividends=%d deposits=%d symbols=%d",
        mode.value,
        holdings_upserted,
        trades_imported,
        dividends_imported,
        deposits_imported,
        len(open_symbols),
    )
    return ImportApplyResult(
        mode=mode,
        holdings_upserted=holdings_upserted,
        trades_imported=trades_imported,
        dividends_imported=dividends_imported,
        deposits_imported=deposits_imported,
        symbols_touched=sorted(scope_symbols),
        issues=issues,
        cleared=cleared,
    )


def _deposit_overlap_issues(
    ctx: object,
    monthly_deposits: list[object],
) -> list[ImportIssue]:
    """Warn when merge would touch deposit months that already exist on file."""
    from services.ibkr_activity_parser import ImportIssue, ImportIssueLevel

    deposits = getattr(ctx, "deposits", None)
    if deposits is None or not monthly_deposits:
        return []

    incoming_keys = {
        (item.year, item.month)
        for item in monthly_deposits
        if item.deposit_eur > 0.01 or item.deposit_usd > 0.01
    }
    if not incoming_keys:
        return []

    existing_keys = {
        (item.period.year, item.period.month)
        for item in deposits.list_deposits()
        if item.deposit_eur > 0.01 or item.deposit_usd > 0.01
    }
    overlap = incoming_keys & existing_keys
    if not overlap:
        return []

    months = ", ".join(f"{year}-{month:02d}" for year, month in sorted(overlap))
    years = sorted({year for year, _month in overlap})
    year_hint = (
        f" For {years[0]}, import statements oldest → newest; "
        "overlapping months keep the larger or combined total."
        if len(years) == 1
        else " Import statements oldest → newest per year."
    )
    return [
        ImportIssue(
            ImportIssueLevel.INFO,
            (
                f"Deposit months already on file ({months}) will be merged — not duplicated."
                f"{year_hint}"
            ),
            section="Deposits & Withdrawals",
        )
    ]


def _journal_net_shares(journal: object, symbol: str) -> float:
    purchases = [
        row
        for row in journal.list_purchases(portfolio_only=False)
        if row.symbol == symbol and row.source != "ibkr-open"
    ]
    buy = sum(float(row.shares or 0.0) for row in purchases if row.side != "sell")
    sell = sum(float(row.shares or 0.0) for row in purchases if row.side == "sell")
    return round(buy - sell, 4)


def _sync_opening_balance_lots(ctx: object, statement: IBKRActivityStatement) -> None:
    """
    Add pre-period share balance when IBKR open positions exceed net imported trades.

    Activity statements list in-period trades only; the open-position snapshot can
    include shares bought before the statement window. Stale ``ibkr-open`` rows for
    symbols touched by this statement are cleared first so merge re-imports do not
    keep opening lots from an earlier file.
    """
    journal = getattr(ctx, "journal", None)
    if journal is None:
        return

    scope_symbols = statement_symbol_scope(statement)
    for symbol in scope_symbols:
        journal.delete_for_symbol(symbol, source="ibkr-open")

    if not statement.open_positions:
        return

    period = statement_deposit_period(statement)
    lot_date = period[0] if period else date.today()

    for position in statement.open_positions:
        symbol = position.symbol
        net = _journal_net_shares(journal, symbol)
        diff = round(position.shares - net, 4)
        if diff <= 0.01:
            continue
        journal.add_purchase(
            symbol,
            lot_date,
            position.cost_price,
            shares=diff,
            commission_usd=0.0,
            side="buy",
            source="ibkr-open",
        )


def _holdings_journal_consistency_issues(ctx: object, open_symbols: set[str]) -> list[ImportIssue]:
    """Warn when IBKR open positions disagree with net shares from imported trades."""
    from services.ibkr_activity_parser import ImportIssue, ImportIssueLevel

    portfolio = getattr(ctx, "portfolio", None)
    journal_service = getattr(ctx, "journal_service", None)
    if portfolio is None or journal_service is None or not open_symbols:
        return []

    net_by_symbol: dict[str, float] = {}
    for symbol in open_symbols:
        net_by_symbol[symbol] = _journal_net_shares(journal_service.journal, symbol)

    issues: list[ImportIssue] = []
    for symbol in sorted(open_symbols):
        holding = next((h for h in portfolio.list_holdings() if h.symbol == symbol), None)
        if holding is None:
            continue
        net = net_by_symbol.get(symbol, 0.0)
        if abs(holding.shares - net) > 0.05:
            issues.append(
                ImportIssue(
                    ImportIssueLevel.WARNING,
                    (
                        f"{symbol}: open position shows {holding.shares:g} shares but "
                        f"imported trades net to {net:g} — evolution valuation uses trades."
                    ),
                    section="Open Positions",
                )
            )
    return issues


def _commission_totals(statement: IBKRActivityStatement) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for trade in statement.trades:
        totals[trade.symbol] += trade.commission_usd
    return {symbol: round(amount, 2) for symbol, amount in totals.items()}


def _sync_monthly_net_from_receipts(ctx: object) -> int:
    from services.portfolio_dividend_sync_service import _sync_monthly_net_from_receipts

    return _sync_monthly_net_from_receipts(ctx)


def _finalize_broker_import(ctx: object, *, db_path: Path | None) -> None:
    """Refresh derived stores after broker import without wiping the UI snapshot."""
    try:
        from services.portfolio_session import invalidate_holdings_cache

        invalidate_holdings_cache()
    except ImportError:
        pass

    try:
        from services.portfolio_vector_sync import sync_portfolio_to_vector_db

        sync_portfolio_to_vector_db(enrich_missing=False, db_path=db_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Portfolio vector sync after IBKR import failed: %s", exc)

    try:
        portfolio = getattr(ctx, "portfolio", None)
        if portfolio is not None and hasattr(portfolio, "list_holdings"):
            logger.debug(
                "IBKR import finalized with %d holdings in database",
                len(portfolio.list_holdings()),
            )
    except Exception:  # noqa: S110
        pass
