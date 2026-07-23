"""
Validation, normalization, and reconciliation layers around broker import.

Wraps the existing IBKR parser/importer without replacing it:

    Validate → Normalize → Existing importer → Fill gaps → Reconcile
"""

from __future__ import annotations

import calendar
import hashlib
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from services.ibkr_activity_parser import (
    IBKRActivityStatement,
    ImportIssue,
    ImportIssueLevel,
    build_monthly_deposits,
    parse_statement_period,
)
from utils.import_money import round_money, round_rate, round_shares

if TYPE_CHECKING:
    from services.portfolio_context import PortfolioContext

_MAX_SINGLE_DEPOSIT_EUR = 250_000.0
_MAX_TRADE_NOTIONAL_USD = 50_000_000.0
_MAX_MOM_JUMP_PCT = 75.0


def content_fingerprint(content: str | bytes) -> str:
    """Stable SHA-256 fingerprint for duplicate file detection."""
    payload = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(payload).hexdigest()


def normalize_statement(statement: IBKRActivityStatement) -> IBKRActivityStatement:
    """Round monetary fields to currency precision using Decimal."""
    statement.open_positions = [
        replace(
            position,
            shares=round_shares(position.shares),
            cost_price=round_money(position.cost_price),
            cost_basis=round_money(position.cost_basis),
        )
        for position in statement.open_positions
    ]
    statement.trades = [
        replace(
            trade,
            quantity=round_shares(trade.quantity),
            price_usd=round_money(trade.price_usd),
            commission_usd=round_money(trade.commission_usd),
        )
        for trade in statement.trades
    ]
    statement.dividends = [
        replace(
            dividend,
            per_share_usd=round_rate(dividend.per_share_usd),
            gross_usd=round_money(dividend.gross_usd),
        )
        for dividend in statement.dividends
    ]
    statement.cash_transfers = [
        replace(
            transfer,
            amount=round_money(transfer.amount),
        )
        for transfer in statement.cash_transfers
    ]
    if statement.nav_total is not None:
        statement.nav_total = round_money(statement.nav_total)
    if statement.deposits_fx_eur_per_usd is not None:
        statement.deposits_fx_eur_per_usd = round_rate(statement.deposits_fx_eur_per_usd)
    statement.fx_rates = {
        currency: round_rate(rate) for currency, rate in statement.fx_rates.items()
    }
    return statement


def validate_import_input(
    content: str | bytes,
    statement: IBKRActivityStatement,
) -> list[ImportIssue]:
    """Pre-import checks for mandatory metadata and malformed payloads."""
    issues: list[ImportIssue] = []

    if not str(content).strip():
        issues.append(
            ImportIssue(ImportIssueLevel.ERROR, "Uploaded file is empty.", section="Upload")
        )
        return issues

    if not statement.meta.account:
        issues.append(
            ImportIssue(
                ImportIssueLevel.WARNING,
                "Missing account number in Account Information.",
                section="Account Information",
            )
        )

    period = parse_statement_period(statement.meta.period or "")
    if statement.meta.period and period is None:
        issues.append(
            ImportIssue(
                ImportIssueLevel.WARNING,
                f"Could not parse statement period: {statement.meta.period!r}.",
                section="Statement",
            )
        )

    for trade in statement.trades:
        if trade.trade_date > date.today():
            issues.append(
                ImportIssue(
                    ImportIssueLevel.WARNING,
                    f"{trade.symbol}: trade date {trade.trade_date} is in the future.",
                    section="Trades",
                )
            )
            break

    return issues


def detect_in_statement_duplicates(statement: IBKRActivityStatement) -> list[ImportIssue]:
    """Flag duplicate event fingerprints inside one CSV export."""
    issues: list[ImportIssue] = []

    trade_keys: dict[tuple[object, ...], int] = {}
    for trade in statement.trades:
        key = (
            trade.symbol,
            trade.trade_date,
            trade.side,
            round_shares(trade.quantity),
            round_money(trade.price_usd),
            round_money(trade.commission_usd),
        )
        trade_keys[key] = trade_keys.get(key, 0) + 1
    dup_trades = sum(count - 1 for count in trade_keys.values() if count > 1)
    if dup_trades:
        issues.append(
            ImportIssue(
                ImportIssueLevel.WARNING,
                f"Found {dup_trades} duplicate trade row(s) in this file — only one will import.",
                section="Trades",
            )
        )

    dividend_keys: dict[tuple[object, ...], int] = {}
    for dividend in statement.dividends:
        key = (
            dividend.symbol,
            dividend.pay_date,
            round_rate(dividend.per_share_usd),
            round_money(dividend.gross_usd),
        )
        dividend_keys[key] = dividend_keys.get(key, 0) + 1
    dup_divs = sum(count - 1 for count in dividend_keys.values() if count > 1)
    if dup_divs:
        issues.append(
            ImportIssue(
                ImportIssueLevel.WARNING,
                f"Found {dup_divs} duplicate dividend row(s) in this file.",
                section="Dividends",
            )
        )

    return issues


def validate_extreme_values(statement: IBKRActivityStatement) -> list[ImportIssue]:
    """Flag unrealistic deposits, trade sizes, or NAV totals."""
    issues: list[ImportIssue] = []
    eur_per_usd = statement.deposits_fx_eur_per_usd or statement.fx_rates.get("EUR")

    for transfer in statement.cash_transfers:
        if transfer.amount <= 0:
            continue
        amount_eur = transfer.amount
        if transfer.currency == "USD" and eur_per_usd and eur_per_usd > 0:
            amount_eur = round_money(transfer.amount * eur_per_usd)
        if amount_eur > _MAX_SINGLE_DEPOSIT_EUR:
            issues.append(
                ImportIssue(
                    ImportIssueLevel.WARNING,
                    (
                        f"Unusually large deposit ({transfer.currency} {transfer.amount:,.2f} "
                        f"on {transfer.transfer_date}) — verify before importing."
                    ),
                    section="Deposits & Withdrawals",
                )
            )

    for trade in statement.trades:
        notional = round_money(trade.quantity * trade.price_usd)
        if notional > _MAX_TRADE_NOTIONAL_USD:
            issues.append(
                ImportIssue(
                    ImportIssueLevel.WARNING,
                    (
                        f"{trade.symbol}: trade notional ${notional:,.0f} on "
                        f"{trade.trade_date} looks unusually large."
                    ),
                    section="Trades",
                )
            )

    nav_eur = statement.nav_total
    if nav_eur is not None and eur_per_usd and eur_per_usd > 0:
        nav_eur = round_money(nav_eur * eur_per_usd)
    if nav_eur is not None and nav_eur > 100_000_000:
        issues.append(
            ImportIssue(
                ImportIssueLevel.WARNING,
                f"Statement NAV ({nav_eur:,.0f} EUR) is unusually high — verify totals.",
                section="Net Asset Value",
            )
        )

    return issues


def _month_label(year: int, month: int) -> str:
    return f"{calendar.month_name[month]} {year}"


def _iter_calendar_months(start: date, end: date) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def fill_missing_deposit_months(
    ctx: PortfolioContext,
    *,
    range_start: date | None = None,
    range_end: date | None = None,
) -> tuple[int, list[ImportIssue]]:
    """
    Insert zero-deposit placeholder rows for calendar gaps in stored history.

    When ``range_start`` / ``range_end`` are set, only gaps inside that window
    are filled (typically the imported statement period on full replace).

    Missing portfolio values remain 0 (null-equivalent in charts).
    """
    issues: list[ImportIssue] = []
    deposits = ctx.deposits.list_deposits()
    if len(deposits) < 2:
        return 0, issues

    existing = {(item.period.year, item.period.month) for item in deposits}
    start = range_start or min(item.period for item in deposits)
    end = range_end or max(item.period for item in deposits)
    missing = [
        (year, month)
        for year, month in _iter_calendar_months(start, end)
        if (year, month) not in existing
    ]
    added = 0
    for year, month in missing:
        ctx.deposits.upsert_deposit(
            year=year,
            month=month,
            label=_month_label(year, month),
            deposit_eur=0.0,
            deposit_usd=0.0,
            portfolio_eur=0.0,
        )
        added += 1

    if added:
        ctx.deposits.resequence_sort_order()
        months = ", ".join(f"{year}-{month:02d}" for year, month in missing[:6])
        suffix = "…" if len(missing) > 6 else ""
        issues.append(
            ImportIssue(
                ImportIssueLevel.INFO,
                f"Filled {added} missing calendar month(s) with zero deposits ({months}{suffix}).",
                section="Deposits & Withdrawals",
            )
        )
    return added, issues


def run_post_import_checks(
    ctx: PortfolioContext,
    statement: IBKRActivityStatement,
) -> list[ImportIssue]:
    """Reconcile imported data against holdings and monthly evolution."""
    issues: list[ImportIssue] = []
    deposits = ctx.deposits.list_deposits()
    if not deposits:
        return issues

    period = parse_statement_period(statement.meta.period or "")
    if period:
        expected_months = set(_iter_calendar_months(period[0], period[1]))
        incoming = build_monthly_deposits(statement, include_zero_months=True)
        incoming_keys = {(item.year, item.month) for item in incoming}
        missing_in_statement = sorted(expected_months - incoming_keys)
        if missing_in_statement:
            issues.append(
                ImportIssue(
                    ImportIssueLevel.INFO,
                    (
                        f"Statement period spans {len(expected_months)} months; "
                        f"{len(missing_in_statement)} had no deposit or NAV rows in the export."
                    ),
                    section="Statement",
                )
            )

    stored_keys = {(item.period.year, item.period.month) for item in deposits}
    start = min(item.period for item in deposits)
    end = max(item.period for item in deposits)
    timeline_gaps = [key for key in _iter_calendar_months(start, end) if key not in stored_keys]
    if timeline_gaps:
        issues.append(
            ImportIssue(
                ImportIssueLevel.WARNING,
                (
                    f"Portfolio timeline still has {len(timeline_gaps)} calendar gap(s) "
                    "between earliest and latest deposit month."
                ),
                section="Deposits & Withdrawals",
            )
        )

    portfolio_rows = [item for item in deposits if item.portfolio_eur > 0]
    prev_value: float | None = None
    for item in sorted(portfolio_rows, key=lambda row: row.period):
        if prev_value is not None and prev_value > 0:
            jump_pct = abs((item.portfolio_eur - prev_value) / prev_value * 100)
            if jump_pct > _MAX_MOM_JUMP_PCT:
                issues.append(
                    ImportIssue(
                        ImportIssueLevel.WARNING,
                        (
                            f"{item.label}: portfolio value changed {jump_pct:.0f}% "
                            f"({prev_value:,.0f} → {item.portfolio_eur:,.0f} EUR) — review import."
                        ),
                        section="Deposits & Withdrawals",
                    )
                )
        prev_value = item.portfolio_eur

    open_symbols = {pos.symbol for pos in statement.open_positions}
    if open_symbols:
        holdings = {h.symbol: h for h in ctx.portfolio.list_holdings()}
        for symbol in sorted(open_symbols):
            holding = holdings.get(symbol)
            position = next(p for p in statement.open_positions if p.symbol == symbol)
            if holding is None:
                continue
            if abs(holding.shares - position.shares) > 0.05:
                issues.append(
                    ImportIssue(
                        ImportIssueLevel.WARNING,
                        (
                            f"{symbol}: stored holdings ({holding.shares:g} shares) differ "
                            f"from statement open position ({position.shares:g})."
                        ),
                        section="Open Positions",
                    )
                )

    parsed_inflows = round_money(sum(t.amount for t in statement.cash_transfers if t.amount > 0))
    if parsed_inflows > 0 and statement.deposits_inflow_total_base is not None:
        expected_inflows = round_money(statement.deposits_inflow_total_base)
        if expected_inflows > 0 and abs(parsed_inflows - expected_inflows) > 0.02:
            issues.append(
                ImportIssue(
                    ImportIssueLevel.WARNING,
                    (
                        f"Parsed deposit inflows ({parsed_inflows:,.2f}) differ from "
                        f"statement total ({expected_inflows:,.2f})."
                    ),
                    section="Deposits & Withdrawals",
                )
            )

    return issues


def prepare_statement(content: str | bytes) -> tuple[IBKRActivityStatement, list[ImportIssue], str]:
    """
    Validate and normalize a statement before the existing importer runs.

    Returns ``(statement, issues, content_fingerprint)``.
    """
    from services.ibkr_activity_parser import parse_activity_statement_csv, validate_statement

    fingerprint = content_fingerprint(content)
    statement = normalize_statement(parse_activity_statement_csv(content))
    issues = validate_statement(statement)
    issues.extend(validate_import_input(content, statement))
    issues.extend(detect_in_statement_duplicates(statement))
    issues.extend(validate_extreme_values(statement))
    return statement, issues, fingerprint


def backfill_monthly_portfolio_eur(
    ctx: PortfolioContext,
    *,
    db_path: Path | None = None,
) -> tuple[int, list[ImportIssue]]:
    """
    Write journal+price-based month-end values into ``monthly_deposits.portfolio_eur``.

    IBKR exports only include one NAV snapshot (statement end). This fills every month
    that has full pricing coverage so evolution charts do not show one spike and zeros.
    """
    from services.ibkr_activity_parser import ImportIssue, ImportIssueLevel
    from services.portfolio_monthly_valuation import compute_monthly_portfolio_valuations

    issues: list[ImportIssue] = []
    deposits = ctx.deposits.list_deposits()
    if not deposits:
        return 0, issues

    valuations = compute_monthly_portfolio_valuations(deposits, db_path=db_path)
    if not valuations:
        return 0, issues

    updated = 0
    for deposit in deposits:
        valuation = valuations.get(deposit.period_key)
        if valuation is None or valuation.coverage < 1.0 or valuation.portfolio_eur <= 0:
            continue
        if abs(deposit.portfolio_eur - valuation.portfolio_eur) < 0.01:
            continue
        ctx.deposits.upsert_deposit(
            year=deposit.period.year,
            month=deposit.period.month,
            label=deposit.label,
            deposit_eur=deposit.deposit_eur,
            deposit_usd=deposit.deposit_usd,
            portfolio_eur=valuation.portfolio_eur,
        )
        updated += 1

    if updated:
        issues.append(
            ImportIssue(
                ImportIssueLevel.INFO,
                (
                    f"Updated portfolio € for {updated} month(s) from purchase journal "
                    "and market prices."
                ),
                section="Deposits & Withdrawals",
            )
        )
    return updated, issues
